import asyncio
import os
import sys
import time
from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import injectable, tool, use_guards, use_middleware, ExecutionContext, DIContainer
from nitrostack.core.pipeline import run_pipeline
from nitrostack.testing import NitroTestingModule
from nitrostack import module
from nitrostack.core.additional_decorators import cache, rate_limit
from nitrostack import AuthContext

class MockLogger:
    def __init__(self):
        self.infos = []
        self.warns = []
    def info(self, msg):
        self.infos.append(msg)
    def warn(self, msg):
        self.warns.append(msg)

class DummyInput(BaseModel):
    val: int

@injectable()
class SyncController:
    @tool(name="sync_val", input_schema=DummyInput)
    def sync_val(self, input: DummyInput, ctx: ExecutionContext) -> str:
        # Blocking synchronous tool function
        time.sleep(0.01)
        return f"sync: {input.val}"

@module(
    name="sync_test",
    controllers=[SyncController],
    providers=[]
)
class SyncTestModule:
    pass

async def _test_sync_tool_pipeline():
    harness = await NitroTestingModule.create(SyncTestModule)
    res = await harness.call_tool("sync_val", {"input": {"val": 42}})
    assert res == "sync: 42"

def test_sync_tool_pipeline():
    asyncio.run(_test_sync_tool_pipeline())

async def _test_sync_cache_decorator():
    call_count = 0

    @cache(ttl=1)
    def get_sync_value(x: int, context: ExecutionContext):
        nonlocal call_count
        call_count += 1
        return x * 3

    ctx = ExecutionContext(
        request_id="test-sync-cache",
        tool_name="test_tool",
        metadata={},
        logger=MockLogger()
    )

    # 1. First call - miss
    res1 = await get_sync_value(10, ctx)
    assert res1 == 30
    assert call_count == 1

    # 2. Second call - hit
    res2 = await get_sync_value(10, ctx)
    assert res2 == 30
    assert call_count == 1

    # 3. Wait for TTL expiration
    await asyncio.sleep(1.1)
    res3 = await get_sync_value(10, ctx)
    assert res3 == 30
    assert call_count == 2

def test_sync_cache_decorator():
    asyncio.run(_test_sync_cache_decorator())

async def _test_sync_rate_limit_decorator():
    call_count = 0

    @rate_limit(max=2, window=1)
    def limited_sync_function(context: ExecutionContext):
        nonlocal call_count
        call_count += 1
        return "sync_ok"

    ctx_anon = ExecutionContext(
        request_id="test-req-sync-rl",
        tool_name="test_tool",
        metadata={},
        logger=MockLogger(),
        auth=AuthContext(subject="sync-user")
    )

    assert await limited_sync_function(ctx_anon) == "sync_ok"
    assert await limited_sync_function(ctx_anon) == "sync_ok"

    try:
        await limited_sync_function(ctx_anon)
        assert False, "Should have rate limited"
    except ValueError as exc:
        assert "rate limit" in str(exc).lower()

def test_sync_rate_limit_decorator():
    asyncio.run(_test_sync_rate_limit_decorator())
