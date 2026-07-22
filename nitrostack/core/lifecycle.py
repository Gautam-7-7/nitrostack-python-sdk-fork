import inspect
import asyncio
from typing import List, Any, Optional

async def trigger_lifecycle_hook(
    instances: List[Any],
    hook_name: str,
    safe: bool = False,
    logger: Optional[Any] = None,
    *args,
    **kwargs
) -> None:
    """
    Triggers a lifecycle hook asynchronously across all deduplicated instances
    that implement the matching method.
    """
    # Deduplicate instances
    unique_instances = []
    seen = set()
    for inst in instances:
        try:
            inst_hash = hash(inst)
            if inst_hash not in seen:
                seen.add(inst_hash)
                unique_instances.append(inst)
        except TypeError:
            inst_id = id(inst)
            if inst_id not in seen:
                seen.add(inst_id)
                unique_instances.append(inst)

    for inst in unique_instances:
        if not inst:
            continue
        hook = getattr(inst, hook_name, None)
        if hook and callable(hook):
            try:
                # Inspect signature to avoid TypeError from unexpected keyword arguments
                sig = inspect.signature(hook)
                has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                
                call_kwargs = {}
                if has_var_keyword:
                    call_kwargs = kwargs
                else:
                    for p_name in sig.parameters:
                        if p_name in kwargs:
                            call_kwargs[p_name] = kwargs[p_name]

                if inspect.iscoroutinefunction(hook):
                    await hook(*args, **call_kwargs)
                else:
                    await asyncio.to_thread(hook, *args, **call_kwargs)
            except Exception as e:
                if not safe:
                    raise e
                if logger:
                    logger.error(f"Failed to execute lifecycle hook '{hook_name}' on {inst.__class__.__name__}: {e}")
