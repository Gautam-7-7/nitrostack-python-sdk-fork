import asyncio
import os
import sys
from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import module, injectable, tool, ExecutionContext, NitroTestingModule, TaskRegistry
import mcp.types as types
from mcp.server.lowlevel.server import request_ctx, RequestContext

class RealCancelInput(BaseModel):
    duration: float

task_cancelled_flag = False

@injectable(deps=[])
class RealCancelController:
    @tool(
        name="cancel_target_tool",
        description="Task to test cancellation",
        input_schema=RealCancelInput,
        task_support="required"
    )
    async def cancel_target_tool(self, input: RealCancelInput, context: ExecutionContext) -> str:
        global task_cancelled_flag
        task_cancelled_flag = False
        if context.task:
            try:
                # Sleep and check cancellation
                await asyncio.sleep(input.duration)
                return "Completed without cancel!"
            except asyncio.CancelledError:
                task_cancelled_flag = True
                raise
        return "Sync!"

@module(
    name="real_cancel_test",
    controllers=[RealCancelController],
    providers=[],
    imports=[],
    exports=[]
)
class RealCancelModule:
    pass

async def _test_task_cancellation_real():
    global task_cancelled_flag
    harness = await NitroTestingModule.create(RealCancelModule)

    req = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(
            name="cancel_target_tool",
            arguments={"input": {"duration": 2.0}},
            task=types.TaskMetadata(ttl=60)
        )
    )
    
    handler = harness.app.mcp_server._mcp_server.request_handlers[types.CallToolRequest]
    
    token = request_ctx.set(RequestContext(
        request_id="test-req-c1",
        meta=None,
        session=None,
        lifespan_context=None,
        request=req
    ))
    try:
        response = await handler(req)
    finally:
        request_ctx.reset(token)

    task_id = response.root.task.taskId
    
    # Let the background task start running and yield control to its sleep
    await asyncio.sleep(0.1)
    
    # Task should be working
    entry = TaskRegistry.get_task(task_id)
    assert entry is not None
    assert entry.status == "working"
    
    # Cancel the task
    cancel_req = types.CancelTaskRequest(
        method="tasks/cancel",
        params=types.CancelTaskRequestParams(taskId=task_id)
    )
    cancel_handler = harness.app.mcp_server._mcp_server.request_handlers[types.CancelTaskRequest]
    cancel_res = await cancel_handler(cancel_req)
    assert cancel_res.status == "cancelled"

    # Wait a small moment to let the background task raise CancelledError and run except block
    await asyncio.sleep(0.1)


    # Verify status in registry
    assert entry.status == "cancelled"
    # Verify the background execution task indeed caught asyncio.CancelledError
    assert task_cancelled_flag is True

def test_task_cancellation_real():
    asyncio.run(_test_task_cancellation_real())
