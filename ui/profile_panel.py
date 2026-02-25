"""Left panel: profile management, source path, and destination drive selection."""
import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Callable, Optional

from core.drive_detector import get_all_non_cdrom_drives
from db.models import SyncProfile, ProfileDestination, DriveInfo
from db.repository import ProfileRepository
from ui.widgets import PathPicker, SectionLabel
from utils.config import MAX_DRIVES
from utils.platform_utils import get_volume_serial, get_volume_label


class ProfilePanel(ttk.Frame):
    """Manages profile selection and source / destination configuration."""

    def __init__(self, parent, on_profile_changed: Callable = None, **kwargs):
        super().__init__(parent, **kwargs)
        self._repo = ProfileRepository()
        self._profiles: list[SyncProfile] = []
        self._current_profile: Optional[SyncProfile] = None
        self._available_drives: list[DriveInfo] = []
        self._on_profile_changed = on_profile_changed

        # Drive destination slot variables
        self._dest_vars: list[tk.StringVar] = [tk.StringVar(value="") for _ in range(MAX_DRIVES)]

        self._build_ui()
        self._load_profiles()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # ---- Profile row ----
        SectionLabel(self, text="PROFILE").pack(fill="x", **pad)

        profile_row = ttk.Frame(self)
        profile_row.pack(fill="x", padx=8, pady=2)
        ttk.Label(profile_row, text="Name:", width=8, anchor="w").pack(side="left")
        self._profile_combo = ttk.Combobox(profile_row, state="readonly", width=20)
        self._profile_combo.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._profile_combo.bind("<<ComboboxSelected>>", self._on_profile_select)
        ttk.Button(profile_row, text="New", width=5, command=self._new_profile).pack(side="left", padx=2)
        ttk.Button(profile_row, text="Del", width=5, command=self._delete_profile).pack(side="left")

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=8, pady=6)

        # ---- Source ----
        SectionLabel(self, text="SOURCE").pack(fill="x", **pad)
        self._source_picker = PathPicker(self, label="Folder:")
        self._source_picker.pack(fill="x", padx=8, pady=2)
        self._source_picker.variable.trace_add("write", lambda *_: self._mark_dirty())

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=8, pady=6)

        # ---- Destinations ----
        SectionLabel(self, text="DESTINATION DRIVES (up to 3)").pack(fill="x", **pad)

        self._dest_combos: list[ttk.Combobox] = []
        for i in range(MAX_DRIVES):
            row = ttk.Frame(self)
            row.pack(fill="x", padx=8, pady=2)
            ttk.Label(row, text=f"Drive {i+1}:", width=8, anchor="w").pack(side="left")
            combo = ttk.Combobox(row, textvariable=self._dest_vars[i], state="readonly", width=22)
            combo.pack(side="left", fill="x", expand=True)
            combo.bind("<<ComboboxSelected>>", lambda e, idx=i: self._on_dest_select(idx))
            self._dest_combos.append(combo)

        ttk.Button(self, text="Refresh Drives", command=self.refresh_drives).pack(
            padx=8, pady=8, anchor="w"
        )

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=8, pady=2)

        # ---- Save profile button ----
        self._save_btn = ttk.Button(self, text="Save Profile", command=self._save_profile)
        self._save_btn.pack(padx=8, pady=6, anchor="w")

    # ------------------------------------------------------------------
    # Drive management
    # ------------------------------------------------------------------

    def refresh_drives(self):
        self._available_drives = get_all_non_cdrom_drives()
        drive_options = ["-- None --"] + [d.display_name for d in self._available_drives]
        for combo in self._dest_combos:
            current = combo.get()
            combo["values"] = drive_options
            if current not in drive_options:
                combo.set("-- None --")

    def _on_dest_select(self, idx: int):
        self._mark_dirty()

    # ------------------------------------------------------------------
    # Profile CRUD
    # ------------------------------------------------------------------

    def _load_profiles(self):
        self._profiles = self._repo.list_all()
        names = [p.name for p in self._profiles]
        self._profile_combo["values"] = names
        if self._profiles:
            self._profile_combo.current(0)
            self._load_profile(self._profiles[0])
        self.refresh_drives()

    def _on_profile_select(self, _event=None):
        idx = self._profile_combo.current()
        if 0 <= idx < len(self._profiles):
            self._load_profile(self._profiles[idx])

    def _load_profile(self, profile: SyncProfile):
        self._current_profile = profile
        self._source_picker.path = profile.source_path
        self.refresh_drives()

        # Reset destination combos
        for combo, var in zip(self._dest_combos, self._dest_vars):
            var.set("-- None --")

        # Fill destinations from profile
        for dest in profile.destinations:
            slot_idx = dest.slot - 1  # slot is 1-based
            if 0 <= slot_idx < MAX_DRIVES:
                # Find matching drive by serial
                matched = next(
                    (d for d in self._available_drives if d.serial == dest.drive_serial),
                    None,
                )
                if matched:
                    self._dest_vars[slot_idx].set(matched.display_name)
                else:
                    # Drive not currently connected — show serial
                    label = dest.drive_label or dest.drive_serial
                    self._dest_vars[slot_idx].set(f"[offline] {label}")

        if self._on_profile_changed:
            self._on_profile_changed(profile)

    def _new_profile(self):
        name = simpledialog.askstring("New Profile", "Enter profile name:", parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        profile = SyncProfile(id=None, name=name, source_path="")
        try:
            profile = self._repo.save(profile)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not create profile:\n{exc}", parent=self)
            return
        self._profiles.append(profile)
        self._profile_combo["values"] = [p.name for p in self._profiles]
        self._profile_combo.current(len(self._profiles) - 1)
        self._load_profile(profile)

    def _delete_profile(self):
        if not self._current_profile or self._current_profile.id is None:
            return
        if not messagebox.askyesno(
            "Delete Profile",
            f"Delete profile '{self._current_profile.name}'?",
            parent=self,
        ):
            return
        self._repo.delete(self._current_profile.id)
        self._profiles = [p for p in self._profiles if p.id != self._current_profile.id]
        names = [p.name for p in self._profiles]
        self._profile_combo["values"] = names
        self._current_profile = None
        if self._profiles:
            self._profile_combo.current(0)
            self._load_profile(self._profiles[0])
        else:
            self._profile_combo.set("")
            self._source_picker.path = ""
            for var in self._dest_vars:
                var.set("-- None --")

    def _mark_dirty(self):
        pass  # Could add a * to title later

    def _save_profile(self):
        if not self._current_profile:
            messagebox.showinfo("No Profile", "Create or select a profile first.", parent=self)
            return
        src = self._source_picker.path
        if not src or not os.path.isdir(src):
            messagebox.showerror("Invalid Source", "Please select a valid source folder.", parent=self)
            return

        self._current_profile.source_path = src
        self._repo.save(self._current_profile)

        # Save destinations
        dests: list[ProfileDestination] = []
        for i, (var, combo) in enumerate(zip(self._dest_vars, self._dest_combos)):
            selected = var.get()
            if selected and selected != "-- None --" and not selected.startswith("[offline]"):
                drive = next(
                    (d for d in self._available_drives if d.display_name == selected),
                    None,
                )
                if drive:
                    dest_path = os.path.join(drive.letter, "SyncTool_Backup")
                    dests.append(ProfileDestination(
                        id=None,
                        profile_id=self._current_profile.id,
                        drive_serial=drive.serial,
                        drive_label=drive.label,
                        dest_path=dest_path,
                        slot=i + 1,
                    ))

        self._repo.save_destinations(self._current_profile.id, dests)
        # Reload to get IDs
        self._current_profile = self._repo.get_by_id(self._current_profile.id)
        messagebox.showinfo("Saved", "Profile saved.", parent=self)

        if self._on_profile_changed:
            self._on_profile_changed(self._current_profile)

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    @property
    def current_profile(self) -> Optional[SyncProfile]:
        return self._current_profile

    def get_active_destinations(self) -> list[ProfileDestination]:
        """Return the destinations currently selected in the UI (unsaved state too)."""
        if not self._current_profile:
            return []
        dests: list[ProfileDestination] = []
        for i, (var, combo) in enumerate(zip(self._dest_vars, self._dest_combos)):
            selected = var.get()
            if selected and selected != "-- None --" and not selected.startswith("[offline]"):
                drive = next(
                    (d for d in self._available_drives if d.display_name == selected),
                    None,
                )
                if drive:
                    dest_path = os.path.join(drive.letter, "SyncTool_Backup")
                    dests.append(ProfileDestination(
                        id=None,
                        profile_id=self._current_profile.id,
                        drive_serial=drive.serial,
                        drive_label=drive.label,
                        dest_path=dest_path,
                        slot=i + 1,
                    ))
        return dests
