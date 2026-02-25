"""Main sync panel: source list, destination drives, direction, controls, progress, log."""
import os
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

from core.drive_detector import get_all_non_cdrom_drives
from core.parallel_sync import ParallelSyncManager
from db.models import DriveJob, SyncDrive
from db.repository import SettingsRepository
from ui.widgets import SectionLabel, ProgressRow
from utils import events
from utils.config import MAX_DRIVES, UI_QUEUE_POLL_MS
from utils.logger import get_logger

log = get_logger("synctool.ui")

_FEED_MAX_ROWS = 2000

_ACTION_COLORS = {
    "copy":     "#44cc44",
    "conflict": "#ffaa00",
    "delete":   "#ff5555",
    "error":    "#ff5555",
    "skip":     "#888888",
}


class SyncPanel(ttk.Frame):
    """Single panel containing all sync controls."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._manager: Optional[ParallelSyncManager] = None
        self._available_drives = []
        self._settings_repo = SettingsRepository()
        self._start_time: Optional[float] = None
        self._timer_id: Optional[str] = None
        self._progress_rows = []
        self._serial_to_row: dict = {}
        self._serial_to_label: dict = {}

        self._dest_drive_vars = [tk.StringVar(value="") for _ in range(MAX_DRIVES)]
        self._dest_path_vars = [tk.StringVar(value="") for _ in range(MAX_DRIVES)]
        self._direction_var = tk.StringVar(value="source_to_dest")

        # Wired in from SettingsPanel after construction
        self._use_hash_var = tk.BooleanVar(value=False)
        self._delete_var = tk.BooleanVar(value=False)

        self._build_ui()
        self._schedule_queue_drain()
        self._load_last_session()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # ---- Left pane: all controls ----
        left = ttk.Frame(paned)
        paned.add(left, weight=3)

        top = ttk.Frame(left)
        top.pack(fill="both", expand=False, padx=6, pady=6)
        self._build_source_section(top)
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        self._build_dest_section(top)

        ttk.Separator(left, orient="horizontal").pack(fill="x", padx=6, pady=2)
        self._build_controls(left)
        ttk.Separator(left, orient="horizontal").pack(fill="x", padx=6, pady=2)
        self._build_progress(left)
        self._build_log(left)

        # ---- Right pane: live file feed ----
        right = ttk.Frame(paned)
        paned.add(right, weight=2)
        self._build_file_feed(right)

    def _build_source_section(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(side="left", fill="both", expand=True)

        SectionLabel(frame, text="SOURCE FOLDERS / FILES").pack(anchor="w", pady=(0, 4))

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill="both", expand=True)

        self._source_listbox = tk.Listbox(
            list_frame, selectmode="extended", height=8,
            font=("Consolas", 9), activestyle="none",
            bg="#f8f8f8", relief="solid", borderwidth=1,
        )
        vsb = ttk.Scrollbar(list_frame, orient="vertical",   command=self._source_listbox.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self._source_listbox.xview)
        self._source_listbox.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self._source_listbox.pack(side="left", fill="both", expand=True)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(4, 0))
        ttk.Button(btn_frame, text="+ Add Folder", command=self._add_folder).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="+ Add Files",  command=self._add_files).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="- Remove",     command=self._remove_selected).pack(side="left")

    def _build_dest_section(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(side="left", fill="both", expand=True)

        SectionLabel(frame, text="DESTINATION DRIVES (up to 3)").pack(anchor="w", pady=(0, 4))

        self._dest_combos = []
        self._dest_path_entries = []

        for i in range(MAX_DRIVES):
            slot = ttk.LabelFrame(frame, text=f"Drive {i + 1}")
            slot.pack(fill="x", pady=3)

            r1 = ttk.Frame(slot)
            r1.pack(fill="x", padx=4, pady=2)
            ttk.Label(r1, text="Drive:", width=6, anchor="w").pack(side="left")
            combo = ttk.Combobox(r1, textvariable=self._dest_drive_vars[i],
                                 state="readonly", width=24)
            combo.pack(side="left", fill="x", expand=True)
            combo.bind("<<ComboboxSelected>>", lambda e, idx=i: self._on_drive_selected(idx))
            self._dest_combos.append(combo)

            r2 = ttk.Frame(slot)
            r2.pack(fill="x", padx=4, pady=2)
            ttk.Label(r2, text="Into:", width=6, anchor="w").pack(side="left")
            entry = ttk.Entry(r2, textvariable=self._dest_path_vars[i])
            entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
            ttk.Button(r2, text="...", width=3,
                       command=lambda idx=i: self._browse_dest(idx)).pack(side="left")
            self._dest_path_entries.append(entry)

        ttk.Button(frame, text="Refresh Drives", command=self.refresh_drives).pack(
            anchor="w", pady=(6, 0)
        )

    def _build_controls(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=8, pady=4)

        SectionLabel(row, text="Direction:").pack(side="left", padx=(0, 8))
        for label, value in [
            ("Source \u2192 Drives", "source_to_dest"),
            ("Drives \u2192 Source", "dest_to_source"),
            ("Bidirectional",        "bidirectional"),
        ]:
            ttk.Radiobutton(row, text=label, value=value,
                            variable=self._direction_var).pack(side="left", padx=6)

        self._elapsed_var = tk.StringVar(value="")
        ttk.Label(row, textvariable=self._elapsed_var, foreground="#666666",
                  font=("", 8)).pack(side="right", padx=8)

        btn_row = ttk.Frame(parent)
        btn_row.pack(fill="x", padx=8, pady=(2, 4))
        self._start_btn = ttk.Button(
            btn_row, text="  \u25b6  Start Sync", command=self._start_sync, width=16
        )
        self._start_btn.pack(side="left", padx=(0, 6))
        self._cancel_btn = ttk.Button(
            btn_row, text="  \u2716  Cancel", command=self._cancel_sync,
            state="disabled", width=12
        )
        self._cancel_btn.pack(side="left")

    def _build_progress(self, parent):
        SectionLabel(parent, text="PROGRESS").pack(anchor="w", padx=8, pady=(4, 2))
        prog_frame = ttk.Frame(parent)
        prog_frame.pack(fill="x", padx=8)
        for i in range(MAX_DRIVES):
            row = ProgressRow(prog_frame, drive_label=f"Drive {i + 1}")
            row.pack(fill="x", pady=2)
            self._progress_rows.append(row)

    def _build_log(self, parent):
        SectionLabel(parent, text="LOG").pack(anchor="w", padx=8, pady=(6, 2))
        log_frame = ttk.Frame(parent)
        log_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._log_text = tk.Text(
            log_frame, height=5, state="disabled", wrap="none",
            font=("Consolas", 8), bg="#1e1e1e", fg="#d4d4d4",
        )
        vsb = ttk.Scrollbar(log_frame, orient="vertical",   command=self._log_text.yview)
        hsb = ttk.Scrollbar(log_frame, orient="horizontal", command=self._log_text.xview)
        self._log_text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self._log_text.pack(side="left", fill="both", expand=True)
        self._log_text.tag_configure("warning", foreground="#ffcc44")
        self._log_text.tag_configure("error",   foreground="#ff5555")
        self._log_text.tag_configure("info",    foreground="#88ddff")

    def _build_file_feed(self, parent):
        SectionLabel(parent, text="LIVE FILE FEED").pack(anchor="w", padx=8, pady=(6, 2))

        feed_frame = ttk.Frame(parent)
        feed_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        cols = ("Action", "Drive", "File", "Size")
        self._feed_tree = ttk.Treeview(
            feed_frame, columns=cols, show="headings",
            selectmode="none", height=30,
        )
        self._feed_tree.heading("Action", text="Action")
        self._feed_tree.heading("Drive",  text="Drive")
        self._feed_tree.heading("File",   text="File")
        self._feed_tree.heading("Size",   text="Size")
        self._feed_tree.column("Action", width=72,  anchor="center", stretch=False)
        self._feed_tree.column("Drive",  width=70,  anchor="center", stretch=False)
        self._feed_tree.column("File",   width=260, anchor="w")
        self._feed_tree.column("Size",   width=72,  anchor="e",      stretch=False)

        # Colour tags per action type
        self._feed_tree.tag_configure("copy",     foreground="#44cc44")
        self._feed_tree.tag_configure("conflict", foreground="#ffaa00")
        self._feed_tree.tag_configure("delete",   foreground="#ff5555")
        self._feed_tree.tag_configure("error",    foreground="#ff5555")
        self._feed_tree.tag_configure("skip",     foreground="#888888")

        vsb = ttk.Scrollbar(feed_frame, orient="vertical", command=self._feed_tree.yview)
        self._feed_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._feed_tree.pack(side="left", fill="both", expand=True)

        self._feed_count = 0

    # ------------------------------------------------------------------
    # Source management
    # ------------------------------------------------------------------

    def _add_folder(self):
        path = filedialog.askdirectory(title="Select Source Folder", mustexist=True)
        if path:
            path = os.path.normpath(path)
            if path not in self._source_listbox.get(0, "end"):
                self._source_listbox.insert("end", path)

    def _add_files(self):
        paths = filedialog.askopenfilenames(title="Select Source Files")
        existing = set(self._source_listbox.get(0, "end"))
        for p in paths:
            p = os.path.normpath(p)
            if p not in existing:
                self._source_listbox.insert("end", p)
                existing.add(p)

    def _remove_selected(self):
        for idx in reversed(self._source_listbox.curselection()):
            self._source_listbox.delete(idx)

    # ------------------------------------------------------------------
    # Drive management
    # ------------------------------------------------------------------

    def refresh_drives(self):
        self._available_drives = get_all_non_cdrom_drives()
        options = ["-- None --"] + [d.display_name for d in self._available_drives]
        for i, combo in enumerate(self._dest_combos):
            current = self._dest_drive_vars[i].get()
            combo["values"] = options
            if current not in options:
                self._dest_drive_vars[i].set("-- None --")
                self._dest_path_vars[i].set("")

    def _on_drive_selected(self, idx: int):
        selected = self._dest_drive_vars[idx].get()
        if selected == "-- None --":
            self._dest_path_vars[idx].set("")
            return
        drive = next((d for d in self._available_drives if d.display_name == selected), None)
        if drive and not self._dest_path_vars[idx].get():
            self._dest_path_vars[idx].set(os.path.join(drive.letter, "SyncBackup"))

    def _browse_dest(self, idx: int):
        initial = self._dest_path_vars[idx].get() or "/"
        path = filedialog.askdirectory(title="Select Destination Folder", initialdir=initial)
        if path:
            self._dest_path_vars[idx].set(os.path.normpath(path))

    # ------------------------------------------------------------------
    # Sync control
    # ------------------------------------------------------------------

    def _get_sources(self) -> list:
        return list(self._source_listbox.get(0, "end"))

    def _get_drives(self) -> list:
        drives = []
        for i in range(MAX_DRIVES):
            selected = self._dest_drive_vars[i].get()
            dest_root = self._dest_path_vars[i].get().strip()
            if not selected or selected == "-- None --" or not dest_root:
                continue
            drive = next(
                (d for d in self._available_drives if d.display_name == selected), None
            )
            if drive:
                drives.append(SyncDrive(
                    drive_serial=drive.serial,
                    drive_label=drive.label,
                    drive_letter=drive.letter,
                    dest_root=dest_root,
                ))
        return drives

    def _start_sync(self):
        if self._manager and self._manager.is_running:
            return

        sources = self._get_sources()
        if not sources:
            messagebox.showerror("No Sources", "Add at least one source folder or file.")
            return
        for s in sources:
            if not os.path.exists(s):
                messagebox.showerror("Invalid Source", f"Path does not exist:\n{s}")
                return

        drives = self._get_drives()
        if not drives:
            messagebox.showerror(
                "No Destinations",
                "Select at least one destination drive and set a destination folder.",
            )
            return

        direction = self._direction_var.get()
        use_hash = self._use_hash_var.get()
        delete_extraneous = self._delete_var.get()

        try:
            self._settings_repo.save_session(sources, drives, direction, use_hash, delete_extraneous)
        except Exception:
            pass

        jobs = [
            DriveJob(drive=drv, sources=sources, direction=direction,
                     use_hash=use_hash, delete_extraneous=delete_extraneous)
            for drv in drives
        ]

        # Reset progress UI and feed
        self._serial_to_row.clear()
        self._serial_to_label.clear()
        for i, (job, row) in enumerate(zip(jobs, self._progress_rows)):
            letter = job.drive.drive_letter.rstrip("\\")
            label = f"Drive {i+1}: {letter} ({job.drive.drive_label})"
            row.set_drive_label(label)
            row.reset()
            row.set_status("Waiting...", "#888888")
            self._serial_to_row[job.drive.drive_serial] = row
            self._serial_to_label[job.drive.drive_serial] = letter
        for row in self._progress_rows[len(jobs):]:
            row.set_drive_label("---")
            row.reset()

        self._feed_clear()
        self._log_clear()
        self._start_btn.config(state="disabled")
        self._cancel_btn.config(state="normal")
        self._start_time = time.time()
        self._tick_elapsed()

        self._manager = ParallelSyncManager()
        self._manager.start(jobs=jobs, on_all_done=self._on_all_done)

    def _cancel_sync(self):
        if self._manager:
            self._manager.cancel()
        self._cancel_btn.config(state="disabled")

    def _on_all_done(self):
        self.after(0, self._on_sync_finished)

    def _on_sync_finished(self):
        self._start_btn.config(state="normal")
        self._cancel_btn.config(state="disabled")
        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None

    # ------------------------------------------------------------------
    # Queue drain
    # ------------------------------------------------------------------

    def _schedule_queue_drain(self):
        self.after(UI_QUEUE_POLL_MS, self._drain_queue)

    def _drain_queue(self):
        try:
            for event in events.drain():
                self._handle_event(event)
        finally:
            self._schedule_queue_drain()

    def _handle_event(self, event):
        if isinstance(event, events.ProgressEvent):
            row = self._serial_to_row.get(event.drive_serial)
            if row:
                row.update_progress(
                    event.files_done, event.files_total,
                    event.bytes_done, event.bytes_total,
                    event.current_file,
                )
        elif isinstance(event, events.FileActionEvent):
            self._feed_insert(event)
        elif isinstance(event, events.SyncCompleteEvent):
            row = self._serial_to_row.get(event.drive_serial)
            if row:
                color = {"completed": "#44cc44",
                         "cancelled": "#ffaa00",
                         "error":     "#ff5555"}.get(event.status, "#888888")
                mb = event.bytes_copied / 1024 / 1024
                row.set_status(
                    f"{event.status.upper()}  {event.files_copied} files  {mb:.1f} MB",
                    color,
                )
        elif isinstance(event, events.LogEvent):
            self._log_append(event.message, event.level)

    # ------------------------------------------------------------------
    # File feed
    # ------------------------------------------------------------------

    def _feed_insert(self, event: "events.FileActionEvent"):
        drive_label = self._serial_to_label.get(event.drive_serial, event.drive_serial[:6])
        action = event.action.upper()
        size_str = _fmt_bytes(event.size_bytes) if event.size_bytes else ""
        tag = event.action.lower()

        # Trim to cap
        if self._feed_count >= _FEED_MAX_ROWS:
            first = self._feed_tree.get_children()[0]
            self._feed_tree.delete(first)
            self._feed_count -= 1

        self._feed_tree.insert(
            "", "end",
            values=(action, drive_label, event.rel_path, size_str),
            tags=(tag,),
        )
        self._feed_count += 1
        # Auto-scroll to bottom
        self._feed_tree.yview_moveto(1.0)

    def _feed_clear(self):
        self._feed_tree.delete(*self._feed_tree.get_children())
        self._feed_count = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log_append(self, message: str, level: str = "info"):
        self._log_text.config(state="normal")
        self._log_text.insert("end", message + "\n", level)
        self._log_text.see("end")
        self._log_text.config(state="disabled")

    def _log_clear(self):
        self._log_text.config(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.config(state="disabled")

    def _tick_elapsed(self):
        if self._start_time:
            elapsed = int(time.time() - self._start_time)
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self._elapsed_var.set(f"Elapsed: {h:02d}:{m:02d}:{s:02d}")
            self._timer_id = self.after(1000, self._tick_elapsed)

    def _load_last_session(self):
        try:
            session = self._settings_repo.load_session()
        except Exception:
            return
        self.refresh_drives()
        for src in session.get("sources", []):
            if os.path.exists(src):
                self._source_listbox.insert("end", src)
        self._direction_var.set(session.get("direction", "source_to_dest"))
        for i, drv in enumerate(session.get("drives", [])[:MAX_DRIVES]):
            matched = next(
                (d for d in self._available_drives if d.serial == drv.drive_serial), None
            )
            if matched:
                self._dest_drive_vars[i].set(matched.display_name)
                self._dest_path_vars[i].set(drv.dest_root)

    def set_settings_vars(self, use_hash_var: tk.BooleanVar, delete_var: tk.BooleanVar):
        """Called by MainWindow to wire settings panel vars into this panel."""
        self._use_hash_var = use_hash_var
        self._delete_var = delete_var


def _fmt_bytes(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024**3:.1f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024**2:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"
