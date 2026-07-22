from typing import Any, Callable, Dict, Optional, Set
from nitrostack.core.decorators import ResourceAnnotations
from nitrostack.core.pipeline import run_pipeline

class Resource:
    def __init__(
        self,
        uri: str,
        name: str,
        handler: Callable,
        description: Optional[str] = None,
        title: Optional[str] = None,
        mime_type: Optional[str] = None,
        size: Optional[int] = None,
        annotations: Optional[ResourceAnnotations] = None,
        metadata: Optional[Dict[str, Any]] = None,
        guards: Optional[list] = None,
        middleware: Optional[list] = None,
        interceptors: Optional[list] = None,
        pipes: Optional[list] = None,
        filters: Optional[list] = None,
    ):
        self.uri = uri
        self.name = name
        self.handler = handler
        self.description = description or ""
        self.title = title
        self.mime_type = mime_type
        self.size = size
        self.annotations = annotations or ResourceAnnotations()
        self.metadata = metadata or {}
        self.guards = guards or []
        self.middleware = middleware or []
        self.interceptors = interceptors or []
        self.pipes = pipes or []
        self.filters = filters or []
        self.subscribers: Set[str] = set()
        self.widget_read_meta: Optional[Dict[str, Any]] = None

    def attach_widget_read_meta(self, meta: Dict[str, Any]) -> None:
        self.widget_read_meta = meta

    def get_widget_read_meta(self) -> Optional[Dict[str, Any]]:
        return self.widget_read_meta

    def subscribe(self, subscriber_id: str) -> None:
        self.subscribers.add(subscriber_id)

    def unsubscribe(self, subscriber_id: str) -> None:
        self.subscribers.discard(subscriber_id)

    async def fetch(self, context: Any, uri: str) -> Any:
        # Determine dynamic args from URI placeholders if any
        # (Resource handler execution runs in pipeline)
        # Note: we can unpack parameters in kwargs based on uri matching if needed,
        # but the builder binds it inside a wrapper.
        # So builder's wrapper is what calls it.
        # However, to be fully general:
        args_dict = context.metadata if hasattr(context, "metadata") else {}
        return await run_pipeline(
            handler=self.handler,
            handler_instance=None,
            args=(),
            kwargs={**args_dict, "context": context},
            context=context,
            guards=self.guards,
            middleware=self.middleware,
            interceptors=self.interceptors,
            pipes=self.pipes,
            filters=self.filters
        )
