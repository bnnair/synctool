"""SyncTool - Windows desktop file sync application.

Entry point. Run with:
    python main.py
"""
import sys
import os

# Ensure the project root is on sys.path so that absolute imports work
# when running as `python main.py` from any working directory.
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from utils.logger import setup_logging
from db.database import initialize


def main():
    setup_logging()

    # Initialize SQLite schema (no-op if already done)
    initialize()

    # Import here (after sys.path is set) to avoid premature tkinter import
    from ui.app import App
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
