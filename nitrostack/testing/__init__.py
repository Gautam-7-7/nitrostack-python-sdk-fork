from typing import Type, Any, List, Optional
from dataclasses import dataclass, field
from nitrostack.core.app import mcp_app, McpApplicationFactory, ServerConfig, McpApplication
from nitrostack.core.context import ExecutionContext, Logger

@dataclass
class LogEntry:
    level: str
    message: str
    meta: Optional[dict] = None

class MockLogger:
    def __init__(self):
        self.logs: List[LogEntry] = []

    def debug(self, message: str, meta: Optional[dict] = None) -> None:
        self.logs.append(LogEntry(level="debug", message=message, meta=meta))

    def info(self, message: str, meta: Optional[dict] = None) -> None:
        self.logs.append(LogEntry(level="info", message=message, meta=meta))

    def warn(self, message: str, meta: Optional[dict] = None) -> None:
        self.logs.append(LogEntry(level="warn", message=message, meta=meta))

    def error(self, message: str, meta: Optional[dict] = None) -> None:
        self.logs.append(LogEntry(level="error", message=message, meta=meta))

    def clear(self) -> None:
        self.logs.clear()

    def has_log(self, level: str, message: str) -> bool:
        return any(log.level == level and message in log.message for log in self.logs)

def create_mock_context(overrides: Optional[dict] = None) -> ExecutionContext:
    mock_logger = MockLogger()
    ctx_args = {
        "request_id": "test-request-id",
        "logger": mock_logger,
        "metadata": {},
        "auth": None,
    }
    if overrides:
        ctx_args.update(overrides)
    return ExecutionContext(**ctx_args)

class TestingModule:
    def __init__(self):
        self.mocks = {}
        self.providers = {}

    @classmethod
    def create(cls) -> "TestingModule":
        return cls()

    def add_provider(self, token: Any, provider: Any = None) -> "TestingModule":
        self.providers[token] = provider or token
        return self

    def add_mock(self, token: Any, mock: Any) -> "TestingModule":
        self.mocks[token] = mock
        return self

    async def compile(self, app_module: Type) -> "CompiledTestingModule":
        from nitrostack.core.di import DIContainer
        
        # Reset container
        DIContainer.get_instance().reset()
        container = DIContainer.get_instance()
        
        # Register mocks first
        for token, mock in self.mocks.items():
            container.register_value(token, mock)
            
        # Register custom providers
        for token, provider in self.providers.items():
            if token not in self.mocks:
                container.register(provider, token=token)
                
        # Build app
        @mcp_app(module=app_module, server=ServerConfig(name="test-server"))
        class TestApp:
            pass
            
        app = await McpApplicationFactory.create(TestApp)
        await app._run_startup_hooks()
        
        return CompiledTestingModule(app, container)

class CompiledTestingModule:
    def __init__(self, app: McpApplication, container: Any):
        self.app = app
        self.container = container

    def get(self, token: Any) -> Any:
        return self.container.resolve(token)

    async def cleanup(self) -> None:
        await self.app._run_shutdown_hooks()
        from nitrostack.core.di import DIContainer
        DIContainer.get_instance().reset()

    async def call_tool(self, name: str, arguments: dict) -> Any:
        if not self.app.mcp_server:
            raise RuntimeError("Application has not been bootstrapped.")
        res = await self.app.mcp_server.call_tool(name, arguments)
        return _extract_content(res)

    async def read_resource(self, uri: str) -> Any:
        if not self.app.mcp_server:
            raise RuntimeError("Application has not been bootstrapped.")
        res = await self.app.mcp_server.read_resource(uri)
        return _extract_resource(res)

    async def get_prompt(self, name: str, arguments: dict) -> Any:
        if not self.app.mcp_server:
            raise RuntimeError("Application has not been bootstrapped.")
        res = await self.app.mcp_server.get_prompt(name, arguments)
        
        res_obj = res[0] if isinstance(res, tuple) and len(res) > 0 else res
        if hasattr(res_obj, "messages"):
            return res_obj.messages
        return res

def _extract_content(res: Any) -> Any:
    content_list = res
    if isinstance(res, tuple) and len(res) > 0:
        content_list = res[0]

    if isinstance(content_list, list) and len(content_list) > 0:
        block = content_list[0]
        if hasattr(block, "text"):
            text_val = block.text
            import json
            try:
                return json.loads(text_val)
            except Exception:
                return text_val
    return res

def _extract_resource(res: Any) -> Any:
    content_list = []
    res_obj = res[0] if isinstance(res, tuple) and len(res) > 0 else res
    
    if isinstance(res_obj, list):
        content_list = res_obj
    elif hasattr(res_obj, "contents"):
        content_list = res_obj.contents

    if content_list and len(content_list) > 0:
        content_block = content_list[0]
        text_val = None
        if hasattr(content_block, "content"):
            text_val = content_block.content
        elif hasattr(content_block, "text"):
            text_val = content_block.text
            
        if text_val is not None:
            import json
            try:
                return json.loads(text_val)
            except Exception:
                return text_val
    return res

class NitroTestingModule:
    @classmethod
    async def create(cls, app_module: Type) -> "NitroTestingModule":
        from nitrostack.core.di import DIContainer
        DIContainer.get_instance().reset()
        
        @mcp_app(module=app_module, server=ServerConfig(name="test-server"))
        class TestApp:
            pass

        app = await McpApplicationFactory.create(TestApp)
        await app._run_startup_hooks()
        return cls(app)

    def __init__(self, app: McpApplication):
        self.app = app

    async def call_tool(self, name: str, arguments: dict) -> Any:
        if not self.app.mcp_server:
            raise RuntimeError("Application has not been bootstrapped.")
        res = await self.app.mcp_server.call_tool(name, arguments)
        return _extract_content(res)

    async def read_resource(self, uri: str) -> Any:
        if not self.app.mcp_server:
            raise RuntimeError("Application has not been bootstrapped.")
        res = await self.app.mcp_server.read_resource(uri)
        return _extract_resource(res)

    async def get_prompt(self, name: str, arguments: dict) -> Any:
        if not self.app.mcp_server:
            raise RuntimeError("Application has not been bootstrapped.")
        res = await self.app.mcp_server.get_prompt(name, arguments)
        
        res_obj = res[0] if isinstance(res, tuple) and len(res) > 0 else res
        if hasattr(res_obj, "messages"):
            return res_obj.messages
        return res
