import pytest
import asyncio
from nitrostack import module, injectable, tool, ExecutionContext
from pydantic import BaseModel
import nitrostack.testing as ns_testing

# Define real service
@injectable()
class HelloService:
    def greet(self, name: str) -> str:
        return f"Hello, {name}!"

# Define mock service
class MockHelloService:
    def greet(self, name: str) -> str:
        return f"Mock Hello, {name}!"

class GreetInput(BaseModel):
    name: str

# Define controller depending on service
@injectable(deps=[HelloService])
class HelloController:
    def __init__(self, service: HelloService):
        self.service = service

    @tool(name="greet", description="Greets a user", input_schema=GreetInput)
    async def greet_tool(self, input: GreetInput, context: ExecutionContext) -> str:
        context.logger.info(f"Greeting {input.name} in tool")
        return self.service.greet(input.name)

# Define lifecycle tracking service
class LifecycleTracker:
    def __init__(self):
        self.events = []

    def on_module_init(self):
        self.events.append("init")

    def on_module_destroy(self):
        self.events.append("destroy")

# Define module
@module(
    name="hello_module",
    controllers=[HelloController],
    providers=[HelloService, LifecycleTracker],
)
class HelloModule:
    pass

def test_mock_logger():
    logger = ns_testing.MockLogger()
    logger.info("This is an info log message")
    logger.error("Something went wrong", meta={"code": 500})
    
    assert logger.has_log("info", "info log")
    assert logger.has_log("error", "went wrong")
    assert not logger.has_log("debug", "any message")

    logger.clear()
    assert len(logger.logs) == 0

def test_create_mock_context():
    ctx = ns_testing.create_mock_context()
    assert ctx.request_id == "test-request-id"
    assert isinstance(ctx.logger, ns_testing.MockLogger)

    ctx.logger.warn("Warning logged")
    assert ctx.logger.has_log("warn", "Warning logged")

@pytest.mark.asyncio
async def test_testing_module_no_mock():
    # Test without DI overrides
    testing_mod = ns_testing.TestingModule.create()
    compiled = await testing_mod.compile(HelloModule)

    try:
        # Check provider resolution
        hello_svc = compiled.get(HelloService)
        assert isinstance(hello_svc, HelloService)
        assert hello_svc.greet("World") == "Hello, World!"

        # Check lifecycle startup was triggered
        tracker = compiled.get(LifecycleTracker)
        assert tracker.events == ["init"]

        # Call tool on compiled module
        res = await compiled.call_tool("greet", {"input": {"name": "Alice"}})
        assert res == "Hello, Alice!"
    finally:
        await compiled.cleanup()
        tracker = compiled.get(LifecycleTracker)
        assert "destroy" in tracker.events

@pytest.mark.asyncio
async def test_testing_module_with_mock():
    # Mock token resolution override
    mock_svc = MockHelloService()
    
    testing_mod = ns_testing.TestingModule.create()
    testing_mod.add_mock(HelloService, mock_svc)
    
    compiled = await testing_mod.compile(HelloModule)
    
    try:
        # Check HelloService resolves to MockHelloService instead of real HelloService
        resolved_svc = compiled.get(HelloService)
        assert resolved_svc is mock_svc
        assert resolved_svc.greet("Alice") == "Mock Hello, Alice!"

        # Call tool, verify mock service was used during execution
        res = await compiled.call_tool("greet", {"input": {"name": "Bob"}})
        assert res == "Mock Hello, Bob!"
    finally:
        await compiled.cleanup()
