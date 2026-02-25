"""Atomic file copy, delete, and verification with retry logic."""
import os
import shutil
import time
from typing import Callable, Optional

from utils.config import COPY_RETRY_COUNT, COPY_RETRY_DELAY
from utils.logger import get_logger

log = get_logger("synctool.file_ops")


def atomic_copy(
    src: str,
    dst: str,
    progress_cb: Optional[Callable[[int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> None:
    """Copy src to dst atomically.

    Writes to dst + '.synctmp', then renames.  Preserves metadata via shutil.copy2.
    progress_cb(bytes_written) is called after each chunk.
    cancel_check() returning True aborts the copy (removes the temp file).
    """
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".synctmp"

    for attempt in range(1, COPY_RETRY_COUNT + 1):
        try:
            _do_copy(src, tmp, progress_cb, cancel_check)
            # Copy metadata (timestamps, permissions)
            shutil.copystat(src, tmp)
            os.replace(tmp, dst)  # atomic on same filesystem
            return
        except _CancelledError:
            _remove_silent(tmp)
            raise
        except OSError as exc:
            _remove_silent(tmp)
            if attempt == COPY_RETRY_COUNT:
                raise
            log.warning("Copy attempt %d failed (%s): %s", attempt, src, exc)
            time.sleep(COPY_RETRY_DELAY)


class _CancelledError(Exception):
    pass


def _do_copy(src, dst, progress_cb, cancel_check):
    from utils.config import COPY_CHUNK_SIZE
    written = 0
    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        while True:
            if cancel_check and cancel_check():
                raise _CancelledError()
            chunk = fsrc.read(COPY_CHUNK_SIZE)
            if not chunk:
                break
            fdst.write(chunk)
            written += len(chunk)
            if progress_cb:
                progress_cb(len(chunk))


def safe_delete(path: str) -> None:
    """Delete a file, logging but not raising on error."""
    try:
        os.remove(path)
        # Clean up empty parent directories (don't remove root)
        parent = os.path.dirname(path)
        try:
            os.removedirs(parent)
        except OSError:
            pass
    except OSError as exc:
        log.warning("Could not delete %s: %s", path, exc)


def _remove_silent(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
