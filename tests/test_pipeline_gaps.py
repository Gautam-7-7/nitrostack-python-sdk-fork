import asyncio
import os
import sys
from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import injectable, tool, use_guards, use_middleware, ExecutionContext, DIContainer
from nitrostack.core.pipeline import run_pipeline
from nitrostack.testing import NitroTestingModule
from nitrostack import module

class DummyInput(BaseModel):
    val: int

class FailingGuard:
    async def can_activate(self, context: ExecutionContext) -> bool:
        return False

class MyMiddleware:
    async def use(self, context: ExecutionContext, call_next):
        context.metadata["middleware_run"] = True
        return await call_next(context)

@injectable()
class PipelineController:
    @tool(name="test_val_error", input_schema=DummyInput)
    async def test_val_error(self, input: DummyInput, ctx: ExecutionContext) -> str:
        return f"ok: {input.val}"

    @tool(name="test_guard_error", input_schema=DummyInput)
    @use_guards(FailingGuard)
    async def test_guard_error(self, input: DummyInput, ctx: ExecutionContext) -> str:
        return "should not reach"

    @tool(name="test_mw_success", input_schema=DummyInput)
    @use_middleware(MyMiddleware)
    async def test_mw_success(self, input: DummyInput, ctx: ExecutionContext) -> str:
        return f"mw_run: {ctx.metadata.get('middleware_run')}"

@module(
    name="pipeline_test",
    controllers=[PipelineController],
    providers=[FailingGuard, MyMiddleware]
)
class PipelineTestModule:
    pass

async def _test_pipeline_gaps():
    harness = await NitroTestingModule.create(PipelineTestModule)
    
    # 1. Test Pydantic validation error handling
    # Passing invalid inputs (string instead of int, or missing fields)
    import mcp.types as types
    res_val = await harness.app.mcp_server.call_tool("test_val_error", {"input": {"val": "not_an_int"}})
    assert isinstance(res_val, types.CallToolResult)
    assert res_val.content[0].text.startswith("Validation failed:")
    # Check that isError is True (which translates to error response in MCP)
    assert res_val.isError is True

    # 2. Test Guard failure handling
    res_guard = await harness.app.mcp_server.call_tool("test_guard_error", {"input": {"val": 10}})
    assert isinstance(res_guard, types.CallToolResult)
    assert "Access Denied" in res_guard.content[0].text
    assert res_guard.isError is True

    # 3. Test Middleware success with ASGI-like call_next signature
    res_mw = await harness.call_tool("test_mw_success", {"input": {"val": 10}})
    # The result should be text block containing mw_run: True
    assert res_mw == "mw_run: True"

def test_pipeline_gaps():
    asyncio.run(_test_pipeline_gaps())
