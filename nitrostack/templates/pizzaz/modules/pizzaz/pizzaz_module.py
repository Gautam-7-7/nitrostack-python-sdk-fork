from nitrostack import module
from modules.pizzaz.pizzaz_tools import PizzazTools
from modules.pizzaz.pizzaz_service import PizzazService

@module(
    name="pizzaz",
    controllers=[PizzazTools],
    providers=[PizzazService],
    exports=[PizzazService]
)
class PizzazModule:
    pass
