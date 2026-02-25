"""SQLite connection manager with WAL mode and thread-safe locking."""
import sqlite3
import threading
from utils.config import DB_PATH

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Key/value store for app settings and last session
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

-- Per-file state recorded after a successful sync (used by bidirectional mode)
CREATE TABLE IF NOT EXISTS file_states (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path  TEXT    NOT NULL,
    drive_serial TEXT    NOT NULL,
    rel_path     TEXT    NOT NULL,
    size_bytes   INTEGER NOT NULL,
    mtime_ns     INTEGER NOT NULL,
    sha256       TEXT,
    synced_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_path, drive_serial, rel_path)
);
CREATE INDEX IF NOT EXISTS idx_file_states_lookup
    ON file_states(source_path, drive_serial, rel_path);

-- One row per sync job execution
CREATE TABLE IF NOT EXISTS sync_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path   TEXT    NOT NULL,
    drive_serial  TEXT    NOT NULL,
    drive_label   TEXT    NOT NULL DEFAULT '',
    dest_path     TEXT    NOT NULL DEFAULT '',
    started_at    TEXT    NOT NULL,
    finished_at   TEXT,
    status        TEXT    NOT NULL DEFAULT 'running',
    files_copied  INTEGER NOT NULL DEFAULT 0,
    bytes_copied  INTEGER NOT NULL DEFAULT 0,
    error_message TEXT    NOT NULL DEFAULT ''
);

-- Per-file detail for each history entry
CREATE TABLE IF NOT EXISTS sync_history_files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    history_id INTEGER NOT NULL REFERENCES sync_history(id) ON DELETE CASCADE,
    rel_path   TEXT    NOT NULL,
    action     TEXT    NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    error_msg  TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_history_files
    ON sync_history_files(history_id);
"""


def initialize() -> None:
    """Create tables if they don't exist. Call once at startup."""
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()


def get_conn() -> tuple[sqlite3.Connection, threading.Lock]:
    """Return the shared connection and its lock.

    Callers must acquire the lock before every execute:
        conn, lock = get_conn()
        with lock:
            conn.execute(...)
    """
    if _conn is None:
        initialize()
    return _conn, _lock


def close() -> None:
    global _conn
    with _lock:
        if _conn:
            _conn.close()
            _conn = None
