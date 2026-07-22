from typing import Any, Callable, List, Optional
from nitrostack.core.decorators import PromptArgument
from nitrostack.core.pipeline import run_pipeline

class Prompt:
    def __init__(
        self,
        name: str,
        description: str,
        handler: Callable,
        title: Optional[str] = None,
        arguments: Optional[List[PromptArgument]] = None,
        guards: Optional[list] = None,
        middleware: Optional[list] = None,
        interceptors: Optional[list] = None,
        pipes: Optional[list] = None,
        filters: Optional[list] = None,
    ):
        self.name = name
        self.description = description
        self.handler = handler
        self.title = title
        self.arguments = arguments or []
        self.guards = guards or []
        self.middleware = middleware or []
        self.interceptors = interceptors or []
        self.pipes = pipes or []
        self.filters = filters or []

    async def execute(self, args: dict, context: Any) -> Any:
        return await run_pipeline(
            handler=self.handler,
            handler_instance=None,
            args=(args, context),
            kwargs={},
            context=context,
            guards=self.guards,
            middleware=self.middleware,
            interceptors=self.interceptors,
            pipes=self.pipes,
            filters=self.filters
        )
