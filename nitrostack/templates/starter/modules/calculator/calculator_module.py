from nitrostack import module
from modules.calculator.calculator_tools import CalculatorTools

@module(
    name="calculator",
    controllers=[CalculatorTools],
    providers=[],
    exports=[]
)
class CalculatorModule:
    pass
