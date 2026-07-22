# NitroStack Python SDK

A Python-idiomatic port of the **NitroStack** Model Context Protocol (MCP) framework, enabling NestJS-like modular architecture, auto-resolving dependency injection, execution pipelines, background task supervision, enterprise security, Next.js UI widget compilation, and diagnostic testing harnesses.

---

## 🌟 Key Capabilities & Features

- 🧩 **Nested Modular Architecture**: Organize controllers, providers, and imports cleanly using `@module`.
- 💉 **Auto-Resolving Dependency Injection**: Parameter signatures are inspected dynamically at runtime (`inspect.signature` + `get_type_hints`) with `@injectable()` without requiring manual dependency arrays.
- ⚡ **Request Execution Pipeline**: Stackable Guards (`@use_guards`), Middleware (`@use_middleware`), Interceptors (`@use_interceptors`), Pipes (`@use_pipes`), and Exception Filters (`@use_filters`) with context propagation.
- ⏳ **Asynchronous Background Task Supervision**: Native `asyncio.Task` background execution (`task_support="required"`), client cancellation via `asyncio.CancelledError`, progress tracking, cursor-based pagination, and thread-pool execution for synchronous tools (`asyncio.to_thread`).
- 🛡️ **Enterprise Security Subsystem**: Pre-built modules for API Keys (`ApiKeyModule` / `APIKeyModule`), JWT validation (`JwtModule` / `JWTModule`), OAuth 2.1 (`OAuthModule` / `OAuthService`), `SecretValue` secure wrappers, Token Stores (`MemoryTokenStore`, `FileTokenStore`), and PKCE verification.
- 🎨 **UI Widgets & Next.js Asset Inlining**: Associate React widgets with tools using `@widget` and statically compile Next.js project directories into standalone single-file HTML bundles via `compile_next_widget` (no Node.js runtime process required in production).
- 📡 **Event Emitter & Telemetry**: Event-driven architecture with `@on_event("event_name")` and `EventEmitter.get_instance().emit("event_name", payload)` supporting both sync and async listener dispatch.
- 🚀 **Utilities & Decorators**: Built-in response caching (`@cache`), rate limiting (`@rate_limit`), and health check registries (`@health_check`).
- 🛠️ **CLI Scaffolding & Tooling (`nitrostack-py`)**: Hot-reloading development server (`nitrostack-py dev --file app.py`), scaffolding (`init`), Claude Desktop integration (`register`), and Cursor AI configuration (`cursor`).
- 📊 **NitroStudio Visual Dashboard (`nitrostack-studio`)**: Web-based interactive dashboard for graph visualization, tool execution, LLM mock testing, and RPC log tracing.
- 🧪 **Diagnostic Testing Harness**: Pre-packaged `pytest` fixture (`nitro_client`) registered via entrypoints, and mock execution harness (`NitroTestingModule`).

---

## 📦 Installation

```bash
pip install nitrostack
```

To install local developer or test dependencies:
```bash
pip install -e .
```

---

## 🚀 Quick Start

### 1. Write your First Server (`app.py`)

```python
import asyncio
from pydantic import BaseModel, Field
from nitrostack import (
    tool,
    resource,
    prompt,
    PromptArgument,
    PromptMessage,
    injectable,
    module,
    mcp_app,
    McpApplicationFactory,
    ServerConfig,
    ExecutionContext,
)

# 1. Input Schema (Pydantic v2)
class AddInput(BaseModel):
    a: float = Field(description="First number")
    b: float = Field(description="Second number")

# 2. Injected Provider Service (Auto-detects dependencies)
@injectable()
class CalculatorService:
    def add(self, a: float, b: float) -> float:
        return a + b

# 3. Controller
@injectable()
class CalculatorController:
    def __init__(self, service: CalculatorService):
        self.service = service

    @tool(
        name="add",
        description="Add two numbers together",
        input_schema=AddInput
    )
    async def add(self, input: AddInput, context: ExecutionContext) -> float:
        context.logger.info(f"Adding {input.a} and {input.b}")
        return self.service.add(input.a, input.b)

    @resource(
        uri="calc://info",
        name="Calculator Info",
        description="Metadata about this calculator"
    )
    async def get_info(self, context: ExecutionContext) -> str:
        return "Simple Add Calculator v1.0.0"

    @prompt(
        name="explain_addition",
        description="Generates an addition prompt template",
        arguments=[PromptArgument(name="topic", description="Target math topic")]
    )
    async def explain(self, args: dict, context: ExecutionContext):
        return [
            PromptMessage(role="user", content=f"Explain math topic: {args.get('topic')}")
        ]

# 4. Modules
@module(
    name="calculator",
    controllers=[CalculatorController],
    providers=[CalculatorService]
)
class CalculatorModule:
    pass

@module(
    name="app",
    imports=[CalculatorModule]
)
class AppModule:
    pass

# 5. Application Entrypoint
@mcp_app(
    module=AppModule,
    server=ServerConfig(name="math-server", version="1.0.0")
)
class App:
    pass

async def main():
    app = await McpApplicationFactory.create(App)
    await app.start()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 📖 Feature Guide

### 1. Dependency Injection (DI)

NitroStack automatically resolves dependencies by inspecting constructor signatures. You can also map custom token names using `provide`:

```python
from nitrostack import injectable, DIContainer

# Custom token mapping
@injectable(provide="DatabaseConnection")
class PostgresConnection:
    def query(self, sql: str):
        return ["row1", "row2"]

@injectable()
class UserRepository:
    # Resolves DatabaseConnection token automatically
    def __init__(self, db: "DatabaseConnection"):
        self.db = db
```

---

### 2. Request Execution Pipeline

Stack Guards, Middleware, Interceptors, Pipes, and Exception Filters using clean decorator syntax:

```python
from nitrostack import (
    tool,
    use_guards,
    use_middleware,
    use_interceptors,
    use_filters,
    Guard,
    Middleware,
    Interceptor,
    ExceptionFilter,
    ExecutionContext,
)

class AdminGuard(Guard):
    async def can_activate(self, context: ExecutionContext) -> bool:
        return context.auth is not None and "admin" in context.auth.scopes

class TimingInterceptor(Interceptor):
    async def intercept(self, context: ExecutionContext, call_next):
        import time
        start = time.perf_counter()
        result = await call_next()
        elapsed = time.perf_counter() - start
        context.logger.info(f"Execution finished in {elapsed:.4f}s")
        return result

@use_guards(AdminGuard)
@use_interceptors(TimingInterceptor)
@tool(name="delete_database", description="Destructive admin tool")
async def delete_db(input: dict, ctx: ExecutionContext):
    return {"deleted": True}
```

---

### 3. Enterprise Authentication & Security

NitroStack Python SDK includes production-ready security modules:

#### JWT Token Authentication
```python
from nitrostack import JwtModule, JwtGuard, use_guards, setup_jwt_auth

# Register JWT Module
JwtModule.for_root(secret_key="my-super-secret-key", expires_in="24h")

@use_guards(JwtGuard)
@tool(name="user_profile", description="Fetch current user profile")
async def get_profile(input: dict, ctx: ExecutionContext):
    user_id = ctx.auth.subject if ctx.auth else "anonymous"
    return {"user_id": user_id, "claims": ctx.auth.claims}
```

#### API Key Protection
```python
from nitrostack import ApiKeyModule, ApiKeyGuard, use_guards

ApiKeyModule.for_root(keys_env_prefix="API_KEY", header_name="x-api-key")

@use_guards(ApiKeyGuard)
@tool(name="protected_resource", description="Requires valid API key")
async def get_data(input: dict, ctx: ExecutionContext):
    return {"data": "sensitive_content"}
```

#### OAuth 2.1 Introspection & Metadata Discovery
```python
from nitrostack import OAuthModule, OAuthGuard, use_guards

OAuthModule.for_root(
    resource_uri="https://api.example.com",
    authorization_servers=["https://auth.example.com"],
    scopes_supported=["read", "write"]
)

@use_guards(OAuthGuard)
@tool(name="oauth_secured_tool", description="Guarded by OAuth token")
async def oauth_tool(input: dict, ctx: ExecutionContext):
    return {"status": "authorized"}
```

---

### 4. Asynchronous Background Task Supervision

Tools can run long-running tasks asynchronously without blocking JSON-RPC protocol communication:

```python
from nitrostack import tool, ExecutionContext

@tool(
    name="generate_large_report",
    description="Generates a complex PDF report",
    task_support="required"
)
async def generate_report(input: dict, ctx: ExecutionContext):
    if ctx.task:
        ctx.task.update_progress("Step 1 of 3: Fetching records...")
        ctx.task.throw_if_cancelled()  # Checks if client issued task cancellation
        
    await asyncio.sleep(3)
    return {"report_url": "https://storage.example.com/report-123.pdf"}
```

---

### 5. UI Widgets & Next.js Asset Inlining

Associate visual React components with tools and compile Next.js frontend projects into standalone HTML bundles:

```python
from nitrostack import tool, widget
from nitrostack.ui_next import compile_next_widget

# Compile Next.js project directory into standalone static HTML bundle
compiled_html = compile_next_widget(
    project_dir="./frontend/my-widgets",
    route_path="weather-panel"
)

@tool(name="get_weather", description="Get weather forecast")
@widget(route="weather-panel")
async def get_weather(input: dict, ctx: ExecutionContext):
    return {"temperature": 72, "condition": "Sunny", "location": "San Francisco"}
```

---

### 6. Event Emitter Pub/Sub

Subscribe to application events using `@on_event`:

```python
from nitrostack import on_event, EventEmitter, injectable

@injectable()
class AuditService:
    @on_event("user_action")
    async def handle_user_action(self, payload: dict):
        print(f"Audit log event: {payload}")

# Dispatching events:
EventEmitter.get_instance().emit_sync("user_action", {"action": "login", "user": "alice"})
```

---

### 7. Caching, Rate Limiting & Health Checks

```python
from nitrostack import cache, rate_limit, health_check, tool, ExecutionContext

@cache(ttl=60)
@rate_limit(limit=10, window=60)
@tool(name="get_stock_price", description="Fetch stock ticker price")
async def get_stock(input: dict, ctx: ExecutionContext):
    return {"symbol": input.get("symbol"), "price": 150.25}

@health_check()
def check_db():
    return {"database": "healthy"}
```

---

## 🛠️ CLI Commands Reference (`nitrostack-py`)

The CLI provides commands to initialize, build, test, and register servers:

| Command | Description | Example |
|---|---|---|
| `nitrostack-py init <name>` | Scaffold a new MCP project interactively | `nitrostack-py init my-app` |
| `nitrostack-py dev --file <file>` | Run local development server with hot-reload | `nitrostack-py dev --file app.py` |
| `nitrostack-py register` | Auto-register server script in Claude Desktop config | `nitrostack-py register --name my-server --file app.py` |
| `nitrostack-py cursor` | Auto-configure Cursor AI (`.cursor/mcp.json`) | `nitrostack-py cursor --name my-server --file app.py` |
| `nitrostack-studio` | Launch interactive visual developer dashboard | `nitrostack-studio` |

---

## 🧪 Testing Harness & Pytest Integration

### Out-of-the-Box Pytest Fixture (`nitro_client`)

NitroStack registers a default `pytest` fixture:

```python
import pytest

@pytest.mark.asyncio
async def test_calculator(nitro_client):
    result = await nitro_client.call_tool("add", {"a": 10, "b": 20})
    assert result == 30.0
```

### In-Process Harness (`NitroTestingModule`)

```python
from nitrostack.testing import NitroTestingModule
from app import AppModule

async def test_in_process():
    harness = await NitroTestingModule.create(AppModule)
    result = await harness.call_tool("add", {"a": 5, "b": 10})
    assert result == 15.0
```

---

## ⚙️ Environment Variables Reference

| Environment Variable | Description | Default |
|---|---|---|
| `PORT` / `MCP_SERVER_PORT` | Port for HTTP/SSE transport | `8000` |
| `MCP_TRANSPORT_TYPE` | Transport mode: `stdio`, `http`, or `dual` | `stdio` |
| `NODE_ENV` | If set to `production`, defaults transport to `dual` | `development` |
| `NITROSTACK_LOG_FILE` | Log file destination | `nitrostack.log` |
| `NITROSTACK_LOG_LEVEL` | Logging level (`DEBUG`, `INFO`, `WARN`, `ERROR`) | `DEBUG` |
| `NITROSTACK_LOG_TO_STDOUT` | Enable stdout logging under stdio mode | `false` |
