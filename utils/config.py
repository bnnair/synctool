"""Application-wide constants and configuration."""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "synctool.db")
LOG_PATH = os.path.join(DATA_DIR, "synctool.log")

MAX_DRIVES = 3
COPY_CHUNK_SIZE = 1 * 1024 * 1024  # 1 MB chunks for streaming copy + hash
COPY_RETRY_COUNT = 3
COPY_RETRY_DELAY = 1.0  # seconds

DRIVE_POLL_INTERVAL_MS = 2000  # how often to check for new drives
UI_QUEUE_POLL_MS = 300          # how often the UI drains the event queue

APP_TITLE = "SyncTool"
APP_WIDTH = 920
APP_HEIGHT = 640

# Ensure data directory exists at import time
os.makedirs(DATA_DIR, exist_ok=True)
