import time
import re
import json
import threading
from functools import wraps
from typing import Callable, Any, Dict, List, Tuple, Union, Optional
from nitrostack.core.context import ExecutionContext

def copy_mcp_attributes(src: Any, dst: Any) -> None:
    """Helper to copy all _mcp_ attributes from src function to dst function."""
    for attr in dir(src):
        if attr.startswith("_mcp_"):
            setattr(dst, attr, getattr(src, attr))

class InMemoryCacheStorage:
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            item = self._cache.get(key)
            if not item:
                return None
            if item["expires"] < time.time():
                self._cache.pop(key, None)
                return None
            return item["value"]

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            self._cache[key] = {
                "value": value,
                "expires": time.time() + ttl
            }

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def cleanup(self) -> None:
        with self._lock:
            now = time.time()
            for key, item in list(self._cache.items()):
                if item["expires"] < now:
                    self._cache.pop(key, None)

default_cache_storage = InMemoryCacheStorage()

def _start_cache_cleanup():
    def cleanup_loop():
        while True:
            time.sleep(60)
            try:
                default_cache_storage.cleanup()
            except Exception:
                pass
    t = threading.Thread(target=cleanup_loop, daemon=True)
    t.start()

_start_cache_cleanup()

def cache(
    ttl: int = 60,
    key: Optional[Callable[[Any, Any], str]] = None,
    storage: Any = None
):
    """
    Caches method outputs for a specific TTL (in seconds).
    Constructs a cache key by serializing inputs, excluding the ExecutionContext.
    """
    active_storage = storage or default_cache_storage

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find execution context
            context = None
            for arg in args:
                if isinstance(arg, ExecutionContext) or type(arg).__name__ == "ExecutionContext":
                    context = arg
                    break
            if not context:
                for v in kwargs.values():
                    if isinstance(v, ExecutionContext) or type(v).__name__ == "ExecutionContext":
                        context = v
                        break

            # Filter args and kwargs for the cache key
            filtered_args = []
            for arg in args:
                if isinstance(arg, ExecutionContext) or type(arg).__name__ == "ExecutionContext":
                    continue
                # If arg is 'self', use its class name
                if hasattr(arg, "__class__") and not isinstance(arg, (int, float, str, bool, list, dict, set, tuple)) and arg.__class__.__name__ not in ("int", "float", "str", "bool", "list", "dict", "set", "tuple"):
                    filtered_args.append(arg.__class__.__name__)
                else:
                    filtered_args.append(arg)

            filtered_kwargs = {}
            for k, v in kwargs.items():
                if isinstance(v, ExecutionContext) or type(v).__name__ == "ExecutionContext":
                    continue
                filtered_kwargs[k] = v

            # Generate cache key
            if key:
                input_val = args[0] if len(args) > 0 else None
                # Strip self if present
                if len(args) > 1 and hasattr(args[0], "__class__") and args[0].__class__.__name__ not in ("int", "float", "str", "bool", "list", "dict", "set", "tuple"):
                    input_val = args[1]
                cache_key = key(input_val, context)
            else:
                serialized_args = []
                for a in filtered_args:
                    if isinstance(a, dict) and "_meta" in a:
                        a_copy = a.copy()
                        a_copy.pop("_meta")
                        serialized_args.append(a_copy)
                    else:
                        serialized_args.append(a)
                
                serialized_kwargs = {}
                for k, v in filtered_kwargs.items():
                    if k == "_meta":
                        continue
                    serialized_kwargs[k] = v
                
                try:
                    key_parts = {
                        "func": f"{func.__module__}.{func.__name__}",
                        "args": serialized_args,
                        "kwargs": serialized_kwargs
                    }
                    cache_key = json.dumps(key_parts, sort_keys=True)
                except Exception:
                    cache_key = f"{func.__module__}.{func.__name__}:{str(filtered_args)}:{str(filtered_kwargs)}"

            import sys
            print(f"[Cache DEBUG] Checking cache for key: {cache_key}", file=sys.stderr)

            # Check cache
            cached_val = active_storage.get(cache_key)
            if cached_val is not None:
                print(f"[Cache DEBUG] HIT - returning cached result", file=sys.stderr)
                if context and getattr(context, "logger", None):
                    context.logger.info(f"[Cache] Hit for key: {cache_key}")
                return cached_val

            print(f"[Cache DEBUG] MISS - executing method", file=sys.stderr)
            import inspect
            import asyncio
            is_coro = inspect.iscoroutinefunction(func)
            if not is_coro and hasattr(func, "__call__"):
                is_coro = inspect.iscoroutinefunction(func.__call__)
            if is_coro:
                result = await func(*args, **kwargs)
            else:
                result = await asyncio.to_thread(func, *args, **kwargs)

            # Store in cache
            active_storage.set(cache_key, result, ttl)
            print(f"[Cache DEBUG] Stored result for {ttl}s", file=sys.stderr)
            if context and getattr(context, "logger", None):
                context.logger.info(f"[Cache] Miss for key: {cache_key}, stored for {ttl}s")

            return result

        copy_mcp_attributes(func, wrapper)
        return wrapper
    return decorator

def parse_window(window: Union[int, str]) -> int:
    """Parse time window string (e.g. '1m', '10s', '2h') to seconds."""
    if isinstance(window, int):
        return window
    match = re.match(r"^(\d+)([smhd])$", window)
    if not match:
        raise ValueError(f"Invalid time window format: {window}. Use format like '1m', '1h', '1d'")
    value = int(match[1])
    unit = match[2]
    multipliers = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }
    return value * multipliers[unit]

class InMemoryRateLimitStorage:
    def __init__(self):
        self._limits = {}
        self._lock = threading.Lock()

    def increment(self, key: str, window_seconds: int) -> int:
        with self._lock:
            now = time.time()
            limit = self._limits.get(key)
            if not limit or limit["reset_at"] < now:
                self._limits[key] = {
                    "count": 1,
                    "reset_at": now + window_seconds
                }
                return 1
            limit["count"] += 1
            return limit["count"]

    def reset(self, key: str) -> None:
        with self._lock:
            self._limits.pop(key, None)

    def cleanup(self) -> None:
        with self._lock:
            now = time.time()
            for key, limit in list(self._limits.items()):
                if limit["reset_at"] < now:
                    self._limits.pop(key, None)

default_rate_limit_storage = InMemoryRateLimitStorage()

def _start_rate_limit_cleanup():
    def cleanup_loop():
        while True:
            time.sleep(60)
            try:
                default_rate_limit_storage.cleanup()
            except Exception:
                pass
    t = threading.Thread(target=cleanup_loop, daemon=True)
    t.start()

_start_rate_limit_cleanup()

def rate_limit(
    max: int,
    window: Union[int, str],
    key: Optional[Callable[[ExecutionContext], str]] = None,
    storage: Any = None,
    message: Optional[str] = None
):
    """
    Rate limits method calls to max calls per window.
    """
    window_secs = parse_window(window)
    active_storage = storage or default_rate_limit_storage

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            context = None
            for arg in args:
                if isinstance(arg, ExecutionContext) or type(arg).__name__ == "ExecutionContext":
                    context = arg
                    break
            if not context:
                for v in kwargs.values():
                    if isinstance(v, ExecutionContext) or type(v).__name__ == "ExecutionContext":
                        context = v
                        break

            if key and context:
                rate_key = key(context)
            else:
                rate_key = getattr(getattr(context, "auth", None), "subject", None) or "anonymous"

            full_key = f"{func.__module__}.{func.__name__}:{rate_key}"
            count = active_storage.increment(full_key, window_secs)

            if count > max:
                err_msg = message or f"Rate limit exceeded. Maximum {max} requests per {window}"
                if context and getattr(context, "logger", None):
                    context.logger.warn(f"[RateLimit] Limit exceeded for key: {full_key}")
                raise ValueError(err_msg)

            if context and getattr(context, "logger", None):
                context.logger.info(f"[RateLimit] Request {count}/{max} for key: {full_key}")

            import inspect
            import asyncio
            is_coro = inspect.iscoroutinefunction(func)
            if not is_coro and hasattr(func, "__call__"):
                is_coro = inspect.iscoroutinefunction(func.__call__)
            if is_coro:
                return await func(*args, **kwargs)
            else:
                return await asyncio.to_thread(func, *args, **kwargs)

        copy_mcp_attributes(func, wrapper)
        return wrapper
    return decorator


class HealthCheckRegistry:
    # Maps name -> (unbound_func, class_type)
    _checks: Dict[str, Tuple[Callable, Any]] = {}
    # Maps name -> bound_callable
    _bound_checks: Dict[str, Callable[[], bool]] = {}

    @classmethod
    def register(cls, name: str, func: Callable, class_type: Any = None) -> None:
        cls._checks[name] = (func, class_type)

    @classmethod
    def bind_instance(cls, name: str, func: Callable, instance: Any) -> None:
        import inspect
        if inspect.ismethod(func):
            cls._bound_checks[name] = func
        else:
            cls._bound_checks[name] = lambda: func(instance)

    @classmethod
    def get_checks(cls) -> Dict[str, Callable[[], bool]]:
        return cls._bound_checks

    @classmethod
    def run_all(cls) -> Dict[str, str]:
        results = {}
        for name, check_fn in cls._bound_checks.items():
            try:
                import inspect
                if inspect.iscoroutinefunction(check_fn):
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    status = loop.run_until_complete(check_fn())
                else:
                    status = check_fn()
                results[name] = "healthy" if status else "unhealthy"
            except Exception as e:
                results[name] = f"error: {str(e)}"
        return results

def health_check(name: str):
    """
    Decorator to mark a service or controller method as a health check.
    """
    def decorator(func: Callable):
        func._mcp_health_check_name = name
        HealthCheckRegistry.register(name, func)
        return func
    return decorator
