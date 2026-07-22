import datetime
import asyncio
from typing import Dict, List, Any, Optional, Callable
from nitrostack.core.errors import TaskNotFoundError, TaskAlreadyTerminalError

class AbortSignal:
    def __init__(self):
        self.aborted = False
        self._listeners: List[Callable] = []

    def add_event_listener(self, event: str, listener: Callable) -> None:
        if event == "abort":
            self._listeners.append(listener)
            if self.aborted:
                try:
                    listener()
                except Exception:
                    pass

    def addEventListener(self, event: str, listener: Callable) -> None:
        self.add_event_listener(event, listener)

class AbortController:
    def __init__(self):
        self.signal = AbortSignal()

    def abort(self) -> None:
        if not self.signal.aborted:
            self.signal.aborted = True
            for listener in list(self.signal._listeners):
                try:
                    listener()
                except Exception:
                    pass

class TaskEntry:
    def __init__(self, task_id: str, ttl: Optional[int] = None):
        self.task_id = task_id
        self.status: str = "working"
        self.status_message: str = "Task started"
        self.created_at = datetime.datetime.now(datetime.timezone.utc)
        self.last_updated_at = self.created_at
        self.ttl = ttl if ttl is not None else 300
        self.poll_interval = 5
        self.result: Any = None
        self.error: Any = None
        self.is_cancelled: bool = False
        self.done_event = asyncio.Event()
        self.asyncio_task: Optional[asyncio.Task] = None
        self.abort_controller = AbortController()

def is_terminal_status(status: str) -> bool:
    return status in ("completed", "failed", "cancelled")

class TaskRegistry:
    _tasks: Dict[str, TaskEntry] = {}
    _next_cursor: Optional[str] = None
    
    @classmethod
    def create_task(cls, task_id: str, ttl: Optional[int] = None) -> TaskEntry:
        entry = TaskEntry(task_id, ttl)
        cls._tasks[task_id] = entry
        start_cleanup_loop()
        return entry

    @classmethod
    def get_task(cls, task_id: str) -> Optional[TaskEntry]:
        return cls._tasks.get(task_id)

    @classmethod
    def list_tasks(cls, cursor: Optional[str] = None, limit: int = 50) -> List[TaskEntry]:
        all_tasks = sorted(cls._tasks.values(), key=lambda t: t.created_at, reverse=True)
        start_idx = 0
        if cursor:
            found = False
            for idx, t in enumerate(all_tasks):
                if t.task_id == cursor:
                    start_idx = idx + 1
                    found = True
                    break
            if not found:
                raise TaskNotFoundError(f"Task with ID {cursor} not found")
        page = all_tasks[start_idx:start_idx + limit]
        cls._next_cursor = page[-1].task_id if len(page) == limit and (start_idx + limit) < len(all_tasks) else None
        return page

    @classmethod
    def update_progress(cls, task_id: str, message: str) -> None:
        entry = cls.get_task(task_id)
        if not entry:
            raise TaskNotFoundError(f"Task {task_id} not found")
        if is_terminal_status(entry.status):
            raise TaskAlreadyTerminalError(f"Task {task_id} is in terminal state '{entry.status}'")
        entry.status_message = message
        entry.last_updated_at = datetime.datetime.now(datetime.timezone.utc)

    @classmethod
    def cancel_task(cls, task_id: str) -> None:
        entry = cls.get_task(task_id)
        if not entry:
            raise TaskNotFoundError(f"Task {task_id} not found")
        if is_terminal_status(entry.status):
            raise TaskAlreadyTerminalError(f"Task {task_id} is in terminal state '{entry.status}'")
        
        entry.is_cancelled = True
        entry.status = "cancelled"
        entry.status_message = "Task cancelled by client"
        entry.last_updated_at = datetime.datetime.now(datetime.timezone.utc)
        entry.abort_controller.abort()
        entry.done_event.set()
        if entry.asyncio_task and not entry.asyncio_task.done():
            entry.asyncio_task.cancel()

    @classmethod
    def is_task_cancelled(cls, task_id: str) -> bool:
        entry = cls.get_task(task_id)
        return entry.is_cancelled if entry else False

    @classmethod
    def complete_task(cls, task_id: str, result: Any) -> None:
        entry = cls.get_task(task_id)
        if not entry:
            raise TaskNotFoundError(f"Task {task_id} not found")
        if is_terminal_status(entry.status):
            raise TaskAlreadyTerminalError(f"Task {task_id} is in terminal state '{entry.status}'")
        
        entry.status = "completed"
        entry.status_message = "Task completed successfully"
        entry.result = result
        entry.last_updated_at = datetime.datetime.now(datetime.timezone.utc)
        entry.done_event.set()

    @classmethod
    def fail_task(cls, task_id: str, error: Any) -> None:
        entry = cls.get_task(task_id)
        if not entry:
            raise TaskNotFoundError(f"Task {task_id} not found")
        if is_terminal_status(entry.status):
            raise TaskAlreadyTerminalError(f"Task {task_id} is in terminal state '{entry.status}'")
        
        entry.status = "failed"
        entry.status_message = f"Task failed: {error}"
        entry.error = error
        entry.last_updated_at = datetime.datetime.now(datetime.timezone.utc)
        entry.done_event.set()

async def cleanup_expired_tasks_loop():
    while True:
        try:
            await asyncio.sleep(30)
            now = datetime.datetime.now(datetime.timezone.utc)
            to_delete = []
            for task_id, entry in list(TaskRegistry._tasks.items()):
                if entry.ttl is not None:
                    elapsed = (now - entry.created_at).total_seconds()
                    if elapsed > entry.ttl:
                        to_delete.append(task_id)
            for task_id in to_delete:
                TaskRegistry._tasks.pop(task_id, None)
        except Exception:
            pass

_cleanup_task = None

def start_cleanup_loop():
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        try:
            loop = asyncio.get_running_loop()
            _cleanup_task = loop.create_task(cleanup_expired_tasks_loop())
        except RuntimeError:
            pass
