import os
import base64
from nitrostack import injectable, tool, widget, ExecutionContext
from pydantic import BaseModel, Field
from typing import Literal, Optional

class CalculateInput(BaseModel):
    operation: Literal["add", "subtract", "multiply", "divide"] = Field(description="The operation to perform")
    a: float = Field(description="First number")
    b: float = Field(description="Second number")

class ConvertTemperatureInput(BaseModel):
    file_name: str = Field(description="Name of the uploaded file")
    file_type: str = Field(description="MIME type of the uploaded file")
    file_content: str = Field(description="Base64 encoded file content. Will be injected by system.")
    value: Optional[float] = Field(default=None, description="Temperature value to convert")
    from_unit: Optional[Literal["C", "F"]] = Field(default=None, description="Unit to convert from (C or F)")
    to_unit: Optional[Literal["C", "F"]] = Field(default=None, description="Unit to convert to (C or F)")

@injectable()
class CalculatorTools:
    @tool(
        name="calculate",
        description="Perform basic arithmetic calculations",
        input_schema=CalculateInput
    )
    @widget("calculator-result")
    async def calculate(self, input: CalculateInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Performing calculation: {input.operation} on {input.a} and {input.b}")
        
        result = 0.0
        symbol = ""
        
        if input.operation == "add":
            result = input.a + input.b
            symbol = "+"
        elif input.operation == "subtract":
            result = input.a - input.b
            symbol = "-"
        elif input.operation == "multiply":
            result = input.a * input.b
            symbol = "×"
        elif input.operation == "divide":
            if input.b == 0:
                raise ValueError("Cannot divide by zero")
            result = input.a / input.b
            symbol = "÷"
            
        return {
            "operation": input.operation,
            "a": input.a,
            "b": input.b,
            "result": result,
            "expression": f"{input.a} {symbol} {input.b} = {result}"
        }

    @tool(
        name="convert_temperature",
        description="Convert temperature units based on file content or direct input. Supports Celsius (C) and Fahrenheit (F).",
        input_schema=ConvertTemperatureInput
    )
    async def convert_temperature(self, input: ConvertTemperatureInput, context: ExecutionContext) -> dict:
        context.logger.info(f"Processing temperature file: {input.file_name}")
        
        uploads_dir = os.path.join(os.getcwd(), "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        file_path = os.path.join(uploads_dir, input.file_name)
        
        if input.file_content:
            try:
                content_str = input.file_content
                if "," in content_str:
                    content_str = content_str.split(",", 1)[1]
                data = base64.b64decode(content_str)
                with open(file_path, "wb") as f:
                    f.write(data)
                context.logger.info(f"Saved file to {file_path}")
            except Exception as e:
                context.logger.error(f"Failed to save file: {e}")
                
        file_stats = {
            "name": input.file_name,
            "type": input.file_type,
            "saved_path": file_path,
            "status": "saved"
        }
        
        result = None
        message = f"Successfully processed and saved file {input.file_name}"
        
        if input.value is not None and input.from_unit and input.to_unit:
            try:
                message += f". Converting {input.value}°{input.from_unit} to {input.to_unit}"
                if input.from_unit == input.to_unit:
                    result = input.value
                elif input.from_unit == "C" and input.to_unit == "F":
                    result = (input.value * 9 / 5) + 32
                elif input.from_unit == "F" and input.to_unit == "C":
                    result = (input.value - 32) * 5 / 9
                else:
                    raise ValueError("Unsupported unit conversion")
                    
                if result is not None:
                    result = round(result, 2)
                    message += f". Result: {result}°{input.to_unit}"
            except Exception as e:
                message += f". Conversion failed: {e}"
        else:
            message += ". No valid conversion parameters detected from manual input or file extraction."
            
        return {
            "status": "success",
            "message": message,
            "file_info": file_stats,
            "conversion_result": {"value": result, "unit": input.to_unit} if result is not None else None,
            "original_value": {"value": input.value, "unit": input.from_unit} if input.value is not None else None
        }
