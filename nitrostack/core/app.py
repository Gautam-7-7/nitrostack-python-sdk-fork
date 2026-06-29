import os
import sys
import uuid
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Set, Type, Optional
from mcp.server.fastmcp import FastMCP
from mcp.types import PromptMessage as McpPromptMessage, TextContent
from pydantic import BaseModel, create_model

from nitrostack.core.context import ExecutionContext
from nitrostack.core.decorators import ToolConfig, ResourceConfig, PromptConfig
from nitrostack.core.di import DIContainer
from nitrostack.core.pipeline import run_pipeline
from nitrostack.core.additional_decorators import HealthCheckRegistry
from nitrostack.events.event_emitter import EventEmitter

# Monkeypatch FastMCP.call_tool to support returning CreateTaskResult without conversion
_original_fastmcp_call_tool = FastMCP.call_tool

async def _custom_fastmcp_call_tool(self, name: str, arguments: dict[str, Any]):
    t = self._tool_manager.get_tool(name)
    if not t:
        return await _original_fastmcp_call_tool(self, name, arguments)
    context = self.get_context()
    result = await self._tool_manager.call_tool(
        name, arguments, context=context, convert_result=False
    )
    import mcp.types as types
    if isinstance(result, types.CreateTaskResult):
        return result
    return t.fn_metadata.convert_result(result)

FastMCP.call_tool = _custom_fastmcp_call_tool

@dataclass
class ServerConfig:
    name: str
    version: str = "1.0.0"
    transport_type: Optional[str] = None

def mcp_app(module: Type, server: ServerConfig):
    """
    Decorator to declare the main application class.
    Specifies the root AppModule and ServerConfig.
    """
    def decorator(cls: Type):
        cls._mcp_app_module = module
        cls._mcp_app_server = server
        return cls
    return decorator


def get_pydantic_model(schema: Any) -> Type[BaseModel]:
    """Helper to resolve or construct a Pydantic model for input validation."""
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema
    if isinstance(schema, dict):
        # Dynamically build a Pydantic model from JSON schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        fields = {}
        for name, prop in properties.items():
            t = Any
            prop_type = prop.get("type")
            if prop_type == "string":
                t = str
            elif prop_type == "integer":
                t = int
            elif prop_type == "number":
                t = float
            elif prop_type == "boolean":
                t = bool
            elif prop_type == "array":
                t = list
            elif prop_type == "object":
                t = dict
                
            default = ... if name in required else None
            fields[name] = (t, default)
        return create_model("DynamicInputModel", **fields)
    
    # Return a default empty model if invalid or empty
    return create_model("EmptyInputModel")


class McpApplication:
    def __init__(self, app_class: Type):
        self.app_class = app_class
        if hasattr(app_class, "_mcp_app_module"):
            self.root_module = app_class._mcp_app_module
            self.server_config = app_class._mcp_app_server
        elif hasattr(app_class, "_mcp_module_config"):
            self.root_module = app_class
            self.server_config = ServerConfig(name=app_class._mcp_module_config.name or "mcp-server")
        else:
            raise ValueError("Invalid application class. Must be decorated with @mcp_app or @module.")
        self.mcp_server: Optional[FastMCP] = None
        self._bootstrap()

    def _bootstrap(self) -> None:
        # 1. Initialize FastMCP
        self.mcp_server = FastMCP(
            name=self.server_config.name
        )

        # 2. Resolve Module Tree recursively and register services
        resolved_modules: Set[Type] = set()
        self._resolve_modules(self.root_module, resolved_modules)

        container = DIContainer.get_instance()

        # Instantiate all providers and controllers to populate container
        for mod in resolved_modules:
            mod_config = getattr(mod, "_mcp_module_config", None)
            if mod_config:
                # Register & Resolve all providers
                for provider in mod_config.providers:
                    container.resolve(provider)
                # Register & Resolve all controllers
                for controller in mod_config.controllers:
                    container.resolve(controller)

        # 3. Discover decorated methods on all instances in the container
        initial_tools = []
        for token, instance in list(container._instances.items()):
            # Scan members of this instance
            for name, member in inspect.getmembers(instance):
                # Discover Tools
                if hasattr(member, "_mcp_tool_config"):
                    tool_config: ToolConfig = getattr(member, "_mcp_tool_config")
                    self._register_tool(instance, member, tool_config)
                    if tool_config.is_initial:
                        initial_tools.append((instance, member, tool_config))

                # Discover Resources
                if hasattr(member, "_mcp_resource_config"):
                    resource_config: ResourceConfig = getattr(member, "_mcp_resource_config")
                    self._register_resource(instance, member, resource_config)

                # Discover Prompts
                if hasattr(member, "_mcp_prompt_config"):
                    prompt_config: PromptConfig = getattr(member, "_mcp_prompt_config")
                    self._register_prompt(instance, member, prompt_config)

                # Bind Health Checks
                if hasattr(member, "_mcp_health_check_name"):
                    check_name = getattr(member, "_mcp_health_check_name")
                    HealthCheckRegistry.bind_instance(check_name, member, instance)

                # Bind Event Listeners
                if hasattr(member, "_mcp_event_name"):
                    event_name = getattr(member, "_mcp_event_name")
                    EventEmitter.get_instance().bind_instance(event_name, member, instance)

        # 4. Register Built-in Health check Resource if any checks exist
        if HealthCheckRegistry.get_checks():
            @self.mcp_server.resource("health://status", name="Health Status", description="System health status check")
            def health_status_resource() -> str:
                import json
                results = HealthCheckRegistry.run_all()
                return json.dumps(results)

        # 5. Register Task Support hook & endpoints
        low_level_server = self.mcp_server._mcp_server
        original_get_caps = low_level_server.get_capabilities

        def custom_get_capabilities(notification_options, experimental_capabilities):
            caps = original_get_caps(notification_options, experimental_capabilities)
            import mcp.types as types
            caps.tasks = types.ServerTasksCapability(
                list=types.TasksListCapability(),
                cancel=types.TasksCancelCapability(),
                requests=types.ServerTasksRequestsCapability()
            )
            return caps

        low_level_server.get_capabilities = custom_get_capabilities

        # Class-level monkeypatch handles call_tool mapping

        import mcp.types as types
        from nitrostack.core.task import TaskRegistry

        async def handle_list_tasks(req):
            tasks_list = [
                types.Task(
                    taskId=t.task_id,
                    status=t.status,
                    statusMessage=t.status_message,
                    createdAt=t.created_at,
                    lastUpdatedAt=t.last_updated_at,
                    ttl=t.ttl,
                    pollInterval=t.poll_interval
                )
                for t in TaskRegistry.list_tasks()
            ]
            return types.ListTasksResult(tasks=tasks_list, nextCursor=None)

        async def handle_get_task(req):
            task_id = req.params.taskId
            t = TaskRegistry.get_task(task_id)
            if not t:
                raise types.McpError(
                    types.ErrorData(
                        code=types.INVALID_PARAMS,
                        message=f"Task {task_id} not found"
                    )
                )
            return types.GetTaskResult(
                taskId=t.task_id,
                status=t.status,
                statusMessage=t.status_message,
                createdAt=t.created_at,
                lastUpdatedAt=t.last_updated_at,
                ttl=t.ttl,
                pollInterval=t.poll_interval
            )

        async def handle_cancel_task(req):
            task_id = req.params.taskId
            t = TaskRegistry.get_task(task_id)
            if not t:
                raise types.McpError(
                    types.ErrorData(
                        code=types.INVALID_PARAMS,
                        message=f"Task {task_id} not found"
                    )
                )
            TaskRegistry.cancel_task(task_id)
            t = TaskRegistry.get_task(task_id)
            return types.CancelTaskResult(
                taskId=t.task_id,
                status=t.status,
                statusMessage=t.status_message,
                createdAt=t.created_at,
                lastUpdatedAt=t.last_updated_at,
                ttl=t.ttl,
                pollInterval=t.poll_interval
            )

        async def handle_get_task_payload(req):
            task_id = req.params.taskId
            t = TaskRegistry.get_task(task_id)
            if not t:
                raise types.McpError(
                    types.ErrorData(
                        code=types.INVALID_PARAMS,
                        message=f"Task {task_id} not found"
                    )
                )
            await t.done_event.wait()
            if t.status == "completed":
                return t.result
            elif t.status == "cancelled":
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text="Task was cancelled.")],
                    isError=True
                )
            else:
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=str(t.error or t.status_message))],
                    isError=True
                )

        low_level_server.request_handlers[types.ListTasksRequest] = handle_list_tasks
        low_level_server.request_handlers[types.GetTaskRequest] = handle_get_task
        low_level_server.request_handlers[types.CancelTaskRequest] = handle_cancel_task
        low_level_server.request_handlers[types.GetTaskPayloadRequest] = handle_get_task_payload

        # 6. Register App Mode formatters for tool listings
        original_list_tools_handler = low_level_server.request_handlers.get(types.ListToolsRequest)
        if original_list_tools_handler:
            async def custom_list_tools_handler(req):
                res = await original_list_tools_handler(req)
                app_mode = os.environ.get("NITROSTACK_APP_MODE", "mcp")
                if app_mode in ("openai", "mcpapps"):
                    for tool in res.tools:
                        if tool.meta is None:
                            tool.meta = {}
                        if app_mode == "openai":
                            tool.meta["openai/type"] = "function"
                            tool.meta["openai/function"] = {
                                "name": tool.name,
                                "description": tool.description,
                                "parameters": tool.inputSchema
                            }
                        elif app_mode == "mcpapps":
                            tool.meta["_meta"] = {
                                "ui": {
                                    "title": tool.title or tool.name,
                                    "description": tool.description
                                }
                            }
                return res
            low_level_server.request_handlers[types.ListToolsRequest] = custom_list_tools_handler

        # 7. Register a notification handler for initialized to auto-call @initial_tool annotated tools
        async def handle_initialized(notification: types.InitializedNotification):
            for inst, memb, config in initial_tools:
                try:
                    input_model = get_pydantic_model(config.input_schema)
                    try:
                        input_inst = input_model()
                    except Exception:
                        input_inst = None
                    
                    ctx = ExecutionContext(
                        request_id=f"initial-tool-{uuid.uuid4().hex[:8]}",
                        tool_name=config.name,
                        metadata={}
                    )
                    
                    guards = getattr(memb, "_mcp_guards", [])
                    middleware = getattr(memb, "_mcp_middleware", [])
                    interceptors = getattr(memb, "_mcp_interceptors", [])
                    pipes = getattr(memb, "_mcp_pipes", [])
                    filters = getattr(memb, "_mcp_filters", [])

                    await run_pipeline(
                        handler=memb,
                        handler_instance=inst,
                        args=(input_inst, ctx),
                        kwargs={},
                        context=ctx,
                        guards=guards,
                        middleware=middleware,
                        interceptors=interceptors,
                        pipes=pipes,
                        filters=filters,
                        param_name="input",
                        param_type=input_model
                    )
                except Exception as e:
                    import sys
                    print(f"Error executing initial tool '{config.name}': {e}", file=sys.stderr)

        low_level_server.notification_handlers[types.InitializedNotification] = handle_initialized

    def _resolve_modules(self, module_class: Type, resolved_modules: Set[Type]) -> None:
        if module_class in resolved_modules:
            return
        resolved_modules.add(module_class)

        mod_config = getattr(module_class, "_mcp_module_config", None)
        if mod_config:
            for imp in mod_config.imports:
                self._resolve_modules(imp, resolved_modules)

    def _register_tool(self, instance: Any, method: Callable, tool_config: ToolConfig) -> None:
        input_model = get_pydantic_model(tool_config.input_schema)

        # Define the wrapper function that executes pipeline stages
        async def tool_wrapper(input: input_model) -> Any:
            # Check if task execution is requested or required
            task_metadata = None
            try:
                from mcp.server.lowlevel.server import request_ctx
                req = request_ctx.get().request
                task_metadata = getattr(req.params, "task", None) if req and hasattr(req, "params") else None
            except Exception:
                pass
            
            is_task = (task_metadata is not None) or (tool_config.task_support == "required")
            if tool_config.task_support == "forbidden":
                is_task = False

            if is_task:
                task_id = f"task_{uuid.uuid4().hex[:12]}"
                ttl = task_metadata.ttl if task_metadata else 300
                from nitrostack.core.task import TaskRegistry
                TaskRegistry.create_task(task_id, ttl=ttl)

                async def background_execution():
                    task_ctx = ExecutionContext(
                        request_id=str(uuid.uuid4()),
                        tool_name=tool_config.name,
                        metadata={"input": input}
                    )
                    from nitrostack.core.context import TaskContext
                    task_ctx.task = TaskContext(task_id)
                    try:
                        guards = getattr(method, "_mcp_guards", [])
                        middleware = getattr(method, "_mcp_middleware", [])
                        interceptors = getattr(method, "_mcp_interceptors", [])
                        pipes = getattr(method, "_mcp_pipes", [])
                        filters = getattr(method, "_mcp_filters", [])

                        result = await run_pipeline(
                            handler=method,
                            handler_instance=instance,
                            args=(input, task_ctx),
                            kwargs={},
                            context=task_ctx,
                            guards=guards,
                            middleware=middleware,
                            interceptors=interceptors,
                            pipes=pipes,
                            filters=filters,
                            param_name="input",
                            param_type=input_model
                        )
                        if isinstance(result, BaseModel):
                            result_dump = result.model_dump()
                        else:
                            result_dump = result
                        
                        import mcp.types as types
                        import json
                        if isinstance(result_dump, types.CallToolResult):
                            final_result = result_dump
                        elif isinstance(result_dump, dict):
                            if "content" in result_dump and "isError" in result_dump:
                                final_result = types.CallToolResult(**result_dump)
                            else:
                                final_result = types.CallToolResult(
                                    content=[types.TextContent(type="text", text=json.dumps(result_dump, indent=2))],
                                    structuredContent=result_dump,
                                    isError=False
                                )
                        else:
                            final_result = types.CallToolResult(
                                content=[types.TextContent(type="text", text=str(result_dump))],
                                isError=False
                            )
                        TaskRegistry.complete_task(task_id, final_result)
                    except Exception as e:
                        TaskRegistry.fail_task(task_id, e)

                import asyncio
                asyncio.create_task(background_execution())
                import datetime
                import mcp.types as types
                now = datetime.datetime.now(datetime.timezone.utc)
                return types.CreateTaskResult(
                    task=types.Task(
                        taskId=task_id,
                        status="working",
                        statusMessage="Task started",
                        createdAt=now,
                        lastUpdatedAt=now,
                        ttl=ttl,
                        pollInterval=5
                    )
                )

            # Initialize ExecutionContext
            ctx = ExecutionContext(
                request_id=str(uuid.uuid4()),
                tool_name=tool_config.name,
                metadata={"input": input}
            )

            # Retrieve pipeline decorators
            guards = getattr(method, "_mcp_guards", [])
            middleware = getattr(method, "_mcp_middleware", [])
            interceptors = getattr(method, "_mcp_interceptors", [])
            pipes = getattr(method, "_mcp_pipes", [])
            filters = getattr(method, "_mcp_filters", [])

            # Run through pipeline runner
            result = await run_pipeline(
                handler=method,
                handler_instance=instance,
                args=(input, ctx),
                kwargs={},
                context=ctx,
                guards=guards,
                middleware=middleware,
                interceptors=interceptors,
                pipes=pipes,
                filters=filters,
                param_name="input",
                param_type=input_model
            )

            if isinstance(result, BaseModel):
                return result.model_dump()
            return result

        # Register metadata
        meta = {
            "is_initial": tool_config.is_initial,
            "visibility": tool_config.visibility,
            "task_support": tool_config.task_support,
            **(tool_config.metadata or {})
        }
        widget_route = getattr(method, "_mcp_widget", None)
        if widget_route:
            meta["ui/template"] = widget_route
            meta["ui"] = {"resourceUri": widget_route}
            meta["openai/outputTemplate"] = widget_route

        if tool_config.invocation:
            meta["openai/toolInvocation/invoking"] = tool_config.invocation.invoking
            meta["openai/toolInvocation/invoked"] = tool_config.invocation.invoked
        if tool_config.examples:
            meta["examples"] = {
                "input": tool_config.examples.input,
                "output": tool_config.examples.output,
                "description": tool_config.examples.description
            }

        # Add to FastMCP
        self.mcp_server.add_tool(
            tool_wrapper,
            name=tool_config.name,
            title=tool_config.title,
            description=tool_config.description,
            meta=meta
        )

    def _register_resource(self, instance: Any, method: Callable, resource_config: ResourceConfig) -> None:
        import re
        # Find all template variables in braces, e.g. {result_id}
        param_names = re.findall(r"\{([^}]+)\}", resource_config.uri)
        sig_str = ", ".join(param_names)

        exec_locals = {}
        exec_globals = {
            "run_pipeline": run_pipeline,
            "method": method,
            "instance": instance,
            "ExecutionContext": ExecutionContext,
            "uuid": uuid,
        }

        # Build dynamic wrapper signature to expose correct parameters to clients/studios
        code = f"""
async def resource_wrapper({sig_str}):
    import uuid
    args_dict = {{
        {", ".join(f"'{name}': {name}" for name in param_names)}
    }}
    ctx = ExecutionContext(
        request_id=str(uuid.uuid4()),
        metadata=args_dict
    )

    guards = getattr(method, "_mcp_guards", [])
    middleware = getattr(method, "_mcp_middleware", [])
    interceptors = getattr(method, "_mcp_interceptors", [])
    pipes = getattr(method, "_mcp_pipes", [])
    filters = getattr(method, "_mcp_filters", [])

    result = await run_pipeline(
        handler=method,
        handler_instance=instance,
        args=(),
        kwargs={{**args_dict, "context": ctx}},
        context=ctx,
        guards=guards,
        middleware=middleware,
        interceptors=interceptors,
        pipes=pipes,
        filters=filters
    )

    # Support Discriminated Union formats for return (Section 1.2)
    if isinstance(result, dict) and "type" in result and "data" in result:
        return result["data"]
    return result
"""
        exec(code, exec_globals, exec_locals)
        resource_wrapper = exec_locals["resource_wrapper"]

        # Register resource decorator on FastMCP
        resource_decorator = self.mcp_server.resource(
            resource_config.uri,
            name=resource_config.name,
            title=resource_config.title,
            description=resource_config.description,
            mime_type=resource_config.mime_type
        )
        resource_decorator(resource_wrapper)

    def _register_prompt(self, instance: Any, method: Callable, prompt_config: PromptConfig) -> None:
        arg_names = [arg.name for arg in prompt_config.arguments]
        sig_parts = []
        for arg in prompt_config.arguments:
            sig_part = f"{arg.name}: str"
            if not arg.required:
                sig_part += " = None"
            sig_parts.append(sig_part)
        sig_str = ", ".join(sig_parts)

        exec_locals = {}
        exec_globals = {
            "run_pipeline": run_pipeline,
            "method": method,
            "instance": instance,
            "ExecutionContext": ExecutionContext,
            "uuid": uuid,
            "McpPromptMessage": McpPromptMessage,
            "TextContent": TextContent,
        }

        # Build dynamic wrapper signature to expose correct parameters to clients/studios
        code = f"""
async def prompt_wrapper({sig_str}):
    args_dict = {{
        {", ".join(f"'{name}': {name}" for name in arg_names)}
    }}
    ctx = ExecutionContext(
        request_id=str(uuid.uuid4()),
        metadata=args_dict,
    )
    
    guards = getattr(method, "_mcp_guards", [])
    middleware = getattr(method, "_mcp_middleware", [])
    interceptors = getattr(method, "_mcp_interceptors", [])
    pipes = getattr(method, "_mcp_pipes", [])
    filters = getattr(method, "_mcp_filters", [])

    raw_messages = await run_pipeline(
        handler=method,
        handler_instance=instance,
        args=(args_dict, ctx),
        kwargs={{}},
        context=ctx,
        guards=guards,
        middleware=middleware,
        interceptors=interceptors,
        pipes=pipes,
        filters=filters
    )
    
    mcp_messages = []
    from collections.abc import Iterable
    if not isinstance(raw_messages, Iterable) or isinstance(raw_messages, (dict, str, bytes)):
        raw_list = [raw_messages]
    else:
        raw_list = list(raw_messages)
        
    for msg in raw_list:
        role = msg.role if hasattr(msg, "role") else msg.get("role")
        content = msg.content if hasattr(msg, "content") else msg.get("content")
        mcp_messages.append({{
            "role": role,
            "content": {{
                "type": "text",
                "text": content
            }}
        }})
    return mcp_messages
"""
        exec(code, exec_globals, exec_locals)
        prompt_wrapper = exec_locals["prompt_wrapper"]

        # Register prompt decorator on FastMCP
        prompt_decorator = self.mcp_server.prompt(
            name=prompt_config.name,
            description=prompt_config.description
        )
        prompt_decorator(prompt_wrapper)

    def get_combined_app(self) -> Any:
        from starlette.applications import Starlette
        from starlette.routing import Route
        combined_app = Starlette()
        
        # Add custom Starlette routes registered via custom_route
        try:
            http_app = self.mcp_server.streamable_http_app()
            for route in http_app.routes:
                combined_app.routes.append(route)
        except Exception:
            pass

        try:
            sse_app = self.mcp_server.sse_app()
            for route in sse_app.routes:
                if not any(r.path == route.path for r in combined_app.routes):
                    combined_app.routes.append(route)
                if route.path == "/messages":
                    if not any(r.path == "/mcp/messages" for r in combined_app.routes):
                        combined_app.routes.append(Route("/mcp/messages", endpoint=route.endpoint, methods=getattr(route, "methods", None)))
        except Exception:
            pass
            
        return combined_app

    async def start(self) -> None:
        """Starts the MCP application based on transport configurations."""
        # Start background OAuth discovery server if OAuthService is resolved
        try:
            from nitrostack.auth.oauth import OAuthService
            oauth_service = DIContainer.get_instance().resolve(OAuthService)
            oauth_service.start_discovery_server()
        except Exception:
            pass

        transport = os.environ.get("MCP_TRANSPORT_TYPE") or getattr(self.server_config, "transport_type", None)
        node_env = os.environ.get("NODE_ENV", "development")
        port = int(os.environ.get("PORT") or os.environ.get("MCP_SERVER_PORT") or 8000)

        # Stdio mode and Dual mode
        if transport == "http":
            # Run combined HTTP Server
            import uvicorn
            app = self.get_combined_app()
            config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
            server = uvicorn.Server(config)
            await server.serve()
        elif transport == "dual" or (node_env == "production" and not transport):
            # dual mode: stdio + HTTP
            import threading
            def run_http():
                import asyncio
                import uvicorn
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                app = self.get_combined_app()
                config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
                server = uvicorn.Server(config)
                loop.run_until_complete(server.serve())

            http_thread = threading.Thread(target=run_http, daemon=True)
            http_thread.start()
            
            # Run stdio in the main thread
            from nitrostack.transports.stdio import safe_stdio_transport
            with safe_stdio_transport():
                await self.mcp_server.run_stdio_async()
        else:
            # Default Stdio
            from nitrostack.transports.stdio import safe_stdio_transport
            with safe_stdio_transport():
                await self.mcp_server.run_stdio_async()



class McpApplicationFactory:
    @classmethod
    async def create(cls, app_class: Type) -> McpApplication:
        """Bootstraps and instantiates the McpApplication class."""
        return McpApplication(app_class)
