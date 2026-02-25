"""Plain dataclasses used across db, core, and ui layers."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DriveInfo:
    letter: str          # e.g. "E:\\"
    label: str
    serial: str          # hex volume serial
    drive_type: int      # Windows DRIVE_TYPE constant
    free_bytes: int = 0

    @property
    def display_name(self) -> str:
        label = self.label or "No Label"
        letter = self.letter.rstrip("\\")
        return f"{letter} ({label})"

    @property
    def is_removable(self) -> bool:
        return self.drive_type == 2

    @property
    def is_fixed(self) -> bool:
        return self.drive_type == 3


@dataclass
class SyncDrive:
    """One selected destination drive."""
    drive_serial: str
    drive_label: str
    drive_letter: str   # e.g. "E:\\"
    dest_root: str      # root folder on the drive to sync into, e.g. "E:\\SyncBackup"


@dataclass
class DriveJob:
    """All sync work destined for a single drive (multiple source folders)."""
    drive: SyncDrive
    sources: list          # list[str] of source folder paths
    direction: str         # source_to_dest | dest_to_source | bidirectional
    use_hash: bool
    delete_extraneous: bool


@dataclass
class FileStat:
    rel_path: str
    size_bytes: int
    mtime_ns: int
    sha256: Optional[str] = None


@dataclass
class SyncPlan:
    to_copy: list = field(default_factory=list)      # (src_abs, dst_abs, rel_path, size_bytes)
    to_delete: list = field(default_factory=list)    # dst_abs strings
    conflicts: list = field(default_factory=list)    # (src_abs, conflict_dst_abs, rel_path, size_bytes)
    to_skip: list = field(default_factory=list)      # (src_abs, dst_abs, rel_path, size_bytes)


@dataclass
class FileState:
    """Last-known file state after a successful sync (for bidirectional diffing)."""
    id: Optional[int]
    source_path: str    # the source root folder
    drive_serial: str   # 'SOURCE' or volume serial
    rel_path: str
    size_bytes: int
    mtime_ns: int
    sha256: Optional[str]


@dataclass
class SyncHistory:
    id: Optional[int]
    source_path: str
    drive_serial: str
    drive_label: str
    dest_path: str
    started_at: str
    finished_at: Optional[str]
    status: str             # running | completed | cancelled | error
    files_copied: int = 0
    bytes_copied: int = 0
    error_message: str = ""
