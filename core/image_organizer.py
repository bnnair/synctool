"""Segregates images and videos into year/month folders by EXIF capture date.

Folder structure produced:
    dest/
      2024/
        2024-01/   <- files whose EXIF DateTimeOriginal falls in Jan 2024
        2024-12/
      2025/
        2025-06/
      misc/        <- files with no readable EXIF / metadata date
"""
import os
import queue
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from utils.logger import get_logger

log = get_logger("synctool.organizer")

# -----------------------------------------------------------------------
# Supported extensions
# -----------------------------------------------------------------------

IMAGE_EXTENSIONS = frozenset({
    ".jpg", ".jpeg",
    ".tif", ".tiff",
    ".heic", ".heif",
    ".raw", ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2",
    ".orf", ".rw2", ".raf", ".dng", ".pef", ".srw",
    ".png", ".webp", ".bmp", ".gif",
})

VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".m4v", ".mov", ".qt",
    ".avi", ".wmv", ".flv",
    ".mkv", ".webm",
    ".3gp", ".3g2",
    ".mpg", ".mpeg", ".m2ts", ".mts", ".ts",
    ".vob", ".ogv",
})

MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


# -----------------------------------------------------------------------
# Data classes
# -----------------------------------------------------------------------

@dataclass
class FileEvent:
    """Emitted for each processed file; consumed by the UI."""
    rel_src: str       # path relative to source root
    dest_folder: str   # path relative to dest root, e.g. "2024/2024-03" or "misc"
    status: str        # "organized" | "misc" | "error"
    error: str = ""


@dataclass
class OrganizeResult:
    total: int = 0
    organized: int = 0
    misc: int = 0
    errors: int = 0
    cancelled: bool = False


# -----------------------------------------------------------------------
# EXIF / metadata extraction
# -----------------------------------------------------------------------

# Pillow EXIF tag IDs.
# DateTimeOriginal (36867) and DateTimeDigitized (36868) are stored inside
# the Exif sub-IFD, pointed to by tag 0x8769 in IFD0.
# DateTime (306) lives directly in IFD0.
_EXIF_IFD_POINTER = 0x8769
_EXIF_IFD_TAG_IDS = (
    36867,  # DateTimeOriginal  — shutter-press time (most reliable)
    36868,  # DateTimeDigitized — digitisation time
)
_IFD0_TAG_IDS = (
    306,    # DateTime — file last-modified (least reliable, last resort)
)


def _exif_date(filepath: str) -> Optional[datetime]:
    """Read the best available capture date from Pillow EXIF data.

    Assumes PIL is already importable (caller must verify).
    Logs and returns None on any per-file error.
    """
    from PIL import Image
    try:
        with Image.open(filepath) as img:
            exif = img.getexif()
            if not exif:
                log.debug("No EXIF data in %s", filepath)
                return None

            # 1. Exif sub-IFD: DateTimeOriginal / DateTimeDigitized
            exif_ifd = exif.get_ifd(_EXIF_IFD_POINTER)
            for tag_id in _EXIF_IFD_TAG_IDS:
                dt = _parse_exif_str(exif_ifd.get(tag_id))
                if dt:
                    return dt

            # 2. IFD0: DateTime (last resort)
            for tag_id in _IFD0_TAG_IDS:
                dt = _parse_exif_str(exif.get(tag_id))
                if dt:
                    return dt

            log.debug("EXIF present but no usable date tag in %s", filepath)

    except Exception as exc:
        log.debug("EXIF read error for %s: %s", filepath, exc)
    return None


def _parse_exif_str(raw) -> Optional[datetime]:
    """Parse an EXIF datetime string '%Y:%m:%d %H:%M:%S', return None if invalid."""
    if not raw or not isinstance(raw, str):
        return None
    if raw.startswith("0000") or raw.startswith("    "):
        return None
    try:
        return datetime.strptime(raw[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def extract_date(filepath: str) -> Optional[datetime]:
    """Return the capture datetime from EXIF, or None.

    Assumes PIL is importable (checked once by organize_folder).
    """
    if os.path.splitext(filepath)[1].lower() in IMAGE_EXTENSIONS:
        return _exif_date(filepath)
    return None


# -----------------------------------------------------------------------
# Path helpers
# -----------------------------------------------------------------------

def _dest_folder(dest_root: str, dt: Optional[datetime]) -> str:
    if dt:
        return os.path.join(dest_root, str(dt.year), f"{dt.year}-{dt.month:02d}")
    return os.path.join(dest_root, "misc")


def _unique_path(folder: str, filename: str) -> str:
    """Return a non-conflicting path, appending _2/_3/… if needed."""
    candidate = os.path.join(folder, filename)
    if not os.path.exists(candidate):
        return candidate
    base, ext = os.path.splitext(filename)
    n = 2
    while True:
        candidate = os.path.join(folder, f"{base}_{n}{ext}")
        if not os.path.exists(candidate):
            return candidate
        n += 1


# -----------------------------------------------------------------------
# Main organizer
# -----------------------------------------------------------------------

def organize_folder(
    source: str,
    dest: str,
    move: bool,
    cancel_event: threading.Event,
    event_queue: queue.Queue,
) -> OrganizeResult:
    """Walk *source*, categorise every media file by EXIF date, copy/move to *dest*.

    Puts FileEvent objects and ("progress", done, total) or ("fatal", msg)
    tuples into *event_queue* for the UI to consume.
    """
    # ---- Verify Pillow is installed before touching a single file ----
    try:
        from PIL import Image as _pil_img  # noqa: F401
        log.debug("Pillow version: %s", _pil_img.__version__ if hasattr(_pil_img, "__version__") else "unknown")
    except ImportError:
        event_queue.put(("fatal",
            "Pillow is not installed.\n\n"
            "Install it by running:\n"
            "    pip install Pillow\n\n"
            "Then restart the application."))
        return OrganizeResult()

    result = OrganizeResult()

    # Phase 1: collect all media files so progress is accurate
    all_files: list[str] = []
    for dirpath, _dirs, filenames in os.walk(source, followlinks=True):
        for fname in filenames:
            if os.path.splitext(fname)[1].lower() in MEDIA_EXTENSIONS:
                all_files.append(os.path.join(dirpath, fname))

    result.total = len(all_files)
    event_queue.put(("progress", 0, result.total))

    # Phase 2: process each file
    for i, src_abs in enumerate(all_files):
        if cancel_event.is_set():
            result.cancelled = True
            break

        rel = os.path.relpath(src_abs, source).replace("\\", "/")
        filename = os.path.basename(src_abs)

        try:
            dt = extract_date(src_abs)
            folder = _dest_folder(dest, dt)
            os.makedirs(folder, exist_ok=True)
            dst_abs = _unique_path(folder, filename)

            if move:
                shutil.move(src_abs, dst_abs)
            else:
                shutil.copy2(src_abs, dst_abs)

            dest_rel = os.path.relpath(folder, dest).replace("\\", "/")
            status = "organized" if dt else "misc"
            if dt:
                result.organized += 1
            else:
                result.misc += 1

            event_queue.put(FileEvent(rel_src=rel, dest_folder=dest_rel, status=status))

        except Exception as exc:
            log.error("Failed to process %s: %s", src_abs, exc)
            result.errors += 1
            event_queue.put(FileEvent(
                rel_src=rel, dest_folder="—",
                status="error", error=str(exc),
            ))

        event_queue.put(("progress", i + 1, result.total))

    return result
