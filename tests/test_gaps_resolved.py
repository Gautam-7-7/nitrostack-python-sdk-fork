import pytest
import asyncio
import time
from typing import List
from starlette.testclient import TestClient
from nitrostack import (
    controller,
    tool,
    prompt,
    injectable,
    module,
    McpApplicationFactory,
    ExecutionContext,
    ValidationError
)
from nitrostack.core.component import Component

# 1. Test Controller and prefixing
@controller("math")
class MathController:
    @tool(name="add", description="add numbers")
    async def add(self, a: int, b: int) -> int:
        return a + b

@module(
    name="math",
    controllers=[MathController]
)
class MathModule:
    pass

@module(
    name="app",
    imports=[MathModule]
)
class TestApp:
    pass

async def _test_controller_prefixing():
    app = await McpApplicationFactory.create(TestApp)
    assert "math_add" in app.tools
    assert app.tools["math_add"].name == "math_add"

def test_controller_prefixing():
    asyncio.run(_test_controller_prefixing())

# 2. Test lifecycle hooks
class LifecycleSpy:
    def __init__(self):
        self.events: List[str] = []

    def on_module_init(self):
        self.events.append("init")

    async def on_application_bootstrap(self):
        self.events.append("bootstrap")

    def on_module_destroy(self):
        self.events.append("destroy")

    async def before_application_shutdown(self):
        self.events.append("before_shutdown")

    def on_application_shutdown(self):
        self.events.append("shutdown")

@injectable()
class ServiceWithLifecycle:
    def __init__(self, spy: LifecycleSpy):
        self.spy = spy

    def on_module_init(self):
        self.spy.events.append("service_init")

    async def on_application_bootstrap(self):
        self.spy.events.append("service_bootstrap")

    def on_module_destroy(self):
        self.spy.events.append("service_destroy")

    async def before_application_shutdown(self):
        self.spy.events.append("service_before_shutdown")

    def on_application_shutdown(self):
        self.spy.events.append("service_shutdown")

@module(
    name="lifecycle_app",
    providers=[LifecycleSpy, ServiceWithLifecycle]
)
class LifecycleApp:
    pass

async def _test_lifecycle_hooks():
    app = await McpApplicationFactory.create(LifecycleApp)
    from nitrostack.core.di import DIContainer
    spy_instance = DIContainer.get_instance().resolve(LifecycleSpy)
    
    await app._run_startup_hooks()
    assert spy_instance.events == ["init", "service_init", "bootstrap", "service_bootstrap"]
    
    await app._run_shutdown_hooks()
    assert spy_instance.events == [
        "init", "service_init", "bootstrap", "service_bootstrap",
        "destroy", "service_destroy",
        "before_shutdown", "service_before_shutdown",
        "shutdown", "service_shutdown"
    ]

def test_lifecycle_hooks():
    asyncio.run(_test_lifecycle_hooks())

# 3. Test component initialization hook
async def _test_component_initialize():
    initialized_ctx = []
    
    async def init_hook(context):
        initialized_ctx.append(context)
        
    comp = Component({
        "id": "test-comp",
        "name": "Test Component",
        "on_init": init_hook
    })
    
    await comp.initialize("dummy-context")
    assert initialized_ctx == ["dummy-context"]

def test_component_initialize():
    asyncio.run(_test_component_initialize())

# 4. Test Prompt Message contract validation
@prompt(name="test_prompt", description="test prompt")
async def valid_prompt_handler(args, context):
    return [{"role": "user", "content": "hello"}]

async def _test_prompt_validation():
    from nitrostack.core.app import validate_message_format
    
    # Test valid message validation
    msg1 = {"role": "user", "content": "hello"}
    val1 = validate_message_format(msg1)
    assert val1["role"] == "user"
    assert val1["content"] == "hello"
    
    # Test invalid role
    with pytest.raises(ValidationError) as exc:
        validate_message_format({"role": "bad_role", "content": "hello"})
    assert "Invalid prompt message role" in str(exc.value)
    
    # Test invalid content type
    with pytest.raises(ValidationError) as exc:
        validate_message_format({"role": "user", "content": 123})
    assert "content must be a string" in str(exc.value)

def test_prompt_validation():
    asyncio.run(_test_prompt_validation())
