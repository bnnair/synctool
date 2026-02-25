"""Windows-specific platform helpers."""
import ctypes
import os
import sys
from typing import Optional


def get_volume_serial(path: str) -> Optional[str]:
    """Return the volume serial number as a hex string for the drive containing *path*.

    Returns None on failure (non-Windows, permission error, etc.).
    """
    if sys.platform != "win32":
        return None
    try:
        # GetVolumeInformation needs the root of the drive
        root = os.path.splitdrive(path)[0] + "\\"
        volume_name = ctypes.create_unicode_buffer(261)
        serial = ctypes.c_ulong(0)
        max_comp_len = ctypes.c_ulong(0)
        fs_flags = ctypes.c_ulong(0)
        fs_name = ctypes.create_unicode_buffer(261)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            root,
            volume_name, 261,
            ctypes.byref(serial),
            ctypes.byref(max_comp_len),
            ctypes.byref(fs_flags),
            fs_name, 261,
        )
        if ok:
            return f"{serial.value:08X}"
    except Exception:
        pass
    return None


def get_volume_label(path: str) -> str:
    """Return the volume label for the drive containing *path*."""
    if sys.platform != "win32":
        return ""
    try:
        root = os.path.splitdrive(path)[0] + "\\"
        volume_name = ctypes.create_unicode_buffer(261)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            root,
            volume_name, 261,
            None, None, None, None, 0,
        )
        if ok:
            return volume_name.value
    except Exception:
        pass
    return ""


def get_drive_type(path: str) -> int:
    """Return Windows DRIVE_TYPE constant for the drive.

    2 = DRIVE_REMOVABLE, 3 = DRIVE_FIXED, 4 = DRIVE_REMOTE, 5 = DRIVE_CDROM, 6 = DRIVE_RAMDISK
    """
    if sys.platform != "win32":
        return 0
    try:
        root = os.path.splitdrive(path)[0] + "\\"
        return ctypes.windll.kernel32.GetDriveTypeW(root)
    except Exception:
        return 0


def list_drives() -> list[str]:
    """Return a list of drive root paths (e.g. ['C:\\', 'D:\\', 'E:\\'])."""
    if sys.platform != "win32":
        return []
    try:
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.kernel32.GetLogicalDriveStringsW(511, buf)
        drives = []
        idx = 0
        while buf[idx] != "\x00":
            start = idx
            while buf[idx] != "\x00":
                idx += 1
            drives.append(buf[start:idx])
            idx += 1
        return drives
    except Exception:
        return []


def drive_free_bytes(path: str) -> int:
    """Return free bytes available on the drive, 0 on error."""
    try:
        free = ctypes.c_ulonglong(0)
        total = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            os.path.splitdrive(path)[0] + "\\",
            ctypes.byref(free),
            ctypes.byref(total),
            None,
        )
        return free.value
    except Exception:
        return 0
