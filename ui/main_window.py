"""Main window: composes sync panel, history, and settings into a notebook."""
import tkinter as tk
from tkinter import ttk

from ui.sync_panel import SyncPanel
from ui.history_panel import HistoryPanel
from ui.settings_dialog import SettingsPanel
from ui.organize_panel import OrganizePanel
from core.drive_detector import DriveMonitor
from utils.config import DRIVE_POLL_INTERVAL_MS


class MainWindow(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._build_ui()
        self._drive_monitor = DriveMonitor(on_change=self._on_drives_changed)
        self._schedule_drive_poll()

    def _build_ui(self):
        self.pack(fill="both", expand=True)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=4, pady=4)

        self._sync_panel = SyncPanel(notebook)
        notebook.add(self._sync_panel, text="  Sync  ")

        self._history_panel = HistoryPanel(notebook)
        notebook.add(self._history_panel, text="  History  ")

        self._settings_panel = SettingsPanel(notebook)
        notebook.add(self._settings_panel, text="  Settings  ")

        self._organize_panel = OrganizePanel(notebook)
        notebook.add(self._organize_panel, text="  Organise  ")

        # Wire settings vars into sync panel so Start Sync reads them live
        self._sync_panel.set_settings_vars(
            use_hash_var=self._settings_panel.use_hash_var,
            delete_var=self._settings_panel.delete_var,
        )

        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._notebook = notebook

    def _on_tab_changed(self, _event):
        tab = self._notebook.select()
        name = self._notebook.tab(tab, "text").strip()
        if name == "History":
            self._history_panel.refresh()

    def _on_drives_changed(self, drives):
        self._sync_panel.refresh_drives()

    def _schedule_drive_poll(self):
        self._drive_monitor.check()
        self.after(DRIVE_POLL_INTERVAL_MS, self._schedule_drive_poll)
