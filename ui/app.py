"""Root Tk window and application bootstrap."""
import tkinter as tk
from tkinter import ttk

from ui.main_window import MainWindow
from utils.config import APP_TITLE, APP_WIDTH, APP_HEIGHT


def _apply_theme(root: tk.Tk) -> None:
    """Apply sv_ttk (Windows 11 theme) if available, fall back to clam."""
    try:
        import sv_ttk
        sv_ttk.set_theme("light")
    except ImportError:
        style = ttk.Style(root)
        available = style.theme_names()
        for preferred in ("vista", "winnative", "xpnative", "clam"):
            if preferred in available:
                style.theme_use(preferred)
                break

    # Accent button style (used for Start Sync)
    style = ttk.Style()
    try:
        style.configure("Accent.TButton", font=("", 10, "bold"))
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self._center_window()
        self.minsize(720, 520)

        _apply_theme(self)
        self._set_icon()

        self._main = MainWindow(self)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _center_window(self):
        """Size the window to 75% of the screen and centre it."""
        self.update_idletasks()          # ensure screen dimensions are available
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = int(sw * 0.75)
        h = int(sh * 0.75)
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _set_icon(self):
        import os
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.ico"
        )
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

    def _on_close(self):
        from db import database
        database.close()
        self.destroy()
