import asyncio
import os
import sys
import time
from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import ExecutionContext, AuthContext
from nitrostack.core.additional_decorators import cache, rate_limit

class MockLogger:
    def __init__(self):
        self.infos = []
        self.warns = []

    def info(self, msg):
        self.infos.append(msg)

    def warn(self, msg):
        self.warns.append(msg)

async def _test_cache_decorator():
    call_count = 0

    @cache(ttl=1)
    async def get_value(x: int, context: ExecutionContext):
        nonlocal call_count
        call_count += 1
        return x * 2

    ctx = ExecutionContext(
        request_id="test-req-cache",
        tool_name="test_tool",
        metadata={},
        logger=MockLogger()
    )

    # 1. First call - miss
    res1 = await get_value(10, ctx)
    assert res1 == 20
    assert call_count == 1

    # 2. Second call - hit
    res2 = await get_value(10, ctx)
    assert res2 == 20
    assert call_count == 1  # count should not increment

    # 3. Call with different parameter - miss
    res3 = await get_value(20, ctx)
    assert res3 == 40
    assert call_count == 2

    # 4. Wait for TTL expiration
    await asyncio.sleep(1.1)
    res4 = await get_value(10, ctx)
    assert res4 == 20
    assert call_count == 3  # count should increment now

def test_cache_decorator():
    asyncio.run(_test_cache_decorator())

async def _test_rate_limit_decorator():
    call_count = 0

    @rate_limit(max=2, window=1)
    async def limited_function(context: ExecutionContext):
        nonlocal call_count
        call_count += 1
        return "ok"

    ctx_anon = ExecutionContext(
        request_id="test-req-rl1",
        tool_name="test_tool",
        metadata={},
        logger=MockLogger(),
        auth=AuthContext(subject="anon-user")
    )

    ctx_other = ExecutionContext(
        request_id="test-req-rl2",
        tool_name="test_tool",
        metadata={},
        logger=MockLogger(),
        auth=AuthContext(subject="other-user")
    )

    # User 'anon-user' calling twice: should pass
    assert await limited_function(ctx_anon) == "ok"
    assert await limited_function(ctx_anon) == "ok"

    # User 'anon-user' calling third time: should raise ValueError
    try:
        await limited_function(ctx_anon)
        assert False, "Should have rate limited"
    except ValueError as exc:
        assert "rate limit exceeded" in str(exc).lower()

    # User 'other-user' calling: should pass (partitioned limits)
    assert await limited_function(ctx_other) == "ok"

def test_rate_limit_decorator():
    asyncio.run(_test_rate_limit_decorator())

async def _test_widget_examples_resource():
    from nitrostack.core.app import McpApplication, ServerConfig
    from nitrostack import module
    import tempfile
    import shutil
    import json
    
    # Create temp directory layout matching src/widgets/widget-manifest.json
    temp_dir = tempfile.mkdtemp()
    widgets_dir = os.path.join(temp_dir, "src", "widgets")
    os.makedirs(widgets_dir)
    
    manifest_data = {
        "version": "1.0.0",
        "widgets": [
            {"uri": "widget://test", "name": "TestWidget", "description": "Desc", "examples": []}
        ],
        "generatedAt": "2026-07-07"
    }
    
    manifest_path = os.path.join(widgets_dir, "widget-manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)
        
    old_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        @module(name="test_widget")
        class TestWidgetModule:
            pass
        app = McpApplication(TestWidgetModule)
        import mcp.types as types
        assert "widget://examples" in app.mcp_server._resource_manager._resources
        
        handler = app.mcp_server._mcp_server.request_handlers[types.ReadResourceRequest]
        req = types.ReadResourceRequest(
            method="resources/read",
            params=types.ReadResourceRequestParams(uri="widget://examples")
        )
        res = await handler(req)
        data = json.loads(res.root.contents[0].text)
        assert data["version"] == "1.0.0"
        assert data["widgets"][0]["name"] == "TestWidget"
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(temp_dir)

def test_widget_examples_resource():
    asyncio.run(_test_widget_examples_resource())

async def _test_docstring_fallback():
    from nitrostack.core.decorators import tool, prompt, resource

    class DummyInput(BaseModel):
        val: int

    @tool(name="doc_tool", input_schema=DummyInput)
    def my_tool_func(input: DummyInput, ctx: ExecutionContext):
        """This is my tool docstring description.
        It spans multiple lines.
        """
        pass

    assert my_tool_func._mcp_tool_config.description == "This is my tool docstring description.\n        It spans multiple lines."

    @prompt(name="doc_prompt")
    def my_prompt_func(args: dict, ctx: ExecutionContext):
        """This is my prompt docstring."""
        pass

    assert my_prompt_func._mcp_prompt_config.description == "This is my prompt docstring."

    @resource(uri="doc://resource", name="doc_res")
    def my_resource_func(ctx: ExecutionContext):
        """This is my resource docstring."""
        pass

    assert my_resource_func._mcp_resource_config.description == "This is my resource docstring."

def test_docstring_fallback():
    asyncio.run(_test_docstring_fallback())
