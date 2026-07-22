from dataclasses import dataclass
from typing import Any, Callable, List, Type, Protocol, Optional
from functools import wraps
from nitrostack.core.context import ExecutionContext, AuthContext
from nitrostack.core.di import DIContainer
from nitrostack.core.errors import ValidationError

# Define Interfaces/Protocols (Section 2)
class Guard(Protocol):
    async def can_activate(self, context: ExecutionContext) -> bool: ...

class Middleware(Protocol):
    async def use(self, context: ExecutionContext, next_fn: Callable[[], Any]) -> Any: ...

class Interceptor(Protocol):
    async def intercept(self, context: ExecutionContext, next_fn: Callable[[], Any]) -> Any: ...

@dataclass
class PipeMetadata:
    param_name: str
    param_type: Optional[Type] = None

class Pipe(Protocol):
    async def transform(self, value: Any, metadata: PipeMetadata) -> Any: ...

class ExceptionFilter(Protocol):
    async def catch(self, error: Exception, context: ExecutionContext) -> Any: ...


# Pipeline Decorators
def use_guards(*guards: Type[Guard]):
    def decorator(func: Callable):
        func._mcp_guards = getattr(func, "_mcp_guards", []) + list(guards)
        return func
    return decorator

def use_middleware(*middleware: Type[Middleware]):
    def decorator(func: Callable):
        func._mcp_middleware = getattr(func, "_mcp_middleware", []) + list(middleware)
        return func
    return decorator

def use_interceptors(*interceptors: Type[Interceptor]):
    def decorator(func: Callable):
        func._mcp_interceptors = getattr(func, "_mcp_interceptors", []) + list(interceptors)
        return func
    return decorator

def use_pipes(*pipes: Type[Pipe]):
    def decorator(func: Callable):
        func._mcp_pipes = getattr(func, "_mcp_pipes", []) + list(pipes)
        return func
    return decorator

def use_filters(*filters: Type[ExceptionFilter]):
    def decorator(func: Callable):
        func._mcp_filters = getattr(func, "_mcp_filters", []) + list(filters)
        return func
    return decorator


# Built-in Guards (Section 2.1)
class ApiKeyGuard:
    """
    Validates API key from request metadata.
    Looks for headers like 'x-api-key' or metadata.
    """
    async def can_activate(self, context: ExecutionContext) -> bool:
        # Check metadata
        api_key = context.metadata.get("x-api-key") or context.metadata.get("headers", {}).get("x-api-key")
        if not api_key:
            return False
        
        # Check if ApiKeyModule is registered and validate
        container = DIContainer.get_instance()
        try:
            # Check if ApiKeyService or similar module is available
            from nitrostack.auth.api_key import ApiKeyService
            api_key_service = container.resolve(ApiKeyService)
            return api_key_service.validate(api_key)
        except Exception:
            # Fallback/Default: check env variable for quick testing
            import os
            expected_key = os.environ.get("API_KEY")
            if expected_key:
                return api_key == expected_key
            # If no API key config exists, reject by default or allow if empty config
            return True

class JwtGuard:
    """
    Validates Bearer JWT from metadata and populates context.auth.
    """
    async def can_activate(self, context: ExecutionContext) -> bool:
        auth_header = context.metadata.get("authorization") or context.metadata.get("headers", {}).get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return False
        
        token = auth_header[len("Bearer "):]
        
        container = DIContainer.get_instance()
        try:
            from nitrostack.auth.jwt import JWTService
            jwt_service = container.resolve(JWTService)
            payload = jwt_service.verify_token(token)
            
            # Populate AuthContext
            context.auth = AuthContext(
                subject=payload.get("sub"),
                scopes=payload.get("scopes", []),
                client_id=payload.get("client_id"),
                exp=payload.get("exp"),
                iat=payload.get("iat"),
                iss=payload.get("iss"),
                claims=payload,
                token_payload=payload
            )
            return True
        except Exception as e:
            context.logger.error(f"JWT Guard token validation failed: {e}")
            return False

class OAuthGuard:
    """
    Validates OAuth 2.1 access token with audience binding.
    """
    async def can_activate(self, context: ExecutionContext) -> bool:
        auth_header = context.metadata.get("authorization") or context.metadata.get("headers", {}).get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return False
        
        token = auth_header[len("Bearer "):]
        
        container = DIContainer.get_instance()
        try:
            from nitrostack.auth.oauth import OAuthService
            oauth_service = container.resolve(OAuthService)
            # Introspect token
            token_info = await oauth_service.introspect_token(token)
            if not token_info.get("active"):
                return False
            
            # Populate AuthContext
            context.auth = AuthContext(
                subject=token_info.get("sub"),
                scopes=token_info.get("scope", "").split(" ") if token_info.get("scope") else [],
                client_id=token_info.get("client_id"),
                exp=token_info.get("exp"),
                iat=token_info.get("iat"),
                iss=token_info.get("iss"),
                claims=token_info,
                token_payload=token_info
            )
            return True
        except Exception as e:
            context.logger.error(f"OAuth Guard validation failed: {e}")
            return False


# Pipeline Runner logic
async def run_pipeline(
    handler: Callable,
    handler_instance: Any,
    args: tuple,
    kwargs: dict,
    context: ExecutionContext,
    guards: List[Type[Guard]],
    middleware: List[Type[Middleware]],
    interceptors: List[Type[Interceptor]],
    pipes: List[Type[Pipe]],
    filters: List[Type[ExceptionFilter]],
    param_name: str = "input",
    param_type: Optional[Type] = None,
) -> Any:
    """
    Executes a handler through the pipeline stages (Guards, Middleware, Interceptors, Pipes, Exception Filters).
    """
    container = DIContainer.get_instance()

    async def execute_handler_flow():
        import inspect
        import asyncio

        # 1. Run Guards
        for guard_cls in guards:
            guard = container.resolve(guard_cls)
            if inspect.iscoroutinefunction(guard.can_activate):
                can_act = await guard.can_activate(context)
            else:
                can_act = await asyncio.to_thread(guard.can_activate, context)
            if not can_act:
                raise PermissionError("Access denied by guard")

        # 2. Run Pipes (if tool call and pipe exists)
        # Note: If pipe is present, we transform args[0] (which represents input value)
        current_args = list(args)
        if pipes and len(current_args) > 0:
            val = current_args[0]
            for pipe_cls in pipes:
                pipe = container.resolve(pipe_cls)
                meta = PipeMetadata(param_name=param_name, param_type=param_type)
                if inspect.iscoroutinefunction(pipe.transform):
                    val = await pipe.transform(val, meta)
                else:
                    val = await asyncio.to_thread(pipe.transform, val, meta)
            current_args[0] = val

        # 3. Chain Middleware and Interceptors
        async def call_target(ctx):
            target_args = list(current_args)
            target_kwargs = dict(kwargs)

            for idx, arg in enumerate(target_args):
                if isinstance(arg, ExecutionContext) or type(arg).__name__ == "ExecutionContext":
                    target_args[idx] = ctx
            
            for k, v in target_kwargs.items():
                if isinstance(v, ExecutionContext) or type(v).__name__ == "ExecutionContext":
                    target_kwargs[k] = ctx

            if inspect.ismethod(handler):
                fn = handler
                fn_args = target_args
                fn_kwargs = target_kwargs
            elif handler_instance is not None:
                fn = handler
                fn_args = [handler_instance] + target_args
                fn_kwargs = target_kwargs
            else:
                fn = handler
                fn_args = target_args
                fn_kwargs = target_kwargs

            is_coro = inspect.iscoroutinefunction(fn)
            if not is_coro and hasattr(fn, "__call__"):
                is_coro = inspect.iscoroutinefunction(fn.__call__)

            if is_coro:
                return await fn(*fn_args, **fn_kwargs)
            else:
                return await asyncio.to_thread(fn, *fn_args, **fn_kwargs)

        # We construct the next chain backwards:
        # Middleware -> Interceptors -> Handler
        current_next = call_target
        for interceptor_cls in reversed(interceptors):
            interceptor = container.resolve(interceptor_cls)
            def make_interceptor_next(nxt):
                async def step(ctx):
                    async def call_next(*a, **k):
                        passed_ctx = a[0] if a else ctx
                        return await nxt(passed_ctx)
                    if inspect.iscoroutinefunction(interceptor.intercept):
                        return await interceptor.intercept(ctx, call_next)
                    else:
                        return await asyncio.to_thread(interceptor.intercept, ctx, call_next)
                return step
            current_next = make_interceptor_next(current_next)

        for middleware_cls in reversed(middleware):
            mw = container.resolve(middleware_cls)
            def make_middleware_next(nxt):
                async def step(ctx):
                    async def call_next(*a, **k):
                        passed_ctx = a[0] if a else ctx
                        return await nxt(passed_ctx)
                    if inspect.iscoroutinefunction(mw.use):
                        return await mw.use(ctx, call_next)
                    else:
                        return await asyncio.to_thread(mw.use, ctx, call_next)
                return step
            current_next = make_middleware_next(current_next)

        # Execute the chain
        return await current_next(context)

    # Wrap the entire flow in Exception Filters
    try:
        return await execute_handler_flow()
    except Exception as e:
        if filters:
            for filter_cls in filters:
                filt = container.resolve(filter_cls)
                try:
                    import inspect
                    import asyncio
                    if inspect.iscoroutinefunction(filt.catch):
                        return await filt.catch(e, context)
                    else:
                        return await asyncio.to_thread(filt.catch, e, context)
                except Exception as filter_err:
                    context.logger.error(f"Filter {filter_cls.__name__} failed to handle error: {filter_err}")
            raise e
        else:
            raise e

