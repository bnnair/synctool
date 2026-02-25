"""Manages concurrent SyncEngine runs: one thread per drive, sequential sources per drive."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Optional

from core.sync_engine import SyncEngine
from db.models import DriveJob
from utils.config import MAX_DRIVES
from utils.logger import get_logger

log = get_logger("synctool.parallel")


class ParallelSyncManager:
    """Run one thread per destination drive; each thread processes all source folders."""

    def __init__(self):
        self._cancel_event = threading.Event()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._futures: list = []
        self._lock = threading.Lock()

    def start(
        self,
        jobs: list,  # list[DriveJob]
        on_all_done: Optional[Callable[[], None]] = None,
    ) -> None:
        if not jobs:
            log.warning("No drive jobs provided.")
            return

        jobs = jobs[:MAX_DRIVES]
        self._cancel_event.clear()

        n_workers = min(len(jobs), MAX_DRIVES)
        self._executor = ThreadPoolExecutor(max_workers=n_workers, thread_name_prefix="sync")

        with self._lock:
            self._futures = [
                self._executor.submit(self._run_job, job)
                for job in jobs
            ]

        threading.Thread(
            target=self._monitor,
            args=(on_all_done,),
            daemon=True,
            name="sync-monitor",
        ).start()

    def cancel(self) -> None:
        self._cancel_event.set()
        log.info("Cancel requested.")

    @property
    def is_running(self) -> bool:
        with self._lock:
            return any(not f.done() for f in self._futures)

    def _run_job(self, job: DriveJob) -> None:
        """Run all source folders for one drive sequentially."""
        for source_path in job.sources:
            if self._cancel_event.is_set():
                break
            # Contents of source go directly into dest_root (no extra subfolder)
            dest_path = job.drive.dest_root
            engine = SyncEngine(
                source_path=source_path,
                dest_path=dest_path,
                drive_serial=job.drive.drive_serial,
                drive_label=job.drive.drive_label,
                direction=job.direction,
                use_hash=job.use_hash,
                delete_extraneous=job.delete_extraneous,
                cancel_event=self._cancel_event,
            )
            try:
                engine.run()
            except Exception as exc:
                log.exception("Unexpected engine error: %s", exc)

    def _monitor(self, on_all_done) -> None:
        with self._lock:
            futures = list(self._futures)
        for f in futures:
            try:
                f.result()
            except Exception:
                pass
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None
        if on_all_done:
            try:
                on_all_done()
            except Exception:
                log.exception("Error in on_all_done callback")
