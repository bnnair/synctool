"""Reusable tkinter widgets."""
import tkinter as tk
from tkinter import ttk, filedialog
from typing import Callable, Optional


class PathPicker(ttk.Frame):
    """A labeled entry + browse button for picking a directory."""

    def __init__(self, parent, label: str = "Path:", variable: tk.StringVar = None, **kwargs):
        super().__init__(parent, **kwargs)
        self._var = variable or tk.StringVar()

        ttk.Label(self, text=label, width=12, anchor="w").pack(side="left")
        self._entry = ttk.Entry(self, textvariable=self._var)
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(self, text="Browse…", width=8, command=self._browse).pack(side="left")

    def _browse(self):
        path = filedialog.askdirectory(title="Select Folder", mustexist=True)
        if path:
            self._var.set(path)

    @property
    def path(self) -> str:
        return self._var.get().strip()

    @path.setter
    def path(self, value: str):
        self._var.set(value)

    @property
    def variable(self) -> tk.StringVar:
        return self._var


class ProgressRow(ttk.Frame):
    """A labeled progress bar + status label for one drive."""

    def __init__(self, parent, drive_label: str = "Drive", **kwargs):
        super().__init__(parent, **kwargs)

        header = ttk.Frame(self)
        header.pack(fill="x")
        self._drive_label = ttk.Label(header, text=drive_label, font=("", 9, "bold"))
        self._drive_label.pack(side="left")
        self._status_label = ttk.Label(header, text="Idle", foreground="#888888")
        self._status_label.pack(side="right")

        self._bar = ttk.Progressbar(self, mode="determinate", maximum=100)
        self._bar.pack(fill="x", pady=(2, 0))

        self._detail_label = ttk.Label(self, text="", font=("", 8), foreground="#666666")
        self._detail_label.pack(fill="x")

    def set_drive_label(self, text: str):
        self._drive_label.config(text=text)

    def update_progress(
        self,
        files_done: int,
        files_total: int,
        bytes_done: int,
        bytes_total: int,
        current_file: str = "",
    ):
        pct = int(files_done / files_total * 100) if files_total > 0 else 0
        self._bar["value"] = pct

        mb_done = bytes_done / 1024 / 1024
        mb_total = bytes_total / 1024 / 1024
        self._status_label.config(
            text=f"{files_done}/{files_total} files  {mb_done:.1f}/{mb_total:.1f} MB",
            foreground="#2266cc",
        )
        short = current_file[-60:] if len(current_file) > 60 else current_file
        self._detail_label.config(text=short)

    def set_status(self, text: str, color: str = "#888888"):
        self._status_label.config(text=text, foreground=color)
        self._detail_label.config(text="")

    def reset(self):
        self._bar["value"] = 0
        self._status_label.config(text="Idle", foreground="#888888")
        self._detail_label.config(text="")


class SectionLabel(ttk.Label):
    """Bold section header label."""

    def __init__(self, parent, text: str, **kwargs):
        kwargs.setdefault("font", ("", 9, "bold"))
        super().__init__(parent, text=text, **kwargs)


class Separator(ttk.Separator):
    def __init__(self, parent, **kwargs):
        kwargs.setdefault("orient", "horizontal")
        super().__init__(parent, **kwargs)
