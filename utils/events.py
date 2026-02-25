"""Thread-safe event bus using queue.Queue.

Sync threads put events; the UI main thread drains the queue via root.after().
"""
import queue
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProgressEvent:
    drive_serial: str
    files_done: int
    files_total: int
    bytes_done: int
    bytes_total: int
    current_file: str = ""


@dataclass
class FileActionEvent:
    drive_serial: str
    rel_path: str
    action: str  # 'copy' | 'skip' | 'delete' | 'conflict' | 'error'
    size_bytes: int = 0
    error_msg: str = ""


@dataclass
class SyncCompleteEvent:
    drive_serial: str
    status: str  # 'completed' | 'cancelled' | 'error'
    files_copied: int = 0
    bytes_copied: int = 0
    error_message: str = ""


@dataclass
class LogEvent:
    level: str  # 'info' | 'warning' | 'error'
    message: str


# Module-level queue shared between sync threads and the UI
_event_queue: queue.Queue = queue.Queue()


def put(event) -> None:
    _event_queue.put_nowait(event)


def drain():
    """Yield all pending events without blocking."""
    while True:
        try:
            yield _event_queue.get_nowait()
        except queue.Empty:
            break
