"""Fast directory tree scanner using os.scandir recursively."""
import os
from typing import Optional
from db.models import FileStat


def scan_tree(root: str, cancel_check=None) -> dict[str, FileStat]:
    """Walk *root* and return {rel_path: FileStat} for every file.

    Uses os.scandir() for speed (avoids repeated stat calls from os.walk).
    rel_path uses forward slashes and is relative to *root*.

    Follows symlinks and Windows junction points (follow_symlinks=True).
    Tracks visited real paths to avoid infinite loops from circular links.

    cancel_check: optional callable returning True to abort early.
    """
    result: dict[str, FileStat] = {}
    root = os.path.normpath(root)

    # If root is a single file (user added via "Add Files"), treat its
    # parent as the base so rel_path = just the filename.
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

    visited: set[str] = set()
    _walk(root, root, result, cancel_check, visited)
    return result


def _walk(base: str, current: str, result: dict, cancel_check, visited: set) -> None:
    if cancel_check and cancel_check():
        return

    # Resolve the real path to detect cycles (circular symlinks / junctions).
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
                # follow_symlinks=True so that Windows junction points and
                # symlinks are treated as their target type.
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
                    _walk(base, entry.path, result, cancel_check, visited)
    except PermissionError:
        pass
    except OSError:
        pass
