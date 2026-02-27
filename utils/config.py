"""Application-wide constants and configuration."""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "synctool.db")
LOG_PATH = os.path.join(DATA_DIR, "synctool.log")

MAX_DRIVES = 3
COPY_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB chunks for streaming copy + hash
COPY_RETRY_COUNT = 3
COPY_RETRY_DELAY = 1.0  # seconds

# Parallel workers for directory tree scanning (more = faster on SSDs/NVMe)
SCAN_WORKERS = 8

# Parallel workers for file copy within a single drive job.
# Helps most with many small files; USB bandwidth is still the ceiling for large files.
COPY_WORKERS = 4

# Directory names that are silently skipped during scanning.
# These are development/VCS artifacts that are never useful to sync and can
# contain hundreds of thousands of files (e.g. .git/objects, node_modules).
# Add or remove entries here to customise the exclusion list.
SCAN_EXCLUDE_DIRS: frozenset = frozenset({
    # Version control internals
    ".git",
    ".hg",
    ".svn",
    ".tmp",
    ".ipynb_checkpoints",
    "ailib",
    ".metadata",
    "Lib/site-packages*",
    # JavaScript / Node
    "node_modules",
    # Python
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
})

DRIVE_POLL_INTERVAL_MS = 2000  # how often to check for new drives
UI_QUEUE_POLL_MS = 300          # how often the UI drains the event queue

APP_TITLE = "SyncTool"
APP_WIDTH = 920
APP_HEIGHT = 640

# Ensure data directory exists at import time
os.makedirs(DATA_DIR, exist_ok=True)
