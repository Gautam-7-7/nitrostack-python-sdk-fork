# NitroStack Python SDK Public API Exports

from nitrostack.core.decorators import (
    tool,
    resource,
    prompt,
    initial_tool,
    widget,
    controller,
    ToolAnnotations,
    ResourceAnnotations,
    PromptArgument,
    PromptMessage,
    ToolInvocation,
    ToolExamples,
)
from nitrostack.core.tool import Tool
from nitrostack.core.resource import Resource
from nitrostack.core.prompt import Prompt
from nitrostack.core.context import (
    ExecutionContext,
    AuthContext,
    TaskContext,
    TaskCancelledError,
)
from nitrostack.core.task import (
    TaskRegistry,
)
from nitrostack.core.di import (
    injectable,
    DIContainer,
)
from nitrostack.core.module import (
    module,
)
from nitrostack.core.app import (
    mcp_app,
    McpApplicationFactory,
    ServerConfig,
)
from nitrostack.core.errors import (
    ToolExecutionError,
    ValidationError,
    ResourceNotFoundError,
    PromptNotFoundError,
)
from nitrostack.core.pipeline import (
    use_guards,
    use_middleware,
    use_interceptors,
    use_pipes,
    use_filters,
    ApiKeyGuard,
    JwtGuard,
    OAuthGuard,
)
from nitrostack.core.additional_decorators import (
    cache,
    rate_limit,
    health_check,
)
from nitrostack.events.event_emitter import (
    on_event,
    EventEmitter,
)
from nitrostack.auth.api_key import (
    ApiKeyModule,
)
from nitrostack.auth.jwt import (
    JWTModule,
    JwtModule,
)
from nitrostack.auth.oauth import (
    OAuthModule,
    OAuthService,
)
from nitrostack.auth.config import (
    ConfigModule,
    ConfigService,
)
from nitrostack.auth.secret import (
    SecretValue,
    unwrap_secret,
)
from nitrostack.auth.token_store import (
    MemoryTokenStore,
    FileTokenStore,
    create_default_token_store,
)
from nitrostack.auth.client import (
    OAuth2Client,
)
from nitrostack.auth.setup import (
    setup_jwt_auth,
    setup_api_key_auth,
    setup_oauth_auth,
    setupJWTAuth,
    setupAPIKeyAuth,
    setupOAuthAuth,
)
from nitrostack.testing import (
    NitroTestingModule,
    TestingModule,
    CompiledTestingModule,
    MockLogger,
    create_mock_context,
)

APIKeyModule = ApiKeyModule
OauthModule = OAuthModule


__all__ = [
    "tool",
    "resource",
    "prompt",
    "initial_tool",
    "widget",
    "controller",
    "ToolAnnotations",
    "ResourceAnnotations",
    "PromptArgument",
    "PromptMessage",
    "ToolInvocation",
    "ToolExamples",
    "Tool",
    "Resource",
    "Prompt",
    "ExecutionContext",
    "AuthContext",
    "injectable",
    "DIContainer",
    "module",
    "mcp_app",
    "McpApplicationFactory",
    "ServerConfig",
    "ToolExecutionError",
    "ValidationError",
    "ResourceNotFoundError",
    "PromptNotFoundError",
    "use_guards",
    "use_middleware",
    "use_interceptors",
    "use_pipes",
    "use_filters",
    "ApiKeyGuard",
    "JwtGuard",
    "OAuthGuard",
    "cache",
    "rate_limit",
    "health_check",
    "on_event",
    "EventEmitter",
    "ApiKeyModule",
    "APIKeyModule",
    "JWTModule",
    "JwtModule",
    "OAuthModule",
    "OauthModule",
    "OAuthService",
    "ConfigModule",
    "ConfigService",
    "SecretValue",
    "unwrap_secret",
    "MemoryTokenStore",
    "FileTokenStore",
    "create_default_token_store",
    "OAuth2Client",
    "setup_jwt_auth",
    "setup_api_key_auth",
    "setup_oauth_auth",
    "setupJWTAuth",
    "setupAPIKeyAuth",
    "setupOAuthAuth",
    "NitroTestingModule",
    "TestingModule",
    "CompiledTestingModule",
    "MockLogger",
    "create_mock_context",
    "TaskContext",
    "TaskCancelledError",
    "TaskRegistry",
]
