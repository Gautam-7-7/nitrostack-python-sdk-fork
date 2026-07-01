import inspect
import threading
import typing
from typing import Any, Dict, List, Type, Union, Optional

def _get_class_dependencies(cls: Type) -> List[Any]:
    """Helper to inspect constructor signature and retrieve type-annotated dependencies."""
    if not hasattr(cls, "__init__") or cls.__init__ is object.__init__:
        return []

    # Get signature and type hints of the __init__ method
    sig = inspect.signature(cls.__init__)
    try:
        # Resolve any forward references/strings in annotations relative to the class's module
        type_hints = typing.get_type_hints(cls.__init__)
    except Exception:
        type_hints = {}

    deps = []
    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        # Skip *args and **kwargs
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        # Use typing.get_type_hints if available, fallback to parameter.annotation
        dep_type = type_hints.get(param_name, param.annotation)
        if dep_type is inspect.Parameter.empty:
            # If a dependency is missing annotations and has no default value, we cannot resolve it.
            if param.default is inspect.Parameter.empty:
                from nitrostack.core.errors import DependencyResolutionError
                raise DependencyResolutionError(
                    f"Parameter '{param_name}' of class '{cls.__name__}' is missing type annotations and cannot be auto-resolved."
                )
            else:
                continue

        # If the parameter has a default value, we only resolve it if it is registered in the DIContainer.
        # Otherwise, we skip it and let Python use the default value.
        if param.default is not inspect.Parameter.empty:
            container = DIContainer.get_instance()
            if dep_type not in container._registry and dep_type not in container._instances:
                continue

        deps.append(dep_type)

    return deps

class DIContainer:
    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "DIContainer":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton container (useful for testing)."""
        with cls._instance_lock:
            cls._instance = None

    def __init__(self):
        self._registry: Dict[Any, Type] = {}
        self._instances: Dict[Any, Any] = {}
        self._lock = threading.RLock()

    def register(self, cls: Type, token: Optional[Any] = None) -> None:
        """Register a provider class."""
        with self._lock:
            reg_token = token if token is not None else cls
            self._registry[reg_token] = cls
            if token is not None:
                self._registry[cls] = cls

    def register_value(self, token: Any, value: Any) -> None:
        """Register a constant value or instantiated service with a token."""
        with self._lock:
            self._instances[token] = value
            # Also map token to its type if possible
            if not isinstance(token, str):
                self._registry[token] = type(value)

    def resolve(self, token: Any, resolving: Optional[List[Any]] = None) -> Any:
        """
        Resolve a dependency by token (class type or string key).
        Instantiates classes if not already instantiated.
        """
        if resolving is None:
            resolving = []

        with self._lock:
            # 1. Check if we already have a cached instance
            if token in self._instances:
                return self._instances[token]

            # 2. Circular dependency detection
            if token in resolving:
                from nitrostack.core.errors import CircularDependencyError
                path = " -> ".join(str(t) for t in resolving + [token])
                raise CircularDependencyError(f"Circular dependency detected: {path}")

            # 3. Check if the token is registered as a class
            cls = self._registry.get(token)
            
            # 4. If not registered, but it's a class type, check if it's decorated with @injectable
            if cls is None and isinstance(token, type):
                cls = token
                # We auto-register it to make usage easier
                self.register(cls)

            from nitrostack.core.errors import DependencyResolutionError

            if cls is None:
                raise DependencyResolutionError(f"Dependency '{token}' is not registered in the DIContainer.")

            # 5. Resolve dependencies of the class
            deps = getattr(cls, "_mcp_deps", None)
            if deps is None:
                deps = _get_class_dependencies(cls)

            resolved_args = []
            next_resolving = resolving + [token]
            for dep in deps:
                resolved_args.append(self.resolve(dep, next_resolving))

            # 6. Instantiate the class
            try:
                instance = cls(*resolved_args)
            except Exception as e:
                from nitrostack.core.errors import DIError
                if isinstance(e, DIError):
                    raise
                raise DependencyResolutionError(f"Failed to instantiate class '{cls.__name__}' due to: {e}") from e

            # 7. Cache and return the singleton instance
            self._instances[token] = instance
            self._instances[cls] = instance
            
            provide = getattr(cls, "_mcp_provide", None)
            if provide is not None:
                self._instances[provide] = instance

            return instance

def injectable(deps: Optional[List[Any]] = None, provide: Optional[Any] = None):
    """
    Decorator to mark a class as Injectable.
    Allows custom token registration and automatic/explicit dependency resolution.
    """
    def decorator(cls: Type):
        cls._mcp_deps = deps
        cls._mcp_provide = provide
        # Automatically register with the DIContainer
        DIContainer.get_instance().register(cls, token=provide)
        return cls
    return decorator
