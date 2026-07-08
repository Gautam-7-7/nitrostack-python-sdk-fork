# Gap Analysis: NitroStack Python SDK vs. Requirements (Updated)

This document provides a comprehensive evaluation of the `nitrostack-python-sdk-fork` repository against the design expectations and requirements specified in the `docs` folder. It outlines key implementation gaps, bugs, and missing features, showing which have been resolved.

---

## 1. Modules & Dependency Injection (DI)
**Reference:** [01_introduction_and_di.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/01_introduction_and_di.md)

*   **Auto-Resolving Constructor Arguments**: **[RESOLVED]**
    *   *Actual:* `di.py` uses `inspect.signature` and `typing.get_type_hints` to auto-resolve type-annotated constructor dependencies.
*   **DI Thread-Safety**: **[RESOLVED]**
    *   *Actual:* `DIContainer` uses locking mechanisms (`threading.Lock` and `threading.RLock`) to ensure safe resolution in multi-threaded contexts.
*   **Custom Token Mapping via `provide`**: **[RESOLVED]**
    *   *Actual:* Support for registering services under custom token names or interfaces is fully implemented via `@injectable(provide="Token")`.
*   **Circular Dependency Detection**: **[RESOLVED]**
    *   *Actual:* The container tracks resolution paths and throws an explicit `CircularDependencyError` defined in `errors.py`.

---

## 2. MCP Primitives (Tools, Resources, Prompts)
**Reference:** [02_mcp_primitives.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/02_mcp_primitives.md)

*   **Omitting Description / Docstring Parsing**: **[RESOLVED]**
    *   *Actual:* The `@tool`, `@prompt`, and `@resource` decorators make the `description` argument optional and inspect function docstrings (`func.__doc__`) to extract the description if omitted.
*   **Structured Validation Errors**: **[RESOLVED]**
    *   *Actual:* Validation errors (Pydantic and custom) are caught and translated into structured MCP protocol validation error blocks returning `types.CallToolResult(isError=True)`.

---

## 3. Request Execution Pipeline
**Reference:** [03_execution_pipeline.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/03_execution_pipeline.md)

*   **Middleware Signature / Lambda Crash**: **[RESOLVED]**
    *   *Actual:* Middleware execution chain is constructed using dynamic async steps that correctly support ASGI-like `call_next(context)` and parameterless `call_next()` invocations, propagating context changes downstream.
*   **Guard Failure Handling**: **[RESOLVED]**
    *   *Actual:* Denials from guards (raising `PermissionError`) are caught by the translation layer and return an access denied result block with `isError=True`.

---

## 4. Security & Authentication
**Reference:** [04_security_and_auth.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/04_security_and_auth.md)

*   **Custom Cryptographic Implementations (Security Flaw - Outstanding)**:
    *   *Requirement:* The SDK must wrap standard, audited packages like `PyJWT`, `cryptography`, or `authlib` to manage tokens instead of writing custom cryptographic functions.
    *   *Actual:* In `nitrostack/auth/jwt.py`, signature creation and verification are implemented from scratch using Python's standard `hmac`, `hashlib`, and `base64` modules. This custom implementation only supports HS256, lacks compliance checks, is prone to cryptographic vulnerabilities, and does not support standard production key validation methods.
*   **Missing Dependencies for JWKS (Missing / Packaging Defect - Outstanding)**:
    *   *Requirement:* Use standard Python packages for JWKS and signature checking.
    *   *Actual:* In `nitrostack/auth/oauth.py`, the JWKS verification code tries to import `jwt` (PyJWT) and use `jwt.PyJWKClient`. However, neither `PyJWT` nor `cryptography` are listed as dependencies in `pyproject.toml` or `requirements.txt`. If JWKS is enabled, invoking a protected endpoint results in a `ModuleNotFoundError`.
*   **Asynchronous HTTP Client for OAuth Introspection (Missing - Outstanding)**:
    *   *Requirement:* Validation of authorization tokens against remote Discovery endpoints must use asynchronous HTTP clients like `httpx` instead of blocking synchronous HTTP clients.
    *   *Actual:* In `nitrostack/auth/oauth.py`, `introspect_token` constructs a request and calls the synchronous `urllib.request.urlopen` standard library utility. Even though it is run within an executor (`loop.run_in_executor`), it does not use a non-blocking asynchronous library like `httpx` as required. `httpx` is not specified as a project dependency.

---

## 5. Async Background Tasks
**Reference:** [05_task_management.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/05_task_management.md)

*   **Task Cancellation & `asyncio.CancelledError` (Bug - Outstanding)**:
    *   *Requirement:* If a client requests cancellation, `asyncio.CancelledError` is raised inside the running task, triggering standard cleanups and context manager releases.
    *   *Actual:* In `nitrostack/core/task.py`, the `cancel_task` method only updates the internal metadata state (`entry.is_cancelled = True`, `entry.status = "cancelled"`). The task execution runner does not keep a reference to the `asyncio.Task` object spawned by `asyncio.create_task()`, meaning it cannot cancel the running asyncio task. The background python code continues running to completion in the background, and no `asyncio.CancelledError` is ever raised.
*   **Synchronous Blocking Operations Support (Missing - Outstanding)**:
    *   *Requirement:* Direct support for running synchronous tool functions in a separate thread pool executor (e.g. via `asyncio.to_thread`) to avoid event loop starvation.
    *   *Actual:* In `pipeline.py`'s `run_pipeline`, the handler is always directly awaited: `await handler(...)`. If a synchronous (blocking) function is registered as a tool, this call fails with a `TypeError` because synchronous functions are not awaitable.
    *   Furthermore, the `@cache` and `@rate_limit` decorators in `additional_decorators.py` are hardcoded to be asynchronous and explicitly await the wrapped function (`await func(...)`), which fails if they wrap a synchronous function.

---

## 6. CLI Scaffolding & Testing Harness
**Reference:** [06_cli_and_testing.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/06_cli_and_testing.md)

*   **Hardcoded CLI Target in `nitrostack-py dev`**: **[RESOLVED]**
    *   *Actual:* CLI subcommands correctly accept a custom `--file` argument, defaulting to `"main.py"`.
*   **Missing Out-of-the-Box Pytest Fixture (Missing - Outstanding)**:
    *   *Requirement:* Provide a pre-configured `pytest` fixture (`nitro_client`) that instantiates an in-process mock transport.
    *   *Actual:* The SDK only exports the `NitroTestingModule` class. No pytest plugins, hooks, or fixtures (`nitro_client`) are defined or packaged by the SDK.

---

## 7. UI Widgets & Next.js Adapters
**Reference:** [07_widgets_integration.md](file:///c:/Users/gauta/OneDrive/Desktop/nitrostack-codebases/docs/07_widgets_integration.md)

*   **Next.js Static HTML Inlining (Missing - Outstanding)**:
    *   *Requirement:* Compile a Next.js directory into a single HTML bundle (inline CSS/JS) using `compile_next_widget`.
    *   *Actual:* The entire frontend adaptation and compilation pipeline is missing. There is no `ui_next` module or `compile_next_widget` helper in the codebase.
