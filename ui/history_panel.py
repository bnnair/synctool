"""History tab: shows past sync runs with expandable per-file detail."""
import os
import tkinter as tk
from tkinter import ttk, messagebox

from db.repository import HistoryRepository


def _fmt_bytes(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024**3:.1f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024**2:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


class HistoryPanel(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._history_repo = HistoryRepository()
        self._build_ui()

    def _build_ui(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=6)
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Clear All History",
                   command=self._clear_history).pack(side="right")

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        cols = ("#", "Date/Time", "Source", "Drive", "Dest Folder", "Files", "Size", "Status")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        for col in cols:
            self._tree.heading(col, text=col)
        self._tree.column("#",           width=40,  anchor="center")
        self._tree.column("Date/Time",   width=140)
        self._tree.column("Source",      width=130)
        self._tree.column("Drive",       width=90)
        self._tree.column("Dest Folder", width=140)
        self._tree.column("Files",       width=55,  anchor="e")
        self._tree.column("Size",        width=75,  anchor="e")
        self._tree.column("Status",      width=85,  anchor="center")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._tree.pack(side="left", fill="both", expand=True)
        self._tree.bind("<Double-1>", self._on_double_click)

        self._tree.tag_configure("completed", foreground="#44aa44")
        self._tree.tag_configure("error",     foreground="#cc3333")
        self._tree.tag_configure("cancelled", foreground="#cc8800")
        self._tree.tag_configure("running",   foreground="#2266cc")

        detail_frame = ttk.LabelFrame(self, text="File Details  (double-click a row above)")
        detail_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        detail_cols = ("File", "Action", "Size", "Error")
        self._detail_tree = ttk.Treeview(
            detail_frame, columns=detail_cols, show="headings", height=6
        )
        for c in detail_cols:
            self._detail_tree.heading(c, text=c)
        self._detail_tree.column("File",   width=380)
        self._detail_tree.column("Action", width=80, anchor="center")
        self._detail_tree.column("Size",   width=80, anchor="e")
        self._detail_tree.column("Error",  width=200)

        dsb = ttk.Scrollbar(detail_frame, orient="vertical", command=self._detail_tree.yview)
        self._detail_tree.configure(yscrollcommand=dsb.set)
        dsb.pack(side="right", fill="y")
        self._detail_tree.pack(side="left", fill="both", expand=True)

    def refresh(self):
        self._tree.delete(*self._tree.get_children())
        for h in self._history_repo.list_recent(limit=200):
            src_name = os.path.basename(h.source_path.rstrip("/\\")) or h.source_path
            dest_name = os.path.basename(h.dest_path.rstrip("/\\")) or h.dest_path
            self._tree.insert(
                "", "end",
                iid=str(h.id),
                values=(
                    h.id,
                    h.started_at[:19].replace("T", " "),
                    src_name,
                    h.drive_label or h.drive_serial,
                    dest_name,
                    h.files_copied,
                    _fmt_bytes(h.bytes_copied),
                    h.status.upper(),
                ),
                tags=(h.status,),
            )

    def _on_double_click(self, _event):
        sel = self._tree.selection()
        if not sel:
            return
        self._load_detail(int(sel[0]))

    def _load_detail(self, history_id: int):
        self._detail_tree.delete(*self._detail_tree.get_children())
        for e in self._history_repo.get_file_entries(history_id):
            self._detail_tree.insert(
                "", "end",
                values=(e["rel_path"], e["action"].upper(),
                        _fmt_bytes(e["size_bytes"]), e["error_msg"]),
            )

    def _clear_history(self):
        if messagebox.askyesno("Clear History",
                               "Delete all sync history records?", parent=self):
            self._history_repo.clear_all()
            self.refresh()
            self._detail_tree.delete(*self._detail_tree.get_children())
