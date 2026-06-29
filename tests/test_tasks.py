import asyncio
import os
import sys
import datetime
from pydantic import BaseModel

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import module, injectable, tool, ExecutionContext, NitroTestingModule
import mcp.types as types
from mcp.server.lowlevel.server import request_ctx, RequestContext

class AsyncTaskInput(BaseModel):
    duration: float

@injectable(deps=[])
class AsyncTaskController:
    @tool(
        name="delayed_tool",
        description="Simulate a long running task",
        input_schema=AsyncTaskInput,
        task_support="optional"
    )
    async def delayed_tool(self, input: AsyncTaskInput, context: ExecutionContext) -> str:
        if context.task:
            context.task.update_progress("Task started...")
            await asyncio.sleep(input.duration)
            context.task.throw_if_cancelled()
            context.task.update_progress("Finishing...")
            return "Success payload!"
        return "Sync return!"

@module(
    name="test_tasks",
    controllers=[AsyncTaskController],
    providers=[],
    imports=[],
    exports=[]
)
class TestTasksModule:
    pass

async def _test_all_tasks():
    print("Initializing NitroTestingModule with TestTasksModule...")
    harness = await NitroTestingModule.create(TestTasksModule)
    
    # 1. Start long-running task (duration 0.2s)
    print("\n1. Dispatching 'delayed_tool' as a task...")
    req = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(
            name="delayed_tool",
            arguments={"input": {"duration": 0.2}},
            task=types.TaskMetadata(ttl=60)
        )
    )
    
    handler = harness.app.mcp_server._mcp_server.request_handlers[types.CallToolRequest]
    
    # Manually set request_ctx to simulate LowLevelServer._handle_request
    token = request_ctx.set(RequestContext(
        request_id="test-req-1",
        meta=None,
        session=None,
        lifespan_context=None,
        request=req
    ))
    try:
        response = await handler(req)
    finally:
        request_ctx.reset(token)
        
    print("Response class:", type(response.root))
    assert isinstance(response.root, types.CreateTaskResult)
    task_id = response.root.task.taskId
    print(f"Task successfully spawned with ID: {task_id}")
    
    # 2. Check tasks/list
    print("\n2. Checking tasks/list endpoint...")
    list_req = types.ListTasksRequest(
        method="tasks/list",
        params=types.PaginatedRequestParams()
    )
    list_handler = harness.app.mcp_server._mcp_server.request_handlers[types.ListTasksRequest]
    list_res = await list_handler(list_req)
    print("Tasks list count:", len(list_res.tasks))
    assert len(list_res.tasks) >= 1
    assert any(t.taskId == task_id for t in list_res.tasks)

    # 3. Check tasks/get (should be working)
    print("\n3. Checking tasks/get status...")
    get_req = types.GetTaskRequest(
        method="tasks/get",
        params=types.GetTaskRequestParams(taskId=task_id)
    )
    get_handler = harness.app.mcp_server._mcp_server.request_handlers[types.GetTaskRequest]
    get_res = await get_handler(get_req)
    print("Task status:", get_res.status)
    assert get_res.status == "working"

    # 4. Wait for tasks/result
    print("\n4. Waiting for tasks/result...")
    result_req = types.GetTaskPayloadRequest(
        method="tasks/result",
        params=types.GetTaskPayloadRequestParams(taskId=task_id)
    )
    result_handler = harness.app.mcp_server._mcp_server.request_handlers[types.GetTaskPayloadRequest]
    result_res = await result_handler(result_req)
    print("Result response content:", result_res.content)
    assert result_res.isError is False
    assert "Success payload!" in result_res.content[0].text

    # 5. Check tasks/get again (should be completed)
    get_res2 = await get_handler(get_req)
    print("Task status after completion:", get_res2.status)
    assert get_res2.status == "completed"

    # 6. Test Task Cancellation
    print("\n5. Testing task cancellation...")
    req_cancel = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(
            name="delayed_tool",
            arguments={"input": {"duration": 1.0}},
            task=types.TaskMetadata(ttl=60)
        )
    )
    
    token = request_ctx.set(RequestContext(
        request_id="test-req-2",
        meta=None,
        session=None,
        lifespan_context=None,
        request=req_cancel
    ))
    try:
        resp_cancel = await handler(req_cancel)
    finally:
        request_ctx.reset(token)
        
    task_id_cancel = resp_cancel.root.task.taskId
    print(f"Spawned cancellable task: {task_id_cancel}")

    # Check it's working
    get_req_c = types.GetTaskRequest(
        method="tasks/get",
        params=types.GetTaskRequestParams(taskId=task_id_cancel)
    )
    st = await get_handler(get_req_c)
    assert st.status == "working"

    # Cancel it
    cancel_req = types.CancelTaskRequest(
        method="tasks/cancel",
        params=types.CancelTaskRequestParams(taskId=task_id_cancel)
    )
    cancel_handler = harness.app.mcp_server._mcp_server.request_handlers[types.CancelTaskRequest]
    cancel_res = await cancel_handler(cancel_req)
    print("Cancellation response status:", cancel_res.status)
    assert cancel_res.status == "cancelled"

    # Retrieve payload (should return cancelled content)
    result_req_c = types.GetTaskPayloadRequest(
        method="tasks/result",
        params=types.GetTaskPayloadRequestParams(taskId=task_id_cancel)
    )
    payload_c = await result_handler(result_req_c)
    print("Cancelled result content:", payload_c.content[0].text)
    assert payload_c.isError is True
    assert "cancelled" in payload_c.content[0].text.lower()

    print("\nAll task registry and protocol tests passed successfully!")

def test_all_tasks():
    asyncio.run(_test_all_tasks())

if __name__ == "__main__":
    test_all_tasks()
