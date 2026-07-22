import inspect
from typing import Any, List, Optional, Type
from nitrostack.core.di import DIContainer
from nitrostack.core.tool import Tool
from nitrostack.core.resource import Resource
from nitrostack.core.prompt import Prompt

def build_tool(
    controller_instance: Any,
    method_name: str,
    options: Any,
    widget_meta: Optional[Any] = None,
    is_initial: bool = False,
) -> Tool:
    method = getattr(controller_instance, method_name)
    guards = getattr(method, "_mcp_guards", [])
    middleware = getattr(method, "_mcp_middleware", [])
    interceptors = getattr(method, "_mcp_interceptors", [])
    pipes = getattr(method, "_mcp_pipes", [])
    filters = getattr(method, "_mcp_filters", [])

    widget_dict = None
    if widget_meta:
        route_path = widget_meta.route if hasattr(widget_meta, "route") else widget_meta.get("route") if isinstance(widget_meta, dict) else str(widget_meta)
        widget_dict = {"route": route_path}

    t = Tool(
        name=options.name,
        description=options.description,
        input_schema=options.input_schema,
        handler=method,
        title=options.title,
        output_schema=options.output_schema,
        annotations=options.annotations,
        invocation=options.invocation,
        visibility=options.visibility,
        examples=options.examples,
        widget=widget_dict,
        output_template=options.metadata.get("ui/template") if options.metadata else None,
        is_initial=is_initial,
        task_support=options.task_support,
        guards=guards,
        middlewares=middleware,
        interceptors=interceptors,
        pipes=pipes,
        filters=filters,
    )

    if widget_meta:
        from nitrostack.core.component import create_component_from_next_route
        route_path = widget_meta.route if hasattr(widget_meta, "route") else widget_meta.get("route") if isinstance(widget_meta, dict) else str(widget_meta)
        domain = getattr(widget_meta, "domain", None) or (widget_meta.get("domain") if isinstance(widget_meta, dict) else None)
        prefers_border = getattr(widget_meta, "prefersBorder", None) or (widget_meta.get("prefersBorder") if isinstance(widget_meta, dict) else None)
        csp = getattr(widget_meta, "csp", None) or (widget_meta.get("csp") if isinstance(widget_meta, dict) else None)

        comp = create_component_from_next_route(
            route_path,
            options={
                "domain": domain,
                "prefersBorder": prefers_border,
                "csp": csp,
            }
        )
        t.set_component(comp)

    return t

def build_tools(controller_instance: Any) -> List[Tool]:
    tools = []
    for name, member in inspect.getmembers(controller_instance):
        if hasattr(member, "_mcp_tool_config"):
            options = getattr(member, "_mcp_tool_config")
            
            # Apply controller prefix if defined on the class
            prefix = getattr(controller_instance.__class__, "_mcp_controller_prefix", None)
            if prefix and not options.name.startswith(f"{prefix}_"):
                import dataclasses
                options = dataclasses.replace(options, name=f"{prefix}_{options.name}")
                
            widget_meta = getattr(member, "_mcp_widget_meta", None)
            if not widget_meta and hasattr(member, "_mcp_widget"):
                widget_meta = {"route": getattr(member, "_mcp_widget")}
            is_initial = getattr(member, "_mcp_is_initial", False)
            tools.append(build_tool(controller_instance, name, options, widget_meta, is_initial))
    return tools


def build_resources(controller_instance: Any) -> List[Resource]:
    resources = []
    for name, member in inspect.getmembers(controller_instance):
        if hasattr(member, "_mcp_resource_config"):
            options = getattr(member, "_mcp_resource_config")
            guards = getattr(member, "_mcp_guards", [])
            middleware = getattr(member, "_mcp_middleware", [])
            interceptors = getattr(member, "_mcp_interceptors", [])
            pipes = getattr(member, "_mcp_pipes", [])
            filters = getattr(member, "_mcp_filters", [])
            r = Resource(
                uri=options.uri,
                name=options.name,
                handler=member,
                description=options.description,
                title=options.title,
                mime_type=options.mime_type,
                size=options.size,
                annotations=options.annotations,
                metadata=options.metadata,
                guards=guards,
                middleware=middleware,
                interceptors=interceptors,
                pipes=pipes,
                filters=filters,
            )
            resources.append(r)
    return resources

def build_prompts(controller_instance: Any) -> List[Prompt]:
    prompts = []
    for name, member in inspect.getmembers(controller_instance):
        if hasattr(member, "_mcp_prompt_config"):
            options = getattr(member, "_mcp_prompt_config")
            guards = getattr(member, "_mcp_guards", [])
            middleware = getattr(member, "_mcp_middleware", [])
            interceptors = getattr(member, "_mcp_interceptors", [])
            pipes = getattr(member, "_mcp_pipes", [])
            filters = getattr(member, "_mcp_filters", [])
            p = Prompt(
                name=options.name,
                description=options.description,
                handler=member,
                arguments=options.arguments,
                guards=guards,
                middleware=middleware,
                interceptors=interceptors,
                pipes=pipes,
                filters=filters,
            )
            prompts.append(p)
    return prompts

def build_controller(controller_cls: Type) -> dict:
    container = DIContainer.get_instance()
    try:
        instance = container.resolve(controller_cls)
    except Exception:
        instance = controller_cls()
    return {
        "tools": build_tools(instance),
        "resources": build_resources(instance),
        "prompts": build_prompts(instance),
    }
