import os
import sys
import uuid
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Set, Type, Optional, Union
from mcp.server.fastmcp import FastMCP
from mcp.types import PromptMessage as McpPromptMessage, TextContent
from pydantic import BaseModel, create_model

from nitrostack.core.context import ExecutionContext
from nitrostack.core.decorators import ToolConfig, ResourceConfig, PromptConfig
from nitrostack.core.di import DIContainer
from nitrostack.core.pipeline import run_pipeline
from nitrostack.core.additional_decorators import HealthCheckRegistry
from nitrostack.events.event_emitter import EventEmitter

from nitrostack.core.tool import Tool
from nitrostack.core.resource import Resource
from nitrostack.core.prompt import Prompt

# Monkeypatch FastMCP.call_tool to support returning CreateTaskResult without conversion
_original_fastmcp_call_tool = FastMCP.call_tool

def validate_message_format(msg: Any) -> dict:
    from nitrostack.core.errors import ValidationError
    if not msg:
        raise ValidationError("Invalid prompt message format: message cannot be empty")
    role = msg.role if hasattr(msg, "role") else msg.get("role") if isinstance(msg, dict) else None
    content = msg.content if hasattr(msg, "content") else msg.get("content") if isinstance(msg, dict) else None
    if not role or role not in ("user", "assistant", "system"):
        raise ValidationError(f"Invalid prompt message role: '{role}'. Must be 'user', 'assistant', or 'system'")
    if not isinstance(content, str):
        raise ValidationError("Invalid prompt message content: content must be a string")
    return {"role": role, "content": content}

def handle_tool_error(e: Exception) -> Any:
    import mcp.types as types
    import pydantic
    from nitrostack.core.errors import ValidationError

    # 1. Pydantic v2 ValidationError
    if isinstance(e, pydantic.ValidationError):
        errors_details = []
        for err in e.errors():
            loc = " -> ".join(str(l) for l in err.get("loc", []))
            msg = err.get("msg", "Unknown error")
            errors_details.append(f"Field '{loc}': {msg}")
        err_msg = "Validation failed:\n" + "\n".join(errors_details)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=err_msg)],
            isError=True
        )

    # 2. SDK custom ValidationError
    if isinstance(e, ValidationError):
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Validation Error: {str(e)}")],
            isError=True
        )

    # 3. PermissionError / Guard auth failures
    if isinstance(e, PermissionError) or "Access denied" in str(e):
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Access Denied: {str(e)}")],
            isError=True
        )

    # 4. Fallback for other exceptions
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=f"Error: {str(e)}")],
        isError=True
    )


async def _custom_fastmcp_call_tool(self, name: str, arguments: dict[str, Any]):
    t = self._tool_manager.get_tool(name)
    if not t:
        return await _original_fastmcp_call_tool(self, name, arguments)
    context = self.get_context()
    try:
        result = await self._tool_manager.call_tool(
            name, arguments, context=context, convert_result=False
        )
        import mcp.types as types
        if isinstance(result, types.CreateTaskResult):
            return result
        return t.fn_metadata.convert_result(result)
    except Exception as e:
        orig_err = e
        if hasattr(e, "__cause__") and e.__cause__:
            orig_err = e.__cause__
        return handle_tool_error(orig_err)

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
        self.tools: Dict[str, Tool] = {}
        self.resources: Dict[str, Resource] = {}
        self.prompts: Dict[str, Prompt] = {}
        self.mcp_server: Optional[FastMCP] = None
        self._startup_hooks_run = False
        self._shutdown_hooks_run = False
        self._active_http_sessions = {}
        self._bootstrap()

    async def _run_startup_hooks(self) -> None:
        if not self._startup_hooks_run:
            self._startup_hooks_run = True
            instances = list(DIContainer.get_instance()._instances.values())
            from nitrostack.core.lifecycle import trigger_lifecycle_hook
            await trigger_lifecycle_hook(instances, "on_module_init")
            await trigger_lifecycle_hook(instances, "on_application_bootstrap")

    async def _run_shutdown_hooks(self, signal: Optional[str] = None) -> None:
        if not self._shutdown_hooks_run:
            self._shutdown_hooks_run = True
            instances = list(DIContainer.get_instance()._instances.values())
            from nitrostack.core.lifecycle import trigger_lifecycle_hook
            await trigger_lifecycle_hook(instances, "on_module_destroy", safe=True)
            await trigger_lifecycle_hook(instances, "before_application_shutdown", safe=True, signal=signal)
            await trigger_lifecycle_hook(instances, "on_application_shutdown", safe=True, signal=signal)

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
        from nitrostack.core.builders import build_tools, build_resources, build_prompts
        for token, instance in list(container._instances.items()):
            # Build and register tools
            for t in build_tools(instance):
                self.tool(t)
                if t.is_initial:
                    initial_tools.append((instance, t.handler, t))
            
            # Build and register resources
            for r in build_resources(instance):
                self.resource(r)
                
            # Build and register prompts
            for p in build_prompts(instance):
                self.prompt(p)

            # Bind Health Checks and Events
            for name, member in inspect.getmembers(instance):
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

        # 4b. Register Built-in Widget Examples Resource if widget-manifest.json exists
        widget_manifest_path = os.path.join(os.getcwd(), "src", "widgets", "widget-manifest.json")
        if os.path.exists(widget_manifest_path):
            @self.mcp_server.resource("widget://examples", name="Widget Examples", description="Provides metadata and examples for all registered UI widgets", mime_type="application/json")
            def widget_examples_resource() -> str:
                try:
                    with open(widget_manifest_path, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception as e:
                    return f'{{"error": "Failed to read manifest: {str(e)}"}}'

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

        import mcp.types as types
        from nitrostack.core.task import TaskRegistry

        async def handle_list_tasks(req):
            cursor = getattr(req.params, "cursor", None) if req and hasattr(req, "params") else None
            limit = getattr(req.params, "limit", 50) if req and hasattr(req, "params") else 50
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
                for t in TaskRegistry.list_tasks(cursor=cursor, limit=limit)
            ]
            return types.ListTasksResult(tasks=tasks_list, nextCursor=TaskRegistry._next_cursor)

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
                if isinstance(t.error, types.CallToolResult):
                    return t.error
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
                from nitrostack.core.app_mode import is_openai_mode, is_mcp_app_mode
                tools_list = []
                if hasattr(res, "root") and hasattr(res.root, "tools"):
                    tools_list = res.root.tools
                elif hasattr(res, "tools"):
                    tools_list = res.tools
                for tool in tools_list:
                    if tool.meta is None:
                        tool.meta = {}
                    if is_openai_mode():
                        tool.meta["openai/type"] = "function"
                        tool.meta["openai/function"] = {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.inputSchema
                        }
                    if is_mcp_app_mode():
                        tool.meta["_meta"] = {
                            "ui": {
                                "title": tool.title or tool.name,
                                "description": tool.description
                            }
                        }
                        local_tool = self.tools.get(tool.name)
                        if local_tool and local_tool.widget:
                            route = local_tool.widget.get("route")
                            tool.meta["_meta"]["ui"]["resourceUri"] = route
                            tool.meta["openai/outputTemplate"] = route
                return res
            low_level_server.request_handlers[types.ListToolsRequest] = custom_list_tools_handler

        # 7. Register a notification handler for initialized to auto-call @initial_tool annotated tools
        async def handle_initialized(notification: types.InitializedNotification):
            for inst, handler, t in initial_tools:
                try:
                    input_model = get_pydantic_model(t.input_schema)
                    try:
                        input_inst = input_model()
                    except Exception:
                        input_inst = None
                    
                    ctx = ExecutionContext(
                        request_id=f"initial-tool-{uuid.uuid4().hex[:8]}",
                        tool_name=t.name,
                        metadata={}
                    )
                    
                    await t.execute(input_inst, ctx)
                except Exception as e:
                    import sys
                    print(f"Error executing initial tool '{t.name}': {e}", file=sys.stderr)

        low_level_server.notification_handlers[types.InitializedNotification] = handle_initialized

    def _resolve_modules(self, module_class: Type, resolved_modules: Set[Type]) -> None:
        if module_class in resolved_modules:
            return
        resolved_modules.add(module_class)

        mod_config = getattr(module_class, "_mcp_module_config", None)
        if mod_config:
            for imp in mod_config.imports:
                self._resolve_modules(imp, resolved_modules)

    def tool(self, tool: Tool) -> "McpApplication":
        self.tools[tool.name] = tool
        if tool.has_component():
            comp = tool.get_component()
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(comp.compile())
                else:
                    loop.run_until_complete(comp.compile())
            except Exception:
                pass
                
            from nitrostack.core.app_mode import get_widget_mime_type
            from nitrostack.core.resource import Resource
            
            async def serve_widget(context):
                import os
                if os.environ.get("NODE_ENV") in ("production", "prod"):
                    possible_paths = [
                        os.path.join(os.getcwd(), "src", "widgets", "out", f"{comp.id}.html"),
                        os.path.join(os.getcwd(), "dist", "widgets", "out", f"{comp.id}.html"),
                        os.path.join(os.getcwd(), "widgets", "out", f"{comp.id}.html")
                    ]
                    if comp.id.startswith("next-"):
                        possible_paths.append(os.path.join(os.getcwd(), "src", "widgets", "out", f"{comp.id[5:]}.html"))
                    for p in possible_paths:
                        if os.path.exists(p):
                            with open(p, "r", encoding="utf-8") as f:
                                return f.read()
                return comp.get_bundle()

            widget_resource = Resource(
                uri=comp.get_resource_uri(),
                name=comp.name,
                handler=serve_widget,
                description=comp.description or f"UI component for {comp.name}",
                mime_type=get_widget_mime_type()
            )
            widget_resource.attach_widget_read_meta(comp.get_resource_metadata())
            self.resource(widget_resource)

        input_model = get_pydantic_model(tool.input_schema)

        async def tool_wrapper(input: input_model) -> Any:
            task_metadata = None
            try:
                from mcp.server.lowlevel.server import request_ctx
                req = request_ctx.get().request
                task_metadata = getattr(req.params, "task", None) if req and hasattr(req, "params") else None
            except Exception:
                pass
            
            is_task = (task_metadata is not None) or (tool.task_support == "required")
            if tool.task_support == "forbidden":
                is_task = False

            if is_task:
                task_id = f"task_{uuid.uuid4().hex[:12]}"
                ttl = task_metadata.ttl if task_metadata else 300
                from nitrostack.core.task import TaskRegistry
                TaskRegistry.create_task(task_id, ttl=ttl)

                async def background_execution():
                    task_ctx = ExecutionContext(
                        request_id=str(uuid.uuid4()),
                        tool_name=tool.name,
                        metadata={"input": input}
                    )
                    from nitrostack.core.context import TaskContext
                    task_ctx.task = TaskContext(task_id)
                    try:
                        result = await tool.execute(input, task_ctx)
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
                            elif result_dump.get("error") is True:
                                final_result = types.CallToolResult(
                                    content=[types.TextContent(type="text", text=str(result_dump.get("message") or result_dump.get("error")))],
                                    isError=True
                                )
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
                        if tool.has_component():
                            comp = tool.get_component()
                            final_result.structuredContent = await comp.transform_data(result, task_ctx)
                            final_result._meta = await comp.get_widget_meta(result, task_ctx) or {}
                        
                        TaskRegistry.complete_task(task_id, final_result)
                    except (asyncio.CancelledError, TaskCancelledError) as e:
                        TaskRegistry.cancel_task(task_id)
                        if isinstance(e, asyncio.CancelledError):
                            raise
                    except Exception as e:
                        translated_error = handle_tool_error(e)
                        TaskRegistry.fail_task(task_id, translated_error)

                import asyncio
                from nitrostack.core.context import TaskCancelledError
                task = asyncio.create_task(background_execution())
                entry = TaskRegistry.get_task(task_id)
                if entry:
                    entry.asyncio_task = task
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

            ctx = ExecutionContext(
                request_id=str(uuid.uuid4()),
                tool_name=tool.name,
                metadata={"input": input}
            )

            try:
                result = await tool.execute(input, ctx)
                if isinstance(result, BaseModel):
                    result_dump = result.model_dump()
                else:
                    result_dump = result

                import mcp.types as types
                from nitrostack.core.app_mode import is_mcp_app_mode
                if isinstance(result_dump, types.CallToolResult):
                    if tool.has_component():
                        comp = tool.get_component()
                        result_dump.structuredContent = await comp.transform_data(result, ctx)
                        result_dump._meta = await comp.get_widget_meta(result, ctx) or {}
                    return result_dump
                elif isinstance(result_dump, dict):
                    if "content" in result_dump and "isError" in result_dump:
                        res_obj = types.CallToolResult(**result_dump)
                    elif result_dump.get("error") is True:
                        err_msg = result_dump.get("message") or result_dump.get("error")
                        res_obj = types.CallToolResult(
                            content=[types.TextContent(type="text", text=str(err_msg))],
                            isError=True
                        )
                    else:
                        res_obj = result_dump
                    
                    if tool.has_component():
                        comp = tool.get_component()
                        if isinstance(res_obj, types.CallToolResult):
                            res_obj.structuredContent = await comp.transform_data(result, ctx)
                            res_obj._meta = await comp.get_widget_meta(result, ctx) or {}
                        elif isinstance(res_obj, dict):
                            res_obj["structuredContent"] = await comp.transform_data(result, ctx)
                            res_obj["_meta"] = await comp.get_widget_meta(result, ctx) or {}
                    return res_obj
                else:
                    if tool.has_component():
                        comp = tool.get_component()
                        structured_content = await comp.transform_data(result, ctx)
                        meta_content = await comp.get_widget_meta(result, ctx) or {}
                        import json
                        return types.CallToolResult(
                            content=[types.TextContent(type="text", text=json.dumps(result_dump) if isinstance(result_dump, (dict, list)) else str(result_dump))],
                            structuredContent=structured_content,
                            _meta=meta_content,
                            isError=False
                        )
                    return result_dump
            except Exception as e:
                return handle_tool_error(e)

        meta = {
            "is_initial": tool.is_initial,
            "visibility": tool.visibility,
            "task_support": tool.task_support,
        }
        if hasattr(tool, "metadata") and tool.metadata:
            meta.update(tool.metadata)
        if tool.widget:
            meta["ui/template"] = tool.widget.get("route")
            meta["ui"] = {"resourceUri": tool.widget.get("route")}
            meta["openai/outputTemplate"] = tool.widget.get("route")

        if tool.invocation:
            meta["openai/toolInvocation/invoking"] = tool.invocation.invoking
            meta["openai/toolInvocation/invoked"] = tool.invocation.invoked
        if tool.examples:
            meta["examples"] = {
                "input": tool.examples.input,
                "output": tool.examples.output,
                "description": tool.examples.description
            }

        self.mcp_server.add_tool(
            tool_wrapper,
            name=tool.name,
            title=tool.title,
            description=tool.description,
            meta=meta
        )
        return self

    def resource(self, resource: Resource) -> "McpApplication":
        self.resources[resource.uri] = resource
        import re
        param_names = re.findall(r"\{([^}]+)\}", resource.uri)
        sig_str = ", ".join(param_names)

        exec_locals = {}
        exec_globals = {
            "resource": resource,
            "ExecutionContext": ExecutionContext,
            "uuid": uuid,
        }

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
    result = await resource.fetch(ctx, resource.uri)
    if isinstance(result, dict) and "type" in result and "data" in result:
        return result["data"]
    return result
"""
        exec(code, exec_globals, exec_locals)
        resource_wrapper = exec_locals["resource_wrapper"]

        resource_decorator = self.mcp_server.resource(
            resource.uri,
            name=resource.name,
            title=resource.title,
            description=resource.description,
            mime_type=resource.mime_type
        )
        resource_decorator(resource_wrapper)
        return self

    def prompt(self, prompt: Prompt) -> "McpApplication":
        self.prompts[prompt.name] = prompt
        
        arg_names = [arg.name for arg in prompt.arguments]
        sig_parts = []
        for arg in prompt.arguments:
            sig_part = f"{arg.name}: str"
            if not arg.required:
                sig_part += " = None"
            sig_parts.append(sig_part)
        sig_str = ", ".join(sig_parts)

        exec_locals = {}
        exec_globals = {
            "prompt": prompt,
            "ExecutionContext": ExecutionContext,
            "uuid": uuid,
            "McpPromptMessage": McpPromptMessage,
            "TextContent": TextContent,
            "validate_message_format": validate_message_format,
        }

        code = f"""
async def prompt_wrapper({sig_str}):
    args_dict = {{
        {", ".join(f"'{name}': {name}" for name in arg_names)}
    }}
    ctx = ExecutionContext(
        request_id=str(uuid.uuid4()),
        metadata=args_dict,
    )
    raw_messages = await prompt.execute(args_dict, ctx)
    
    mcp_messages = []
    from collections.abc import Iterable
    if not isinstance(raw_messages, Iterable) or isinstance(raw_messages, (dict, str, bytes)):
        raw_list = [raw_messages]
    else:
        raw_list = list(raw_messages)
        
    for msg in raw_list:
        validated = validate_message_format(msg)
        mcp_messages.append({{
            "role": validated["role"],
            "content": {{
                "type": "text",
                "text": validated["content"]
            }}
        }})
    return mcp_messages
"""
        exec(code, exec_globals, exec_locals)
        prompt_wrapper = exec_locals["prompt_wrapper"]

        prompt_decorator = self.mcp_server.prompt(
            name=prompt.name,
            description=prompt.description
        )
        prompt_decorator(prompt_wrapper)
        return self

    def get_combined_app(self) -> Any:
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.requests import Request
        from starlette.responses import Response
        from mcp.server.sse import SseServerTransport
        from mcp.server import Server
        from contextlib import asynccontextmanager
        from starlette.middleware.base import BaseHTTPMiddleware
        import time

        @asynccontextmanager
        async def lifespan_context(app):
            await self._run_startup_hooks()
            yield
            await self._run_shutdown_hooks()

        combined_app = Starlette(lifespan=lifespan_context)
        
        # Add custom Starlette routes registered via custom_route
        try:
            http_app = self.mcp_server.streamable_http_app()
            for route in http_app.routes:
                combined_app.routes.append(route)
        except Exception:
            pass

        if not hasattr(self, "_legacy_sse_transports"):
            self._legacy_sse_transports = {}

        max_sessions = int(os.environ.get("NITROSTACK_MAX_SESSIONS", "1000"))
        session_timeout = int(os.environ.get("NITROSTACK_SESSION_TIMEOUT", "1800"))

        class SessionLimitMiddleware(BaseHTTPMiddleware):
            def __init__(self, app, max_sessions: int, session_timeout: int, active_sse: dict, active_http: dict):
                super().__init__(app)
                self.max_sessions = max_sessions
                self.session_timeout = session_timeout
                self.active_sse = active_sse
                self.active_http = active_http

            async def dispatch(self, request, call_next):
                now = time.time()
                expired = [sid for sid, t in list(self.active_http.items()) if now - t > self.session_timeout]
                for sid in expired:
                    self.active_http.pop(sid, None)

                session_id = request.headers.get("mcp-session-id") or request.query_params.get("session_id")
                path = request.url.path
                method = request.method

                is_new_session = False
                if path == "/sse" and method == "GET" and not session_id:
                    is_new_session = True
                elif path == "/mcp" and method == "POST" and not session_id:
                    is_new_session = True

                if is_new_session:
                    total_sessions = len(self.active_sse) + len(self.active_http)
                    if total_sessions >= self.max_sessions:
                        return Response("Too Many Sessions", status_code=429)

                if session_id:
                    if path == "/sse" or path == "/messages" or path == "/mcp/messages":
                        pass
                    else:
                        self.active_http[session_id] = now

                response = await call_next(request)
                resp_session_id = response.headers.get("mcp-session-id")
                if resp_session_id:
                    self.active_http[resp_session_id] = time.time()

                return response

        combined_app.add_middleware(
            SessionLimitMiddleware,
            max_sessions=max_sessions,
            session_timeout=session_timeout,
            active_sse=self._legacy_sse_transports,
            active_http=self._active_http_sessions
        )

        normalized_message_endpoint = "/mcp/messages"

        async def sse_asgi_app(scope, receive, send):
            session_server = Server(
                name=self.mcp_server._mcp_server.name,
                version=self.mcp_server._mcp_server.version
            )
            session_server.request_handlers = dict(self.mcp_server._mcp_server.request_handlers)
            session_server.notification_handlers = dict(self.mcp_server._mcp_server.notification_handlers)
            session_server.get_capabilities = self.mcp_server._mcp_server.get_capabilities

            transport = SseServerTransport(normalized_message_endpoint)
            
            async with transport.connect_sse(scope, receive, send) as streams:
                session_id = None
                if transport._read_stream_writers:
                    session_id = list(transport._read_stream_writers.keys())[0]
                
                if session_id:
                    self._legacy_sse_transports[session_id.hex] = transport
                
                try:
                    await session_server.run(
                        streams[0],
                        streams[1],
                        session_server.create_initialization_options()
                    )
                finally:
                    if session_id:
                        self._legacy_sse_transports.pop(session_id.hex, None)
            return Response()

        async def messages_asgi_app(scope, receive, send):
            request = Request(scope, receive)
            session_id_param = request.query_params.get("session_id")
            if not session_id_param:
                response = Response("session_id is required", status_code=400)
                return await response(scope, receive, send)
            
            transport = self._legacy_sse_transports.get(session_id_param)
            if not transport:
                response = Response("Could not find session", status_code=404)
                return await response(scope, receive, send)
            
            return await transport.handle_post_message(scope, receive, send)

        combined_app.routes.append(Route("/sse", endpoint=sse_asgi_app, methods=["GET"]))
        combined_app.routes.append(Route("/messages", endpoint=messages_asgi_app, methods=["POST"]))
        combined_app.routes.append(Route("/mcp/messages", endpoint=messages_asgi_app, methods=["POST"]))
            
        return combined_app

    async def start(self) -> None:
        """Starts the MCP application based on transport configurations."""
        await self._run_startup_hooks()

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

        try:
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
        finally:
            await self._run_shutdown_hooks()



class McpApplicationFactory:
    @classmethod
    async def create(cls, app_class: Type) -> McpApplication:
        """Bootstraps and instantiates the McpApplication class."""
        return McpApplication(app_class)
