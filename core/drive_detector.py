"""Enumerate available drives on Windows, including USB/removable drives."""
import os
import sys
from typing import Callable, Optional
from db.models import DriveInfo
from utils.platform_utils import (
    list_drives, get_volume_serial, get_volume_label,
    get_drive_type, drive_free_bytes,
)


def _build_drive_info(root: str) -> Optional[DriveInfo]:
    """Build a DriveInfo for the given root path (e.g. 'E:\\')."""
    try:
        drive_type = get_drive_type(root)
        if drive_type == 0:
            return None  # unknown
        serial = get_volume_serial(root) or f"UNKNOWN_{root[0]}"
        label = get_volume_label(root)
        free = drive_free_bytes(root)
        return DriveInfo(
            letter=root,
            label=label,
            serial=serial,
            drive_type=drive_type,
            free_bytes=free,
        )
    except Exception:
        return None


def get_all_drives() -> list[DriveInfo]:
    """Return DriveInfo for every mounted drive (fixed + removable)."""
    drives = []
    for root in list_drives():
        info = _build_drive_info(root)
        if info is not None:
            drives.append(info)
    return drives


def get_removable_drives() -> list[DriveInfo]:
    """Return only removable/USB drives."""
    return [d for d in get_all_drives() if d.is_removable]


def get_all_non_cdrom_drives() -> list[DriveInfo]:
    """Return fixed + removable drives (excludes CD-ROM and network)."""
    return [d for d in get_all_drives() if d.drive_type in (2, 3)]


class DriveMonitor:
    """Poll for drive changes and call *on_change* when the set changes."""

    def __init__(self, on_change: Callable[[list[DriveInfo]], None]):
        self._on_change = on_change
        self._last_serials: set[str] = set()
        self._running = False

    def check(self) -> None:
        """Call this periodically (e.g. via root.after). Fires on_change if drives changed."""
        drives = get_all_non_cdrom_drives()
        serials = {d.serial for d in drives}
        if serials != self._last_serials:
            self._last_serials = serials
            self._on_change(drives)
