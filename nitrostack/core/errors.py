class ToolExecutionError(Exception):
    """Raised when tool execution fails."""
    pass

class ValidationError(Exception):
    """Raised when inputs or outputs fail schema validation."""
    pass

class ResourceNotFoundError(Exception):
    """Raised when a requested resource is not found."""
    pass

class PromptNotFoundError(Exception):
    """Raised when a requested prompt template is not found."""
    pass

class DIError(Exception):
    """Base class for dependency injection errors."""
    pass

class DependencyResolutionError(DIError):
    """Raised when a dependency cannot be resolved by the DI container."""
    pass

class CircularDependencyError(DIError):
    """Raised when a circular dependency is detected."""
    pass

class ConfigurationError(Exception):
    """Raised when configuration validation fails."""
    pass
