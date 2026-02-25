"""Orchestrates a single source folder to one destination folder sync job."""
import os
import threading
from datetime import datetime, timezone
from typing import Optional

from core.scanner import scan_tree
from core.comparator import compare_trees
from core.file_ops import atomic_copy, safe_delete, _CancelledError
from db.models import SyncHistory, FileState
from db.repository import FileStateRepository, HistoryRepository
from utils import events
from utils.logger import get_logger

log = get_logger("synctool.engine")


class SyncEngine:
    """Syncs one source folder to one destination folder on one drive."""

    def __init__(
        self,
        source_path: str,
        dest_path: str,
        drive_serial: str,
        drive_label: str,
        direction: str,
        use_hash: bool,
        delete_extraneous: bool,
        cancel_event: threading.Event,
    ):
        self.source_path = source_path
        self.dest_path = dest_path
        self.drive_serial = drive_serial
        self.drive_label = drive_label
        self.direction = direction
        self.use_hash = use_hash
        self.delete_extraneous = delete_extraneous
        self.cancel_event = cancel_event
        self._file_state_repo = FileStateRepository()
        self._history_repo = HistoryRepository()
        self._history: Optional[SyncHistory] = None

    def run(self) -> None:
        self._history = self._history_repo.create(
            SyncHistory(
                id=None,
                source_path=self.source_path,
                drive_serial=self.drive_serial,
                drive_label=self.drive_label,
                dest_path=self.dest_path,
                started_at=datetime.now(timezone.utc).isoformat(),
                finished_at=None,
                status="running",
            )
        )
        events.put(events.LogEvent("info", f"[{self._tag()}] Scanning..."))

        try:
            plan = self._build_plan()
            if self._is_cancelled():
                self._finish("cancelled")
                return
            self._execute_plan(plan)
        except _CancelledError:
            self._finish("cancelled")
            return
        except Exception as exc:
            log.exception("Sync error for %s to %s", self.source_path, self.dest_path)
            self._finish("error", str(exc))
            return

        status = "cancelled" if self._is_cancelled() else "completed"
        self._finish(status)

    def _is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def _cancel_check(self) -> bool:
        return self.cancel_event.is_set()

    def _tag(self) -> str:
        src_name = os.path.basename(self.source_path) or self.source_path
        letter = self.dest_path[:3] if len(self.dest_path) >= 3 else self.drive_label
        return letter + "\\" + src_name

    def _build_plan(self):
        events.put(events.LogEvent("info", f"[{self._tag()}] Scanning source..."))
        src_stats = scan_tree(self.source_path, cancel_check=self._cancel_check)
        if self._is_cancelled():
            raise _CancelledError()

        events.put(events.LogEvent("info", f"[{self._tag()}] Scanning destination..."))
        dst_stats = scan_tree(self.dest_path, cancel_check=self._cancel_check)
        if self._is_cancelled():
            raise _CancelledError()

        # When source_path is a single file, scan_tree uses the file's basename
        # as rel_path but src_root must be the parent directory so that
        # os.path.join(src_root, rel) reconstructs the correct absolute path.
        src_root = (
            os.path.dirname(self.source_path)
            if os.path.isfile(self.source_path)
            else self.source_path
        )

        known_src, known_dst = {}, {}
        if self.direction == "bidirectional":
            known_src = self._file_state_repo.get_states(self.source_path, "SOURCE")
            known_dst = self._file_state_repo.get_states(self.source_path, self.drive_serial)

        plan = compare_trees(
            src_root=src_root,
            dst_root=self.dest_path,
            src_stats=src_stats,
            dst_stats=dst_stats,
            direction=self.direction,
            use_hash=self.use_hash,
            delete_extraneous=self.delete_extraneous,
            known_src_states=known_src,
            known_dst_states=known_dst,
        )
        events.put(events.LogEvent(
            "info",
            f"[{self._tag()}] Plan: {len(plan.to_copy)} copy, "
            f"{len(plan.conflicts)} conflict, {len(plan.to_delete)} delete, "
            f"{len(plan.to_skip)} skip",
        ))
        return plan

    def _execute_plan(self, plan) -> None:
        all_ops = (
            [(src, dst, rel, sz, "copy") for src, dst, rel, sz in plan.to_copy]
            + [(src, dst, rel, sz, "conflict") for src, dst, rel, sz in plan.conflicts]
        )
        total_files = len(all_ops) + len(plan.to_delete) + len(plan.to_skip)
        total_bytes = sum(sz for _, _, _, sz, _ in all_ops)
        done_files = 0
        done_bytes = 0
        history_entries = []

        def _emit(current_file=""):
            events.put(events.ProgressEvent(
                drive_serial=self.drive_serial,
                files_done=done_files,
                files_total=total_files,
                bytes_done=done_bytes,
                bytes_total=total_bytes,
                current_file=current_file,
            ))

        _emit()

        for src_abs, dst_abs, rel, size_bytes, action in all_ops:
            if self._is_cancelled():
                raise _CancelledError()

            def _progress_cb(n):
                nonlocal done_bytes
                done_bytes += n
                _emit(rel)

            try:
                atomic_copy(src_abs, dst_abs, progress_cb=_progress_cb,
                            cancel_check=self._cancel_check)
                history_entries.append((rel, action, size_bytes, ""))
                done_files += 1
                if self._history:
                    self._history.files_copied += 1
                    self._history.bytes_copied += size_bytes
                events.put(events.FileActionEvent(
                    drive_serial=self.drive_serial, rel_path=rel,
                    action=action, size_bytes=size_bytes,
                ))
            except _CancelledError:
                raise
            except Exception as exc:
                log.error("Copy failed %s: %s", src_abs, exc)
                history_entries.append((rel, "error", size_bytes, str(exc)))
                events.put(events.FileActionEvent(
                    drive_serial=self.drive_serial, rel_path=rel,
                    action="error", size_bytes=size_bytes, error_msg=str(exc),
                ))
                done_files += 1
            _emit(rel)

        for dst_abs in plan.to_delete:
            if self._is_cancelled():
                raise _CancelledError()
            rel = os.path.relpath(dst_abs, self.dest_path).replace("\\", "/")
            safe_delete(dst_abs)
            history_entries.append((rel, "delete", 0, ""))
            done_files += 1
            events.put(events.FileActionEvent(
                drive_serial=self.drive_serial, rel_path=rel,
                action="delete", size_bytes=0,
            ))
            _emit(rel)

        for src_abs, dst_abs, rel, size_bytes in plan.to_skip:
            if self._is_cancelled():
                raise _CancelledError()
            events.put(events.FileActionEvent(
                drive_serial=self.drive_serial, rel_path=rel,
                action="skip", size_bytes=size_bytes,
            ))
            done_files += 1
            _emit(rel)

        self._update_file_states(plan)
        if self._history and history_entries:
            self._history_repo.add_file_entries(self._history.id, history_entries)

    def _update_file_states(self, plan) -> None:
        if self.direction != "bidirectional":
            return
        states = []
        for src_abs, dst_abs, rel, *_ in plan.to_copy:
            for path, serial in [(dst_abs, self.drive_serial), (src_abs, "SOURCE")]:
                try:
                    st = os.stat(path)
                    states.append(FileState(
                        id=None,
                        source_path=self.source_path,
                        drive_serial=serial,
                        rel_path=rel,
                        size_bytes=st.st_size,
                        mtime_ns=st.st_mtime_ns,
                        sha256=None,
                    ))
                except OSError:
                    pass
        if states:
            self._file_state_repo.upsert_batch(states)

    def _finish(self, status: str, error_message: str = "") -> None:
        if self._history is None:
            return
        self._history.status = status
        self._history.finished_at = datetime.now(timezone.utc).isoformat()
        self._history.error_message = error_message
        self._history_repo.update(self._history)
        events.put(events.SyncCompleteEvent(
            drive_serial=self.drive_serial,
            status=status,
            files_copied=self._history.files_copied,
            bytes_copied=self._history.bytes_copied,
            error_message=error_message,
        ))
        events.put(events.LogEvent(
            "info" if status == "completed" else "warning",
            f"[{self._tag()}] {status.upper()} - "
            f"{self._history.files_copied} files, "
            f"{self._history.bytes_copied / 1024 / 1024:.1f} MB",
        ))
