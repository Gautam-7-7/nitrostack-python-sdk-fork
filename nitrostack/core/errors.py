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

class TaskError(Exception):
    """Base class for task errors."""
    pass

class TaskNotFoundError(TaskError):
    """Raised when a requested task is not found."""
    pass

class TaskAlreadyTerminalError(TaskError):
    """Raised when trying to mutate a task that is already in a terminal state."""
    pass
