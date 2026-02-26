"""Fast directory tree scanner using os.scandir with parallel subdirectory walking."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from db.models import FileStat
from utils.config import SCAN_WORKERS, SCAN_EXCLUDE_DIRS


def scan_tree(root: str, cancel_check=None) -> dict[str, FileStat]:
    """Walk *root* and return {rel_path: FileStat} for every file.

    Top-level subdirectories are scanned in parallel via a ThreadPoolExecutor
    (up to SCAN_WORKERS threads) which significantly reduces wall time on SSDs
    and NVMe drives with deep or wide trees.

    Uses os.scandir() so each directory entry yields its stat for free,
    avoiding a separate stat() call per file.

    cancel_check: optional callable returning True to abort early.
    """
    result: dict[str, FileStat] = {}
    root = os.path.normpath(root)

    # Single-file source: treat the file's parent as base so rel_path = filename.
    if os.path.isfile(root):
        try:
            st = os.stat(root)
            rel = os.path.basename(root)
            result[rel] = FileStat(
                rel_path=rel,
                size_bytes=st.st_size,
                mtime_ns=st.st_mtime_ns,
            )
        except OSError:
            pass
        return result

    # Scan the root level to separate files (handled inline) from subdirectories
    # (each dispatched to its own worker thread).
    subdirs: list[str] = []
    try:
        with os.scandir(root) as it:
            for entry in it:
                if cancel_check and cancel_check():
                    return result
                if entry.is_file(follow_symlinks=True):
                    try:
                        st = entry.stat(follow_symlinks=True)
                        rel = os.path.relpath(entry.path, root).replace("\\", "/")
                        result[rel] = FileStat(
                            rel_path=rel,
                            size_bytes=st.st_size,
                            mtime_ns=st.st_mtime_ns,
                        )
                    except OSError:
                        pass
                elif entry.is_dir(follow_symlinks=True):
                    if entry.name not in SCAN_EXCLUDE_DIRS:
                        subdirs.append(entry.path)
    except OSError:
        return result

    if not subdirs or (cancel_check and cancel_check()):
        return result

    # Each subdirectory is scanned independently in a worker thread.
    # Every worker gets its own `visited` set; this is correct because
    # circular-link detection only needs to be cycle-free within one traversal.
    def _scan_subdir(subdir: str) -> dict[str, FileStat]:
        sub: dict[str, FileStat] = {}
        visited: set[str] = set()
        _walk(root, subdir, sub, cancel_check, visited)
        return sub

    workers = min(SCAN_WORKERS, len(subdirs))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scanner") as ex:
        futures = {ex.submit(_scan_subdir, d): d for d in subdirs}
        for fut in as_completed(futures):
            if cancel_check and cancel_check():
                break
            try:
                result.update(fut.result())
            except Exception:
                pass

    return result


def _walk(base: str, current: str, result: dict, cancel_check, visited: set) -> None:
    """Recursively walk *current*, appending FileStat entries to *result*."""
    if cancel_check and cancel_check():
        return

    try:
        real = os.path.realpath(current)
    except OSError:
        return
    if real in visited:
        return
    visited.add(real)

    try:
        with os.scandir(current) as it:
            for entry in it:
                if cancel_check and cancel_check():
                    return
                if entry.is_file(follow_symlinks=True):
                    try:
                        st = entry.stat(follow_symlinks=True)
                        rel = os.path.relpath(entry.path, base).replace("\\", "/")
                        result[rel] = FileStat(
                            rel_path=rel,
                            size_bytes=st.st_size,
                            mtime_ns=st.st_mtime_ns,
                        )
                    except OSError:
                        pass
                elif entry.is_dir(follow_symlinks=True):
                    if entry.name not in SCAN_EXCLUDE_DIRS:
                        _walk(base, entry.path, result, cancel_check, visited)
    except PermissionError:
        pass
    except OSError:
        pass
