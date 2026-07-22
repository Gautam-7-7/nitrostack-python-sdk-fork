from dataclasses import dataclass, field
from typing import Any, Callable, List, Dict, Optional, Type, Literal
from functools import wraps

@dataclass
class ToolAnnotations:
    destructive_hint: bool = True
    idempotent_hint: bool = False
    read_only_hint: bool = False
    open_world_hint: bool = True

@dataclass
class ResourceAnnotations:
    audience: List[Literal["user", "assistant"]] = field(default_factory=list)
    priority: float = 1.0
    last_modified: Optional[str] = None

@dataclass
class PromptArgument:
    name: str
    description: str
    required: bool = False

@dataclass
class PromptMessage:
    role: Literal["user", "assistant", "system"]
    content: str

@dataclass
class ToolInvocation:
    invoking: str
    invoked: str

@dataclass
class ToolExamples:
    input: Any
    output: Any
    description: Optional[str] = None

@dataclass
class ToolConfig:
    name: str
    description: str
    input_schema: Any  # Pydantic model class or dict schema
    title: Optional[str] = None
    output_schema: Optional[Any] = None
    annotations: ToolAnnotations = field(default_factory=ToolAnnotations)
    task_support: Literal["forbidden", "optional", "required"] = "forbidden"
    visibility: Literal["visible", "hidden"] = "visible"
    examples: Optional[ToolExamples] = None
    invocation: Optional[ToolInvocation] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_initial: bool = False

@dataclass
class ResourceConfig:
    uri: str
    name: str
    description: str
    title: Optional[str] = None
    mime_type: Optional[str] = None
    size: Optional[int] = None
    annotations: ResourceAnnotations = field(default_factory=ResourceAnnotations)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PromptConfig:
    name: str
    description: str
    arguments: List[PromptArgument] = field(default_factory=list)

def tool(
    name: str,
    description: Optional[str] = None,
    input_schema: Optional[Any] = None,
    title: Optional[str] = None,
    output_schema: Optional[Any] = None,
    annotations: Optional[ToolAnnotations] = None,
    task_support: Literal["forbidden", "optional", "required"] = "forbidden",
    visibility: Literal["visible", "hidden"] = "visible",
    examples: Optional[ToolExamples] = None,
    invocation: Optional[ToolInvocation] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Decorator to register a method as an MCP Tool.
    """
    if annotations is None:
        annotations = ToolAnnotations()
    if metadata is None:
        metadata = {}

    def decorator(func: Callable):
        desc = description
        if not desc and func.__doc__:
            desc = func.__doc__.strip()
        if not desc:
            desc = ""

        # Attach or update tool config
        config = ToolConfig(
            name=name,
            title=title,
            description=desc,
            input_schema=input_schema,
            output_schema=output_schema,
            annotations=annotations,
            task_support=task_support,
            visibility=visibility,
            examples=examples,
            invocation=invocation,
            metadata=metadata,
            is_initial=getattr(func, "_mcp_is_initial", False)
        )
        # Check if function already had a widget decorator applied first
        widget_route = getattr(func, "_mcp_widget", None)
        if widget_route:
            config.metadata["ui/template"] = widget_route
            config.metadata["ui"] = {"resourceUri": widget_route}
            config.metadata["openai/outputTemplate"] = widget_route
            
        func._mcp_tool_config = config
        return func
    return decorator

@dataclass
class WidgetCspOptions:
    connectDomains: Optional[List[str]] = None
    resourceDomains: Optional[List[str]] = None
    frameDomains: Optional[List[str]] = None

@dataclass
class WidgetRouteMetadata:
    route: str
    csp: Optional[WidgetCspOptions] = None
    domain: Optional[str] = None
    prefersBorder: Optional[bool] = None

def widget(route_path: Any):
    """
    Decorator to associate a UI widget route with a tool.
    Supports either string route or dictionary/object with domains and CSP options.
    """
    def decorator(func: Callable):
        func._mcp_widget_meta = route_path
        route = route_path
        if hasattr(route_path, "route"):
            route = route_path.route
        elif isinstance(route_path, dict):
            route = route_path.get("route")
        
        func._mcp_widget = route
        
        if hasattr(func, "_mcp_tool_config"):
            config = func._mcp_tool_config
            config.metadata["ui/template"] = route
            config.metadata["ui"] = {"resourceUri": route}
            config.metadata["openai/outputTemplate"] = route
            
            csp = None
            domain = None
            prefers_border = None
            if isinstance(route_path, dict):
                csp = route_path.get("csp")
                domain = route_path.get("domain") or route_path.get("subdomain")
                prefers_border = route_path.get("prefersBorder")
            elif hasattr(route_path, "route"):
                csp = getattr(route_path, "csp", None)
                domain = getattr(route_path, "domain", None)
                prefers_border = getattr(route_path, "prefersBorder", None)
                
            if prefers_border:
                config.metadata["openai/widgetPrefersBorder"] = True
            if domain:
                config.metadata["openai/widgetDomain"] = domain
            if csp:
                csp_meta = {}
                if isinstance(csp, dict):
                    if csp.get("connectDomains"):
                        csp_meta["connect_domains"] = csp["connectDomains"]
                    if csp.get("resourceDomains"):
                        csp_meta["resource_domains"] = csp["resourceDomains"]
                    if csp.get("frameDomains"):
                        csp_meta["frame_domains"] = csp["frameDomains"]
                else:
                    if getattr(csp, "connectDomains", None):
                        csp_meta["connect_domains"] = csp.connectDomains
                    if getattr(csp, "resourceDomains", None):
                        csp_meta["resource_domains"] = csp.resourceDomains
                    if getattr(csp, "frameDomains", None):
                        csp_meta["frame_domains"] = csp.frameDomains
                if csp_meta:
                    config.metadata["openai/widgetCSP"] = csp_meta
        return func
    return decorator

def initial_tool(func: Callable):
    """
    Stacked decorator with @tool to mark it as auto-called on client connection.
    Can be placed before or after @tool.
    """
    func._mcp_is_initial = True
    if hasattr(func, "_mcp_tool_config"):
        func._mcp_tool_config.is_initial = True
    return func

def resource(
    uri: str,
    name: str,
    description: Optional[str] = None,
    title: Optional[str] = None,
    mime_type: Optional[str] = None,
    size: Optional[int] = None,
    annotations: Optional[ResourceAnnotations] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Decorator to register a method as an MCP Resource.
    """
    if annotations is None:
        annotations = ResourceAnnotations()
    if metadata is None:
        metadata = {}

    def decorator(func: Callable):
        desc = description
        if not desc and func.__doc__:
            desc = func.__doc__.strip()
        if not desc:
            desc = ""

        config = ResourceConfig(
            uri=uri,
            name=name,
            description=desc,
            title=title,
            mime_type=mime_type,
            size=size,
            annotations=annotations,
            metadata=metadata
        )
        func._mcp_resource_config = config
        return func
    return decorator

def prompt(
    name: str,
    description: Optional[str] = None,
    arguments: Optional[List[PromptArgument]] = None,
):
    """
    Decorator to register a method as an MCP Prompt template.
    """
    if arguments is None:
        arguments = []

    def decorator(func: Callable):
        desc = description
        if not desc and func.__doc__:
            desc = func.__doc__.strip()
        if not desc:
            desc = ""

        config = PromptConfig(
            name=name,
            description=desc,
            arguments=arguments
        )
        func._mcp_prompt_config = config
        return func
    return decorator

def controller(prefix_or_options: Optional[Any] = None):
    """
    Decorator to mark a class as a Controller.
    Supports dependency injection and optional tool prefixing.
    """
    def decorator(cls: Type):
        prefix = None
        if isinstance(prefix_or_options, str):
            prefix = prefix_or_options
        elif isinstance(prefix_or_options, dict):
            prefix = prefix_or_options.get("prefix")
        cls._mcp_controller_prefix = prefix

        from nitrostack.core.di import DIContainer
        DIContainer.get_instance().register(cls)
        return cls
    return decorator

