import pytest
from pydantic import BaseModel
from nitrostack import module, injectable, tool, ExecutionContext

class FixtureInput(BaseModel):
    num: int

@injectable()
class FixtureController:
    @tool(name="double_num", input_schema=FixtureInput)
    def double_num(self, input: FixtureInput, ctx: ExecutionContext) -> int:
        return input.num * 2

@module(
    name="fixture_test_module",
    controllers=[FixtureController]
)
class FixtureTestModule:
    pass

@pytest.fixture
def anyio_backend():
    return "asyncio"

# Define the nitro_app fixture expected by the out-of-the-box nitro_client fixture
@pytest.fixture
def nitro_app():
    return FixtureTestModule

# Test using the out-of-the-box nitro_client fixture
@pytest.mark.anyio
async def test_fixture_out_of_the_box(nitro_client):
    res = await nitro_client.call_tool("double_num", {"input": {"num": 21}})
    assert res == 42
