"""Diff two scanned trees and produce a SyncPlan."""
import hashlib
import os
from datetime import datetime
from typing import Optional

from db.models import FileStat, SyncPlan, FileState
from utils.config import COPY_CHUNK_SIZE


def _compute_sha256(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(COPY_CHUNK_SIZE)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _files_differ(
    src_path: str,
    dst_path: str,
    src_stat: FileStat,
    dst_stat: FileStat,
    use_hash: bool,
) -> bool:
    """Return True if src and dst should be considered different."""
    if src_stat.size_bytes != dst_stat.size_bytes:
        return True
    if src_stat.mtime_ns != dst_stat.mtime_ns:
        if use_hash:
            return _compute_sha256(src_path) != _compute_sha256(dst_path)
        return True
    return False


def _conflict_dst_path(dst_path: str) -> str:
    """Generate a conflict-renamed path: file.conflict_20260224_143000.txt"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base, ext = os.path.splitext(dst_path)
    return f"{base}.conflict_{stamp}{ext}"


def compare_trees(
    src_root: str,
    dst_root: str,
    src_stats: dict[str, FileStat],
    dst_stats: dict[str, FileStat],
    direction: str,
    use_hash: bool,
    delete_extraneous: bool,
    known_src_states: Optional[dict[str, FileState]] = None,
    known_dst_states: Optional[dict[str, FileState]] = None,
) -> SyncPlan:
    """
    Returns a SyncPlan describing what needs to happen.

    to_copy  entries: (src_abs, dst_abs, rel_path, size_bytes)
    to_delete entries: dst_abs path strings
    conflicts entries: (src_abs, conflict_dst_abs, rel_path, size_bytes)
    """
    plan = SyncPlan()

    if direction == "source_to_dest":
        _plan_one_way(
            src_root, dst_root,
            src_stats, dst_stats,
            use_hash, delete_extraneous,
            plan,
        )
    elif direction == "dest_to_source":
        _plan_one_way(
            dst_root, src_root,
            dst_stats, src_stats,
            use_hash, delete_extraneous,
            plan,
        )
    elif direction == "bidirectional":
        _plan_bidirectional(
            src_root, dst_root,
            src_stats, dst_stats,
            use_hash, delete_extraneous,
            known_src_states or {},
            known_dst_states or {},
            plan,
        )

    return plan


def _plan_one_way(
    from_root: str,
    to_root: str,
    from_stats: dict[str, FileStat],
    to_stats: dict[str, FileStat],
    use_hash: bool,
    delete_extraneous: bool,
    plan: SyncPlan,
) -> None:
    for rel, from_stat in from_stats.items():
        from_abs = os.path.join(from_root, rel.replace("/", os.sep))
        to_abs = os.path.join(to_root, rel.replace("/", os.sep))

        if rel not in to_stats:
            plan.to_copy.append((from_abs, to_abs, rel, from_stat.size_bytes))
        else:
            to_stat = to_stats[rel]
            if _files_differ(from_abs, to_abs, from_stat, to_stat, use_hash):
                plan.to_copy.append((from_abs, to_abs, rel, from_stat.size_bytes))
            else:
                plan.to_skip.append((from_abs, to_abs, rel, from_stat.size_bytes))

    if delete_extraneous:
        for rel in to_stats:
            if rel not in from_stats:
                to_abs = os.path.join(to_root, rel.replace("/", os.sep))
                plan.to_delete.append(to_abs)


def _stat_changed(stat: FileStat, known: Optional[FileState]) -> bool:
    if known is None:
        return True  # never synced → treat as changed
    return stat.size_bytes != known.size_bytes or stat.mtime_ns != known.mtime_ns


def _plan_bidirectional(
    src_root: str,
    dst_root: str,
    src_stats: dict[str, FileStat],
    dst_stats: dict[str, FileStat],
    use_hash: bool,
    delete_extraneous: bool,
    known_src: dict[str, FileState],
    known_dst: dict[str, FileState],
    plan: SyncPlan,
) -> None:
    all_paths = set(src_stats) | set(dst_stats)

    for rel in all_paths:
        src_abs = os.path.join(src_root, rel.replace("/", os.sep))
        dst_abs = os.path.join(dst_root, rel.replace("/", os.sep))

        src_stat = src_stats.get(rel)
        dst_stat = dst_stats.get(rel)

        src_changed = src_stat is not None and _stat_changed(src_stat, known_src.get(rel))
        dst_changed = dst_stat is not None and _stat_changed(dst_stat, known_dst.get(rel))

        if src_stat and dst_stat:
            if src_changed and dst_changed:
                # Both changed → conflict: copy src over with a renamed dst
                conflict_abs = _conflict_dst_path(dst_abs)
                plan.conflicts.append((src_abs, conflict_abs, rel, src_stat.size_bytes))
            elif src_changed:
                if _files_differ(src_abs, dst_abs, src_stat, dst_stat, use_hash):
                    plan.to_copy.append((src_abs, dst_abs, rel, src_stat.size_bytes))
                else:
                    plan.to_skip.append((src_abs, dst_abs, rel, src_stat.size_bytes))
            elif dst_changed:
                if _files_differ(dst_abs, src_abs, dst_stat, src_stat, use_hash):
                    plan.to_copy.append((dst_abs, src_abs, rel, dst_stat.size_bytes))
                else:
                    plan.to_skip.append((dst_abs, src_abs, rel, dst_stat.size_bytes))
            else:
                plan.to_skip.append((src_abs, dst_abs, rel, src_stat.size_bytes))
        elif src_stat and not dst_stat:
            # Only on source
            plan.to_copy.append((src_abs, dst_abs, rel, src_stat.size_bytes))
        elif dst_stat and not src_stat:
            # Only on dest
            if delete_extraneous:
                plan.to_delete.append(dst_abs)
            else:
                plan.to_copy.append((dst_abs, src_abs, rel, dst_stat.size_bytes))
