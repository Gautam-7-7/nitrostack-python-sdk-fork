# Gap Analysis: NitroStack Python SDK vs. Reference TypeScript SDK

This document provides a comprehensive evaluation of the `nitrostack-python-sdk-fork` repository against the reference TypeScript SDK. It outlines the implementation status of key features, highlight resolved gaps, and details remaining outstanding discrepancies.

---

## 1. Modules & Dependency Injection (DI)
**Reference Documentation:** [01_introduction_and_di.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/01_introduction_and_di.md)

*   **Auto-Resolving Constructor Arguments**: **[RESOLVED]**
    *   *Actual:* [di.py](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/nitrostack-python-sdk-fork/nitrostack/core/di.py) uses `inspect.signature` and `typing.get_type_hints` to auto-resolve type-annotated constructor dependencies.
*   **DI Thread-Safety**: **[RESOLVED]**
    *   *Actual:* `DIContainer` uses locking mechanisms (`threading.Lock` and `threading.RLock`) to ensure safe resolution in multi-threaded contexts.
*   **Custom Token Mapping via `provide`**: **[RESOLVED]**
    *   *Actual:* Support for registering services under custom token names or interfaces is fully implemented via `@injectable(provide="Token")`.
*   **Circular Dependency Detection**: **[RESOLVED]**
    *   *Actual:* The container tracks resolution paths and throws an explicit `CircularDependencyError` defined in `errors.py`.

---

## 2. MCP Primitives & Programmatic Builders (Tools, Resources, Prompts)
**Reference Documentation:** [02_mcp_primitives.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/02_mcp_primitives.md)

*   **Omitting Description / Docstring Parsing**: **[RESOLVED]**
    *   *Actual:* The `@tool`, `@prompt`, and `@resource` decorators make the `description` argument optional and inspect function docstrings (`func.__doc__`) to extract the description if omitted.
*   **Structured Validation Errors**: **[RESOLVED]**
    *   *Actual:* Validation errors (Pydantic and custom) are caught and translated into structured MCP protocol validation error blocks returning `types.CallToolResult(isError=True)`.
*   **Programmatic Builders**: **[RESOLVED]**
    *   *Actual:* Standalone programmatic builders (`build_tool`, `build_tools`, `build_resources`, `build_prompts`, and `build_controller`) are implemented in [builders.py](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/nitrostack-python-sdk-fork/nitrostack/core/builders.py), allowing construction of core models from decorated class controllers.
*   **Class-level Tool Name Prefixing**: **[RESOLVED]**
    *   *Actual:* The Python SDK `@controller` decorator supports a `prefix` parameter (e.g. `@controller("github")`) and `builders.py` automatically prefixes all tool names registered under that controller class.

---

## 3. Request Execution & Transport Pipeline
**Reference Documentation:** [03_execution_pipeline.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/03_execution_pipeline.md)

*   **Middleware Signature / Lambda Crash**: **[RESOLVED]**
    *   *Actual:* Middleware execution chain is constructed using dynamic async steps that correctly support ASGI-like `call_next(context)` and parameterless `call_next()` invocations, propagating context changes downstream.
*   **Guard Failure Handling**: **[RESOLVED]**
    *   *Actual:* Denials from guards (raising `PermissionError`) are caught by the translation layer and return an access denied result block with `isError=True`.
*   **Multi-Session SSE Transport Isolation**: **[RESOLVED]**
    *   *Actual:* [app.py](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/nitrostack-python-sdk-fork/nitrostack/core/app.py) handles legacy SSE connections by dynamically instantiating isolated `Server` sessions on every incoming connection inside `get_combined_app()`, preventing cross-session resource interference.

---

## 4. Security & Authentication
**Reference Documentation:** [04_security_and_auth.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/04_security_and_auth.md)

*   **Custom Cryptographic Implementations**: **[RESOLVED]**
    *   *Actual:* Uses the standard, audited `PyJWT` package for token encoding and decoding.
*   **Missing Dependencies for JWKS**: **[RESOLVED]**
    *   *Actual:* Standard dependencies `pyjwt` and `cryptography` are added to the package's dependencies in `pyproject.toml` and `requirements.txt`.
*   **Asynchronous HTTP Client for OAuth Introspection**: **[RESOLVED]**
    *   *Actual:* [oauth.py](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/nitrostack-python-sdk-fork/nitrostack/auth/oauth.py) performs token introspection requests asynchronously using `httpx.AsyncClient`.
*   **Advanced Authentication Subsystem**: **[RESOLVED]**
    *   *Actual:* The Python SDK has implemented a comprehensive auth subsystem matching TS including `SecretValue` secure wrappers, PKCE verification, Token Stores (`MemoryTokenStore`, `FileTokenStore`), an asynchronous `OAuth2Client`, and quick one-line setup utilities (`setup_jwt_auth`, `setup_api_key_auth`, `setup_oauth_auth`).

---

## 5. Async Background Tasks
**Reference Documentation:** [05_task_management.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/05_task_management.md)

*   **Task Cancellation & `asyncio.CancelledError`**: **[RESOLVED]**
    *   *Actual:* Stored active `asyncio.Task` references inside `TaskEntry` objects in the task registry. Cancellation requests call `.cancel()` on the task, raising a standard `asyncio.CancelledError` inside the running coroutine context.
*   **Synchronous Blocking Operations Support**: **[RESOLVED]**
    *   *Actual:* Run synchronous tool handlers, guards, pipes, middleware, interceptors, filters, and decorators in a thread pool executor using `asyncio.to_thread`.
*   **Task Cleanup & Resource Leakage**: **[RESOLVED]**
    *   *Actual:* The Python `TaskRegistry` in [task.py](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/nitrostack-python-sdk-fork/nitrostack/core/task.py) runs an async background task `cleanup_expired_tasks_loop` every 30 seconds to clean up expired background tasks, preventing memory leaks.
*   **Task State Transitions, Pagination, and Signals**: **[RESOLVED]**
    *   *Actual:* Enforces task state transitions, throws custom error exceptions (e.g. `TaskAlreadyTerminalError`), supports cursor-based pagination in listing, and exposes a native `AbortSignal` / `AbortController` on `TaskContext` so child procedures can respond to cancellation.

---

## 6. CLI Scaffolding & Testing Harness
**Reference Documentation:** [06_cli_and_testing.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/06_cli_and_testing.md)

*   **Hardcoded CLI Target in `nitrostack-py dev`**: **[RESOLVED]**
    *   *Actual:* CLI subcommands correctly accept a custom `--file` argument, defaulting to `"main.py"`.
*   **Missing Out-of-the-Box Pytest Fixture**: **[RESOLVED]**
    *   *Actual:* Packaged `nitrostack/testing/pytest_plugin.py` exposing the `nitro_client` fixture, registered via the `project.entry-points.pytest11` hook in `pyproject.toml`.
*   **PostHog CLI Telemetry & Analytics**: **[RESOLVED]**
    *   *Actual:* The Python CLI tracks developer commands, initialization templates, start, and build completions anonymously to PostHog via [analytics.py](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/nitrostack-python-sdk-fork/nitrostack/cli/analytics.py).
*   **Structured Logger Telemetry**: **[RESOLVED]**
    *   *Actual:* Python's logger config in [context.py](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/nitrostack-python-sdk-fork/nitrostack/core/context.py) emits structured JSON logs prefixed with `NITRO_LOG::` via the `EventEmitterHandler` so the developer CLI and monitoring wrappers can parse and display log payloads interactively.
*   **DI Mocking Test Harness (`TestingModule`)**: **[RESOLVED]**
    *   *Actual:* The Python SDK provides `TestingModule`, `CompiledTestingModule`, `MockLogger`, and `create_mock_context` inside `nitrostack/testing/__init__.py`, supporting chainable `.add_mock(...)` DI overrides, logger assertions, and lifespan hooks execution.
*   **Cursor Configuration Integration**: **[RESOLVED]**
    *   *Actual:* The Python CLI in `main.py` implements a `cursor` command configured to setup global or local `.cursor/mcp.json` configs with command, legacy-sse, and streamable-http connection support.

---

## 7. UI Widgets, Components, & Next.js Adapters
**Reference Documentation:** [07_widgets_integration.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/07_widgets_integration.md)

*   **Next.js Static HTML Inlining**: **[RESOLVED]**
    *   *Actual:* Exposes the `compile_next_widget` function, which automatically runs `npm install` and static `npm run build` inside a Next.js directory, and inline-injects stylesheet and script assets into a single static index.html.
*   **UI Components Abstraction**: **[RESOLVED]**
    *   *Actual:* The Python SDK implements the `Component` class wrapper in [component.py](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/nitrostack-python-sdk-fork/nitrostack/core/component.py) matching TS SDK component metadata representations.
*   **Advanced `@widget` Options**: **[RESOLVED]**
    *   *Actual:* The Python `@widget` decorator in [decorators.py](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/nitrostack-python-sdk-fork/nitrostack/core/decorators.py) supports route paths as dictionaries or objects, mapping advanced metadata including CSP options, prefers border, and subdomains to MCP tool schemas.
*   **Component Lifecycle Initialization Hook**: **[RESOLVED]**
    *   *Actual:* The Python SDK implements the `initialize` method on the `Component` class to trigger `on_init` / `onInit` hooks asynchronously, passing the execution context.

---

## 8. Protocols & App Modes
**Reference Documentation:** [01_introduction_and_di.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/01_introduction_and_di.md)

*   **Universal App Mode Integration**: **[RESOLVED]**
    *   *Actual:* Supported via `get_app_mode()` in [app_mode.py](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/nitrostack-python-sdk-fork/nitrostack/core/app_mode.py), mapping "universal" configuration modes and appending profile parameters (e.g. `text/html;profile=mcp-app`) to widget MIME types.
*   **Prompt Message Contract Validation**: **[RESOLVED]**
    *   *Actual:* Prompt execution results are strictly validated in `app.py` via `validate_message_format`, checking message role and string content and raising `ValidationError` on format discrepancies.
*   **Streamable HTTP Transport Limits**: **[RESOLVED]**
    *   *Actual:* Python implements `SessionLimitMiddleware` in `app.py` that limits concurrent sessions to `max_sessions` (returning HTTP 429 when exceeded) and automatically tears down idle sessions exceeding `session_timeout`.

---

## 9. Server Lifecycle Hooks
**Reference Documentation:** [01_introduction_and_di.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/01_introduction_and_di.md)

*   **Modules & Service Lifecycle Hooks**: **[RESOLVED]**
    *   *Actual:* Python SDK supports NestJS-style lifecycle hooks (`on_module_init`, `on_application_bootstrap`, `on_module_destroy`, `before_application_shutdown`, `on_application_shutdown`) run sequentially on startup and shutdown in `app.py`.

---

## 10. CLI Skills Flow & Automated Upgrades
**Reference Documentation:** [06_cli_and_testing.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/06_cli_and_testing.md)

*   **CLI Agent-Skills Installation & Upgrades**: **[RESOLVED]**
    *   *Actual:* The Python SDK provides a CLI skills management framework in `skills.py` (discovered, cloned, versioned, and copied to agent directories). This flow runs during initial project creation and upgrades.
