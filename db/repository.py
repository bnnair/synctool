"""CRUD operations for all database entities."""
import json
import sqlite3
from typing import Optional
from db.database import get_conn
from db.models import FileState, SyncHistory, SyncDrive


class SettingsRepository:
    """Key/value settings store — also persists the last used session."""

    def get(self, key: str, default: str = "") -> str:
        conn, lock = get_conn()
        with lock:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        conn, lock = get_conn()
        with lock:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            conn.commit()

    def save_session(
        self,
        sources: list,
        drives: list,       # list[SyncDrive]
        direction: str,
        use_hash: bool,
        delete_extraneous: bool,
    ) -> None:
        drives_data = [
            {"serial": d.drive_serial, "label": d.drive_label,
             "letter": d.drive_letter, "dest_root": d.dest_root}
            for d in drives
        ]
        self.set("last_sources", json.dumps(sources))
        self.set("last_drives", json.dumps(drives_data))
        self.set("direction", direction)
        self.set("use_hash", "1" if use_hash else "0")
        self.set("delete_extraneous", "1" if delete_extraneous else "0")

    def load_session(self) -> dict:
        try:
            sources = json.loads(self.get("last_sources", "[]"))
        except Exception:
            sources = []
        try:
            drives_data = json.loads(self.get("last_drives", "[]"))
            drives = [
                SyncDrive(
                    drive_serial=d["serial"],
                    drive_label=d["label"],
                    drive_letter=d["letter"],
                    dest_root=d["dest_root"],
                )
                for d in drives_data
            ]
        except Exception:
            drives = []
        return {
            "sources": sources,
            "drives": drives,
            "direction": self.get("direction", "source_to_dest"),
            "use_hash": self.get("use_hash", "0") == "1",
            "delete_extraneous": self.get("delete_extraneous", "0") == "1",
        }


class FileStateRepository:
    def get_states(self, source_path: str, drive_serial: str) -> dict:
        """Return {rel_path: FileState} for the given source+drive."""
        conn, lock = get_conn()
        with lock:
            rows = conn.execute(
                "SELECT * FROM file_states WHERE source_path=? AND drive_serial=?",
                (source_path, drive_serial),
            ).fetchall()
        return {
            r["rel_path"]: FileState(
                id=r["id"],
                source_path=r["source_path"],
                drive_serial=r["drive_serial"],
                rel_path=r["rel_path"],
                size_bytes=r["size_bytes"],
                mtime_ns=r["mtime_ns"],
                sha256=r["sha256"],
            )
            for r in rows
        }

    def upsert_batch(self, states: list) -> None:
        if not states:
            return
        conn, lock = get_conn()
        with lock:
            conn.executemany(
                """INSERT INTO file_states (source_path, drive_serial, rel_path, size_bytes, mtime_ns, sha256)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_path, drive_serial, rel_path)
                   DO UPDATE SET size_bytes=excluded.size_bytes,
                                 mtime_ns=excluded.mtime_ns,
                                 sha256=excluded.sha256,
                                 synced_at=datetime('now')""",
                [(s.source_path, s.drive_serial, s.rel_path, s.size_bytes, s.mtime_ns, s.sha256)
                 for s in states],
            )
            conn.commit()


class HistoryRepository:
    def create(self, history: SyncHistory) -> SyncHistory:
        conn, lock = get_conn()
        with lock:
            cur = conn.execute(
                """INSERT INTO sync_history
                   (source_path, drive_serial, drive_label, dest_path, started_at, status)
                   VALUES (?, ?, ?, ?, ?, 'running')""",
                (history.source_path, history.drive_serial,
                 history.drive_label, history.dest_path, history.started_at),
            )
            conn.commit()
            history.id = cur.lastrowid
        return history

    def update(self, history: SyncHistory) -> None:
        conn, lock = get_conn()
        with lock:
            conn.execute(
                """UPDATE sync_history
                   SET finished_at=?, status=?, files_copied=?, bytes_copied=?, error_message=?
                   WHERE id=?""",
                (history.finished_at, history.status, history.files_copied,
                 history.bytes_copied, history.error_message, history.id),
            )
            conn.commit()

    def list_recent(self, limit: int = 200) -> list:
        conn, lock = get_conn()
        with lock:
            rows = conn.execute(
                "SELECT * FROM sync_history ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def _row_to_model(self, r) -> SyncHistory:
        return SyncHistory(
            id=r["id"],
            source_path=r["source_path"],
            drive_serial=r["drive_serial"],
            drive_label=r["drive_label"],
            dest_path=r["dest_path"],
            started_at=r["started_at"],
            finished_at=r["finished_at"],
            status=r["status"],
            files_copied=r["files_copied"],
            bytes_copied=r["bytes_copied"],
            error_message=r["error_message"],
        )

    def add_file_entries(self, history_id: int, entries: list) -> None:
        """entries: list of (rel_path, action, size_bytes, error_msg)"""
        if not entries:
            return
        conn, lock = get_conn()
        with lock:
            conn.executemany(
                """INSERT INTO sync_history_files (history_id, rel_path, action, size_bytes, error_msg)
                   VALUES (?, ?, ?, ?, ?)""",
                [(history_id, e[0], e[1], e[2], e[3]) for e in entries],
            )
            conn.commit()

    def get_file_entries(self, history_id: int) -> list:
        conn, lock = get_conn()
        with lock:
            return conn.execute(
                "SELECT * FROM sync_history_files WHERE history_id=? ORDER BY id",
                (history_id,),
            ).fetchall()

    def clear_all(self) -> None:
        conn, lock = get_conn()
        with lock:
            conn.execute("DELETE FROM sync_history_files")
            conn.execute("DELETE FROM sync_history")
            conn.commit()
