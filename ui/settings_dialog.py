"""Settings panel — hash mode, mirror mode, conflict resolution."""
import tkinter as tk
from tkinter import ttk, messagebox

from utils.config import DB_PATH


class SettingsPanel(ttk.Frame):
    """Embedded settings panel (Settings notebook tab)."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        # Public vars — wired into SyncPanel by MainWindow so Start Sync reads them live
        self.use_hash_var = tk.BooleanVar(value=False)
        self.delete_var = tk.BooleanVar(value=False)
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        ttk.Label(
            self,
            text="Settings apply to all sync operations and are read each time Start Sync is clicked.",
            wraplength=460, foreground="#555555",
        ).pack(fill="x", **pad)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=8, pady=4)

        ttk.Checkbutton(
            self,
            text="Use SHA-256 hash when file sizes match but timestamps differ\n"
                 "(more accurate, but slower — recommended for FAT32 / exFAT drives)",
            variable=self.use_hash_var,
        ).pack(anchor="w", **pad)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=8, pady=4)

        ttk.Checkbutton(
            self,
            text="Mirror mode — delete files on destination not present in source\n"
                 "(WARNING: permanently deletes files that exist only on the destination)",
            variable=self.delete_var,
        ).pack(anchor="w", **pad)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=8, pady=4)

        ttk.Label(self, text="Conflict resolution (bidirectional sync):",
                  font=("", 9, "bold")).pack(anchor="w", padx=12)
        self._conflict_var = tk.StringVar(value="keep_both")
        for label, value in [
            ("Keep both — rename the conflicting file with a timestamp  (safe default)", "keep_both"),
            ("Prefer source — overwrite destination",                                    "prefer_source"),
            ("Prefer destination — overwrite source",                                   "prefer_dest"),
        ]:
            ttk.Radiobutton(
                self, text=label, value=value, variable=self._conflict_var
            ).pack(anchor="w", padx=24, pady=1)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=8, pady=12)

        ttk.Label(self, text="Database", font=("", 9, "bold")).pack(anchor="w", padx=12)
        ttk.Label(self, text=f"Location: {DB_PATH}",
                  wraplength=460, foreground="#555555").pack(anchor="w", padx=12)
        ttk.Button(self, text="Vacuum DB  (shrink file size)",
                   command=self._vacuum).pack(anchor="w", padx=12, pady=6)

    def _vacuum(self):
        from db.database import get_conn
        conn, lock = get_conn()
        with lock:
            conn.execute("VACUUM")
        messagebox.showinfo("Done", "Database vacuumed successfully.", parent=self)
