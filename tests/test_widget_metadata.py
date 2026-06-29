import asyncio
import os
import sys

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import injectable, tool, widget, module, ExecutionContext
from nitrostack.testing import NitroTestingModule
from pydantic import BaseModel

class DummyInput(BaseModel):
    pass

@injectable()
class WidgetController:
    @tool(
        name="widget_tool",
        description="A tool with a widget",
        input_schema=DummyInput
    )
    @widget("my-custom-widget-route")
    async def widget_tool(self, input: DummyInput, context: ExecutionContext) -> dict:
        return {"status": "ok"}

@module(
    name="widget_test",
    controllers=[WidgetController]
)
class WidgetTestModule:
    pass

async def main():
    print("Testing widget decorator metadata mapping...")
    
    # 1. Initialize test harness
    harness = await NitroTestingModule.create(WidgetTestModule)
    
    # 2. Extract tools from FastMCP server
    tools = await harness.app.mcp_server.list_tools()
    
    # Find our tool
    target_tool = None
    for t in tools:
        if t.name == "widget_tool":
            target_tool = t
            break
            
    assert target_tool is not None, "widget_tool was not registered"
    
    print("Registered tool representation:", target_tool)
    
    # Verify metadata fields are present
    meta = getattr(target_tool, "meta", None)
    if meta is None:
        meta = getattr(target_tool, "_meta", {})
        
    assert meta is not None, "Tool metadata is missing"
    print("Tool metadata:", meta)
    
    # Check that widget fields are populated in metadata
    assert meta.get("ui/template") == "my-custom-widget-route"
    assert meta.get("openai/outputTemplate") == "my-custom-widget-route"
    assert meta.get("ui") == {"resourceUri": "my-custom-widget-route"}
    
    print("Success! Widget metadata is correctly mapped and verified in the MCP Tool specification.")

if __name__ == "__main__":
    asyncio.run(main())
