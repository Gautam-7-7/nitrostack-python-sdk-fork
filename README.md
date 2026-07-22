# NitroStack Python SDK

A Python-idiomatic port of the **NitroStack** Model Context Protocol (MCP) framework, enabling NestJS-like modular architecture, auto-resolving dependency injection, request execution pipelines, background task processing, enterprise authentication modules, Next.js UI widget compilation, and diagnostic testing harnesses.

---

## Features

- **Nested Modular Architecture**: Group components cleanly with `@module`.
- **Auto-Resolving Dependency Injection**: Constructor signatures are inspected automatically (`inspect.signature` + `get_type_hints`) with `@injectable()` without requiring manual dependency lists.
- **Request Execution Pipeline**: Guards, Middleware, Interceptors, Pipes, and Exception Filters with request context propagation and protocol error translation.
- **Asynchronous Background Tasks**: Native `asyncio.Task` background processing, cancellation with `asyncio.CancelledError`, task state supervision, and thread-pool execution for synchronous tools via `asyncio.to_thread`.
- **Enterprise Authentication**: Out-of-the-box modules for API Keys (`ApiKeyModule`), JWT token verification (`JwtModule`), OAuth 2.1 (`OAuthModule`), `SecretValue` secure wrappers, and quick setup helpers (`setup_jwt_auth`, `setup_api_key_auth`).
- **UI Widgets & Next.js Bundle Inlining**: Associate React widgets with tools using `@widget` and compile Next.js directories into inline single-file HTML templates using `compile_next_widget` (no Node.js process required in production).
- **CLI & Scaffolding (`nitrostack-py`)**: Hot-reloading development server (`nitrostack-py dev --file app.py`), scaffolding (`init`), Claude Desktop integration (`register`), and Cursor configuration (`cursor`).
- **Diagnostic Testing Harness**: Packaged `pytest` fixture (`nitro_client`) and mock execution harness (`NitroTestingModule`) for fast in-process testing.

---

## Installation

```bash
pip install nitrostack
```

To install local developer or test dependencies:
```bash
pip install -e .
```

---

## Scaffolding a New Project

You can quickly scaffold a new project template using the interactive CLI tool:

```bash
nitrostack-py init my-server
```

*(Or via Python: `python -m nitrostack.cli.main init my-server`)*

Options & Templates:
1. **Starter**: A simple calculator server with DI and testing skeletons.
2. **Advanced**: A food delivery server with items and order status tracking.
3. **OAuth**: A flight booking server demonstrating OAuth 2.1 authentication and guarded routes.

---

## Quick Start

### 1. Write your First Server

Create a file named `app.py`:

```python
import asyncio
from pydantic import BaseModel, Field
from nitrostack import (
    tool,
    resource,
    injectable,
    module,
    mcp_app,
    McpApplicationFactory,
    ServerConfig,
    ExecutionContext,
)

# 1. Input Validation Schema
class AddInput(BaseModel):
    a: float = Field(description="First number")
    b: float = Field(description="Second number")

# 2. Injected Provider Service (Auto-resolves dependencies)
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

## Advanced Capabilities

### 🛡️ Authentication & Security

NitroStack Python SDK provides pre-built security modules and guards:

#### JWT Authentication
```python
from nitrostack import JwtModule, JwtGuard, use_guards, setup_jwt_auth

# Quick setup helper or module import
setup_jwt_auth(secret_key="my-super-secret-key")

@use_guards(JwtGuard)
@tool(name="user_profile", description="Get current authenticated user profile")
async def get_profile(input: dict, ctx: ExecutionContext):
    user_id = ctx.auth.subject if ctx.auth else "anonymous"
    return {"user_id": user_id, "claims": ctx.auth.claims}
```

#### API Key Protection
```python
from nitrostack import ApiKeyModule, ApiKeyGuard, use_guards

ApiKeyModule.for_root(keys_env_prefix="API_KEY", header_name="x-api-key")

@use_guards(ApiKeyGuard)
@tool(name="admin_action", description="Protected admin tool")
async def admin_action(input: dict, ctx: ExecutionContext):
    return {"status": "success"}
```

---

### ⏳ Asynchronous Background Tasks

Tools can run long-running operations as async background tasks:

```python
from nitrostack import tool, ExecutionContext

@tool(
    name="generate_heavy_report",
    description="Generates a complex PDF report",
    task_support="required"
)
async def generate_report(input: dict, ctx: ExecutionContext):
    if ctx.task:
        ctx.task.update_progress("Processing step 1/3...")
        # Check for client cancellation requests
        ctx.task.throw_if_cancelled()
        
    await asyncio.sleep(5)
    return {"report_url": "https://storage.example.com/report.pdf"}
```

---

### 🎨 Visual UI Widgets (Next.js HTML Inlining)

Associate React components with tools and compile them into static HTML bundles for AI desktop clients:

```python
from nitrostack import tool, widget
from nitrostack.ui_next import compile_next_widget

# Statically bundle Next.js frontend route into index.html
compiled_html = compile_next_widget(
    project_dir="./frontend",
    route_path="weather-panel"
)

@tool(name="get_weather", description="Get weather forecast")
@widget(route="weather-panel")
async def get_weather(input: dict, ctx: ExecutionContext):
    return {"temperature": 72, "condition": "Sunny"}
```

---

## 🛠️ CLI Commands & Development

The `nitrostack-py` CLI automates common developer workflows:

```bash
# 1. Start hot-reloading development server
nitrostack-py dev --file app.py

# 2. Register server with Claude Desktop
nitrostack-py register --name my-mcp-server --file app.py

# 3. Configure Cursor AI (.cursor/mcp.json)
nitrostack-py cursor --name my-mcp-server --file app.py

# 4. Launch NitroStudio Dashboard
nitrostack-studio
```

---

## 🧪 Testing Harness & Pytest Integration

### Using Pytest Fixture (`nitro_client`)
NitroStack provides an out-of-the-box `pytest` fixture:

```python
import pytest

@pytest.mark.asyncio
async def test_calculator(nitro_client):
    result = await nitro_client.call_tool("add", {"a": 10, "b": 20})
    assert result == 30.0
```

### In-Process Mock Harness (`NitroTestingModule`)
```python
from nitrostack.testing import NitroTestingModule
from app import AppModule

async def test_in_process():
    harness = await NitroTestingModule.create(AppModule)
    result = await harness.call_tool("add", {"a": 5, "b": 10})
    assert result == 15.0
```

---

## Environment Configuration

| Environment Variable | Description |
|---|---|
| `PORT` / `MCP_SERVER_PORT` | The port to bind for HTTP/SSE transport (default: `8000`). |
| `MCP_TRANSPORT_TYPE` | Transport selection: `stdio`, `http`, or `dual` (combining stdio + HTTP/SSE). |
| `NODE_ENV` | If set to `production`, defaults to `dual` transport. Otherwise defaults to `stdio`. |
| `NITROSTACK_LOG_FILE` | Destination file for logs (default: `nitrostack.log`). |
| `NITROSTACK_LOG_LEVEL` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `NITROSTACK_LOG_TO_STDOUT` | Set to `true` to allow logging to stdout under stdio transport. |
