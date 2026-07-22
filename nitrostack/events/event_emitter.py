import sys
import inspect
from typing import Any, Callable, Dict, List, Tuple, Optional

class EventEmitter:
    _instance = None

    @classmethod
    def get_instance(cls) -> "EventEmitter":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def __init__(self):
        # Maps event_name -> list of (unbound_func, class_type)
        self._listeners: Dict[str, List[Tuple[Callable, Optional[Any]]]] = {}
        # Maps event_name -> list of bound_callables
        self._bound_listeners: Dict[str, List[Callable]] = {}

    def register_listener(self, event_name: str, func: Callable, class_type: Optional[Any] = None) -> None:
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append((func, class_type))

    def bind_instance(self, event_name: str, func: Callable, instance: Any) -> None:
        if event_name not in self._bound_listeners:
            self._bound_listeners[event_name] = []
        
        # Bind the unbound method to the class instance
        # Standard Python descriptor binding: func.__get__(instance, type(instance))
        bound_func = func.__get__(instance, type(instance))
        self._bound_listeners[event_name].append(bound_func)

    def emit_sync(self, event_name: str, payload: Any) -> None:
        import asyncio
        listeners = self._bound_listeners.get(event_name, [])
        for listener in listeners:
            try:
                if inspect.iscoroutinefunction(listener):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(listener(payload))
                    except RuntimeError:
                        pass
                else:
                    listener(payload)
            except Exception as e:
                sys.stderr.write(f"Event emitter error: handler for '{event_name}' failed: {e}\n")
                sys.stderr.flush()

    async def emit(self, event_name: str, payload: Any) -> None:
        listeners = self._bound_listeners.get(event_name, [])
        for listener in listeners:
            try:
                if inspect.iscoroutinefunction(listener):
                    await listener(payload)
                else:
                    listener(payload)
            except Exception as e:
                sys.stderr.write(f"Event emitter error: handler for '{event_name}' failed: {e}\n")
                sys.stderr.flush()

def on_event(event_name: str):
    """
    Decorator to mark a service or controller method as an event listener.
    """
    def decorator(func: Callable):
        func._mcp_event_name = event_name
        EventEmitter.get_instance().register_listener(event_name, func)
        return func
    return decorator
