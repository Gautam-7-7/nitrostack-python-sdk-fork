import pytest
from nitrostack.testing import NitroTestingModule

@pytest.fixture
async def nitro_client(request):
    """
    An out-of-the-box pytest fixture that instantiates an in-process mock transport (NitroTestingModule).
    Expects either:
    1. A fixture named 'nitro_app' defined in the test file/conftest, returning the root module class.
    2. A test marked with '@pytest.mark.nitro_app(MyRootModule)'.
    """
    # 1. Try to retrieve a fixture named 'nitro_app'
    try:
        app_module = request.getfixturevalue("nitro_app")
        if isinstance(app_module, NitroTestingModule):
            return app_module
        harness = await NitroTestingModule.create(app_module)
        return harness
    except Exception:
        pass

    # 2. Try to retrieve the 'nitro_app' marker
    marker = request.node.get_closest_marker("nitro_app")
    if marker and marker.args:
        app_module = marker.args[0]
        harness = await NitroTestingModule.create(app_module)
        return harness

    # 3. Fallback error
    raise RuntimeError(
        "The 'nitro_client' fixture requires either a 'nitro_app' fixture or a "
        "'@pytest.mark.nitro_app(ModuleClass)' marker to be defined in your test context."
    )
