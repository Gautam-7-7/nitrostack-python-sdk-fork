from typing import Any, Callable, List, Optional, Type
from pydantic import BaseModel
from nitrostack.core.decorators import ToolAnnotations, ToolInvocation, ToolExamples
from nitrostack.core.pipeline import run_pipeline

class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Any,
        handler: Callable,
        title: Optional[str] = None,
        output_schema: Optional[Any] = None,
        annotations: Optional[ToolAnnotations] = None,
        invocation: Optional[ToolInvocation] = None,
        visibility: str = "visible",
        examples: Optional[ToolExamples] = None,
        widget: Optional[dict] = None,
        output_template: Optional[str] = None,
        is_initial: bool = False,
        task_support: str = "forbidden",
        guards: Optional[List[Type]] = None,
        middlewares: Optional[List[Type]] = None,
        interceptors: Optional[List[Type]] = None,
        pipes: Optional[List[Type]] = None,
        filters: Optional[List[Type]] = None,
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler
        self.title = title
        self.output_schema = output_schema
        self.annotations = annotations or ToolAnnotations()
        self.invocation = invocation
        self.visibility = visibility
        self.examples = examples
        self.widget = widget
        self.output_template = output_template
        self.is_initial = is_initial
        self.task_support = task_support
        self.guards = guards or []
        self.middlewares = middlewares or []
        self.interceptors = interceptors or []
        self.pipes = pipes or []
        self.filters = filters or []
        self.component = None

    def set_component(self, component: Any) -> None:
        self.component = component

    def has_component(self) -> bool:
        return self.component is not None

    def get_component(self) -> Any:
        return self.component

    async def execute(self, input_val: Any, context: Any) -> Any:
        # Determine param_type for Pydantic parsing
        param_type = None
        if isinstance(self.input_schema, type) and issubclass(self.input_schema, BaseModel):
            param_type = self.input_schema
        return await run_pipeline(
            handler=self.handler,
            handler_instance=None,
            args=(input_val, context),
            kwargs={},
            context=context,
            guards=self.guards,
            middleware=self.middlewares,
            interceptors=self.interceptors,
            pipes=self.pipes,
            filters=self.filters,
            param_name="input",
            param_type=param_type
        )
