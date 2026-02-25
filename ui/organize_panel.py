"""Organize tab: segregates images/videos into year/month folders by EXIF date."""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

from core.image_organizer import FileEvent, OrganizeResult, organize_folder
from ui.widgets import SectionLabel
from utils.logger import get_logger

log = get_logger("synctool.organize")

_FEED_MAX_ROWS = 2000


class OrganizePanel(ttk.Frame):
    """Tab for segregating images/videos into year/month folders by EXIF date."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._cancel_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._event_queue: queue.Queue = queue.Queue()
        self._feed_count = 0
        self._build_ui()
        self._poll_queue()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned)
        paned.add(left, weight=2)
        self._build_controls(left)

        right = ttk.Frame(paned)
        paned.add(right, weight=3)
        self._build_feed(right)

    def _build_controls(self, parent):
        # Source folder
        SectionLabel(parent, text="SOURCE FOLDER").pack(anchor="w", padx=8, pady=(8, 2))
        src_row = ttk.Frame(parent)
        src_row.pack(fill="x", padx=8, pady=(0, 6))
        self._src_var = tk.StringVar()
        ttk.Entry(src_row, textvariable=self._src_var).pack(
            side="left", fill="x", expand=True, padx=(0, 4)
        )
        ttk.Button(src_row, text="...", width=3, command=self._browse_src).pack(side="left")

        # Destination folder
        SectionLabel(parent, text="DESTINATION FOLDER").pack(anchor="w", padx=8, pady=(6, 2))
        dst_row = ttk.Frame(parent)
        dst_row.pack(fill="x", padx=8, pady=(0, 6))
        self._dst_var = tk.StringVar()
        ttk.Entry(dst_row, textvariable=self._dst_var).pack(
            side="left", fill="x", expand=True, padx=(0, 4)
        )
        ttk.Button(dst_row, text="...", width=3, command=self._browse_dst).pack(side="left")

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=8, pady=8)

        # Mode
        SectionLabel(parent, text="MODE").pack(anchor="w", padx=8, pady=(2, 4))
        self._mode_var = tk.StringVar(value="copy")
        ttk.Radiobutton(
            parent, text="Copy  (keep originals in source)",
            value="copy", variable=self._mode_var,
        ).pack(anchor="w", padx=20, pady=2)
        ttk.Radiobutton(
            parent, text="Move  (remove originals from source)",
            value="move", variable=self._mode_var,
        ).pack(anchor="w", padx=20, pady=2)

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=8, pady=8)

        # Buttons
        btn_row = ttk.Frame(parent)
        btn_row.pack(fill="x", padx=8)
        self._start_btn = ttk.Button(
            btn_row, text="  \u25b6  Start Organize",
            command=self._start, width=18,
        )
        self._start_btn.pack(side="left", padx=(0, 6))
        self._cancel_btn = ttk.Button(
            btn_row, text="  \u2716  Cancel",
            command=self._cancel, state="disabled", width=12,
        )
        self._cancel_btn.pack(side="left")

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=8, pady=8)

        # Progress
        SectionLabel(parent, text="PROGRESS").pack(anchor="w", padx=8, pady=(2, 4))
        self._prog_bar = ttk.Progressbar(parent, mode="determinate", maximum=100)
        self._prog_bar.pack(fill="x", padx=8, pady=(0, 2))
        self._prog_label_var = tk.StringVar(value="")
        ttk.Label(
            parent, textvariable=self._prog_label_var,
            foreground="#666666", font=("", 8),
        ).pack(anchor="w", padx=8)

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=8, pady=8)

        # Summary
        SectionLabel(parent, text="SUMMARY").pack(anchor="w", padx=8, pady=(2, 2))
        self._summary_var = tk.StringVar(value="Ready.")
        ttk.Label(
            parent, textvariable=self._summary_var,
            wraplength=300, foreground="#555555",
        ).pack(anchor="w", padx=8, pady=(2, 8))

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=8, pady=4)

        # Output structure diagram
        SectionLabel(parent, text="OUTPUT STRUCTURE").pack(anchor="w", padx=8, pady=(6, 2))
        ttk.Label(
            parent,
            text=(
                "dest/\n"
                "  2024/\n"
                "    2024-01/   \u2190 EXIF date Jan 2024\n"
                "    2024-12/   \u2190 EXIF date Dec 2024\n"
                "  2025/\n"
                "    2025-06/   \u2190 EXIF date Jun 2025\n"
                "  misc/        \u2190 no EXIF metadata found"
            ),
            font=("Consolas", 8), foreground="#888888", justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 8))

        # Supported formats note
        ttk.Label(
            parent,
            text=(
                "Supported: JPEG, PNG, TIFF, HEIC, RAW (CR2/NEF/ARW/DNG…),\n"
                "WebP, BMP, GIF, MP4, MOV, AVI, MKV, WMV and more.\n"
                "Videos always go to misc/ (no EXIF)."
            ),
            font=("", 8), foreground="#888888", justify="left", wraplength=300,
        ).pack(anchor="w", padx=8, pady=(0, 8))

    def _build_feed(self, parent):
        SectionLabel(parent, text="LIVE FILE FEED").pack(anchor="w", padx=8, pady=(8, 2))

        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        cols = ("Status", "Dest Folder", "Source File")
        self._feed = ttk.Treeview(
            frame, columns=cols, show="headings",
            selectmode="none", height=30,
        )
        self._feed.heading("Status",      text="Status")
        self._feed.heading("Dest Folder", text="Dest Folder")
        self._feed.heading("Source File", text="Source File")
        self._feed.column("Status",      width=90,  anchor="center", stretch=False)
        self._feed.column("Dest Folder", width=140, anchor="w",      stretch=False)
        self._feed.column("Source File", width=320, anchor="w")

        self._feed.tag_configure("organized", foreground="#44cc44")
        self._feed.tag_configure("misc",      foreground="#ffaa00")
        self._feed.tag_configure("error",     foreground="#ff5555")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._feed.yview)
        self._feed.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._feed.pack(side="left", fill="both", expand=True)

    # ------------------------------------------------------------------
    # Browse
    # ------------------------------------------------------------------

    def _browse_src(self):
        path = filedialog.askdirectory(title="Select Source Folder with Images/Videos")
        if path:
            self._src_var.set(os.path.normpath(path))

    def _browse_dst(self):
        path = filedialog.askdirectory(title="Select Destination Folder for Organised Files")
        if path:
            self._dst_var.set(os.path.normpath(path))

    # ------------------------------------------------------------------
    # Start / Cancel
    # ------------------------------------------------------------------

    def _start(self):
        if self._thread and self._thread.is_alive():
            return

        # Quick Pillow check before doing anything else
        try:
            from PIL import Image as _pil  # noqa: F401
        except ImportError:
            messagebox.showerror(
                "Missing Dependency",
                "Pillow is required for the Organise feature.\n\n"
                "Install it by running:\n"
                "    pip install Pillow\n\n"
                "Then restart the application.",
                parent=self,
            )
            return

        source = self._src_var.get().strip()
        dest   = self._dst_var.get().strip()

        if not source or not os.path.isdir(source):
            messagebox.showerror(
                "Invalid Source", "Please select a valid source folder.", parent=self
            )
            return
        if not dest:
            messagebox.showerror(
                "No Destination", "Please select a destination folder.", parent=self
            )
            return
        if os.path.normpath(source) == os.path.normpath(dest):
            messagebox.showerror(
                "Same Folder",
                "Source and destination must be different folders.", parent=self
            )
            return

        move = self._mode_var.get() == "move"
        if move and not messagebox.askyesno(
            "Confirm Move",
            "Files will be MOVED from the source folder.\nThis cannot be undone. Continue?",
            parent=self,
        ):
            return

        # Reset UI
        self._cancel_event.clear()
        self._feed_clear()
        self._summary_var.set("Running\u2026")
        self._prog_bar["value"] = 0
        self._prog_label_var.set("")
        self._start_btn.config(state="disabled")
        self._cancel_btn.config(state="normal")

        self._thread = threading.Thread(
            target=self._worker,
            args=(source, dest, move),
            daemon=True,
            name="organize",
        )
        self._thread.start()

    def _cancel(self):
        self._cancel_event.set()
        self._cancel_btn.config(state="disabled")

    def _worker(self, source: str, dest: str, move: bool):
        try:
            result = organize_folder(
                source=source,
                dest=dest,
                move=move,
                cancel_event=self._cancel_event,
                event_queue=self._event_queue,
            )
            self._event_queue.put(("done", result))
        except Exception as exc:
            log.exception("Organizer error: %s", exc)
            r = OrganizeResult(cancelled=False)
            r.errors = 1
            self._event_queue.put(("done", r))

    # ------------------------------------------------------------------
    # Queue polling (main thread)
    # ------------------------------------------------------------------

    def _poll_queue(self):
        try:
            while True:
                item = self._event_queue.get_nowait()
                if isinstance(item, FileEvent):
                    self._on_file_event(item)
                elif isinstance(item, tuple):
                    kind = item[0]
                    if kind == "progress":
                        self._on_progress(item[1], item[2])
                    elif kind == "done":
                        self._on_done(item[1])
                    elif kind == "fatal":
                        self._on_fatal(item[1])
        except queue.Empty:
            pass
        finally:
            self.after(200, self._poll_queue)

    def _on_file_event(self, evt: FileEvent):
        tag = evt.status  # "organized" | "misc" | "error"
        label = evt.status.upper()
        if evt.status == "error":
            label = f"ERROR"

        if self._feed_count >= _FEED_MAX_ROWS:
            self._feed.delete(self._feed.get_children()[0])
            self._feed_count -= 1

        self._feed.insert(
            "", "end",
            values=(label, evt.dest_folder, evt.rel_src),
            tags=(tag,),
        )
        self._feed_count += 1
        self._feed.yview_moveto(1.0)

    def _on_progress(self, done: int, total: int):
        pct = int(done / total * 100) if total > 0 else 0
        self._prog_bar["value"] = pct
        self._prog_label_var.set(f"{done} / {total} files")

    def _on_fatal(self, msg: str):
        """Called when a fatal error (e.g. Pillow not installed) aborts the run."""
        self._start_btn.config(state="normal")
        self._cancel_btn.config(state="disabled")
        self._summary_var.set("Failed — see error dialog.")
        messagebox.showerror("Organise Error", msg, parent=self)

    def _on_done(self, result: OrganizeResult):
        self._start_btn.config(state="normal")
        self._cancel_btn.config(state="disabled")
        if not result.cancelled:
            self._prog_bar["value"] = 100

        status = "Cancelled." if result.cancelled else "Complete."
        parts = [f"{result.organized} organised into year/month folders"]
        if result.misc:
            parts.append(f"{result.misc} sent to misc/")
        if result.errors:
            parts.append(f"{result.errors} errors")
        self._summary_var.set(f"{status}  " + ",  ".join(parts) + ".")

    def _feed_clear(self):
        self._feed.delete(*self._feed.get_children())
        self._feed_count = 0
