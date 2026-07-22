import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Protocol, List, Dict, Optional

# Protocol for Logger matching TS Winstron logger equivalent (Section 13)
class Logger(Protocol):
    def debug(self, message: str, meta: dict | None = None) -> None: ...
    def info(self, message: str, meta: dict | None = None) -> None: ...
    def warn(self, message: str, meta: dict | None = None) -> None: ...
    def error(self, message: str, meta: dict | None = None) -> None: ...

import datetime
import json

class EventEmitterHandler(logging.Handler):
    def emit(self, record):
        try:
            info = {
                "level": record.levelname.lower(),
                "message": record.getMessage(),
                "timestamp": datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).isoformat(),
            }
            if hasattr(record, "meta") and isinstance(record.meta, dict):
                info.update(record.meta)
            
            try:
                from nitrostack.events.event_emitter import EventEmitter
                EventEmitter.get_instance().emit_sync("log", info)
            except Exception:
                pass

            sys.stderr.write(f"NITRO_LOG::{json.dumps(info)}\n")
            sys.stderr.flush()
        except Exception:
            pass

class FileLogger:
    """
    Logger implementation that writes to a file or stdout/stderr based on transport settings.
    This prevents corrupting the MCP stdio JSON-RPC transport.
    """
    def __init__(self, log_file: Optional[str] = None, name: str = "nitrostack"):
        self.logger = logging.getLogger(name)
        
        level_str = os.environ.get("NITROSTACK_LOG_LEVEL", "DEBUG").upper()
        level = getattr(logging, level_str, logging.DEBUG)
        self.logger.setLevel(level)
        
        has_ee_handler = any(isinstance(h, EventEmitterHandler) for h in self.logger.handlers)
        if not has_ee_handler:
            self.logger.addHandler(EventEmitterHandler())
            
        if not [h for h in self.logger.handlers if not isinstance(h, EventEmitterHandler)]:
            formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] (%(name)s): %(message)s'
            )
            
            log_to_stdout = (
                os.environ.get("NITROSTACK_LOG_TO_STDOUT", "false").lower() == "true"
                or os.environ.get("MCP_TRANSPORT_TYPE") == "http"
            )
            
            if log_to_stdout:
                sh = logging.StreamHandler(sys.stdout)
                sh.setLevel(level)
                sh.setFormatter(formatter)
                self.logger.addHandler(sh)
            else:
                target_file = log_file or os.environ.get("NITROSTACK_LOG_FILE", "nitrostack.log")
                try:
                    fh = logging.FileHandler(target_file, encoding='utf-8')
                    fh.setLevel(level)
                    fh.setFormatter(formatter)
                    self.logger.addHandler(fh)
                except Exception:
                    pass
                
    def _format_message(self, message: str, meta: dict | None = None) -> str:
        if meta:
            return f"{message} | meta: {meta}"
        return message

    def debug(self, message: str, meta: dict | None = None) -> None:
        self.logger.debug(self._format_message(message, meta), extra={"meta": meta})

    def info(self, message: str, meta: dict | None = None) -> None:
        self.logger.info(self._format_message(message, meta), extra={"meta": meta})

    def warn(self, message: str, meta: dict | None = None) -> None:
        self.logger.warning(self._format_message(message, meta), extra={"meta": meta})

    def error(self, message: str, meta: dict | None = None) -> None:
        self.logger.error(self._format_message(message, meta), extra={"meta": meta})

@dataclass
class AuthContext:
    subject: str | None = None       # user/client identifier
    scopes: List[str] = field(default_factory=list)  # granted permissions
    client_id: str | None = None     # machine-to-machine
    exp: int | None = None           # expiration timestamp
    iat: int | None = None           # issued-at timestamp
    iss: str | None = None           # issuer URL
    claims: Dict[str, Any] = field(default_factory=dict)  # custom claims
    token_payload: Any = None        # full decoded token

class TaskCancelledError(Exception):
    """Raised when an MCP background task has been cancelled."""
    pass

class TaskContext:
    """Context representation for long-running asynchronous MCP tasks."""
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.progress_message: str = ""

    @property
    def is_cancelled(self) -> bool:
        try:
            from nitrostack.core.task import TaskRegistry
            return TaskRegistry.is_task_cancelled(self.task_id)
        except Exception:
            return False

    @property
    def abort_signal(self) -> Any:
        try:
            from nitrostack.core.task import TaskRegistry
            entry = TaskRegistry.get_task(self.task_id)
            if entry:
                return entry.abort_controller.signal
        except Exception:
            pass
        from nitrostack.core.task import AbortSignal
        return AbortSignal()

    @property
    def abortSignal(self) -> Any:
        return self.abort_signal

    def update_progress(self, message: str) -> None:
        self.progress_message = message
        try:
            from nitrostack.core.task import TaskRegistry
            TaskRegistry.update_progress(self.task_id, message)
        except Exception:
            pass

    def cancel(self) -> None:
        try:
            from nitrostack.core.task import TaskRegistry
            TaskRegistry.cancel_task(self.task_id)
        except Exception:
            pass

    def throw_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise TaskCancelledError(f"Task {self.task_id} has been cancelled.")

@dataclass
class ExecutionContext:
    request_id: str
    tool_name: str | None = None
    logger: Logger = field(default_factory=lambda: FileLogger())
    metadata: dict = field(default_factory=dict)
    auth: AuthContext | None = None
    task: TaskContext | None = None
