# SyncTool

A Windows desktop application for syncing files and folders to external USB drives. Built with Python and Tkinter, it supports parallel sync to multiple drives, bidirectional synchronization, and image organization by EXIF capture date.

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Standalone Executable](#standalone-executable-recommended)
- [Installation from Source](#installation-from-source)
- [Running from Source](#running-from-source)
- [Usage](#usage)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [File Descriptions](#file-descriptions)
- [Design Patterns](#design-patterns)
- [Database Schema](#database-schema)
- [Dependencies](#dependencies)

---

## Features

- **Parallel sync** — sync to up to 3 USB drives simultaneously via `ThreadPoolExecutor`
- **Parallel scanning** — top-level subdirectories are scanned concurrently (8 worker threads); significantly faster on SSDs and NVMe for large trees
- **Parallel copying** — up to 4 files copied concurrently per drive job; especially effective for folders with many small files
- **Smart diffing** — three-level comparison: size → modification timestamp → optional SHA-256 hash
- **Atomic copies** — writes to a `.synctmp` file, then renames; safe if the drive is disconnected mid-copy
- **Bidirectional sync** — three-way comparison using stored per-file states; conflicts are renamed with a timestamp suffix (no data loss)
- **Mirror mode** — optionally deletes files on the destination that no longer exist in the source
- **Live progress** — per-drive progress bars, a real-time file feed, and a color-coded log
- **Drive identity** — tracks drives by volume serial number, not drive letter (stable across re-plugs)
- **Persistent session** — last-used sources, drives, and settings are restored from SQLite on startup
- **Sync history** — every sync run and each individual file action are recorded in the database
- **Image organizer** — sorts photos and videos into `YYYY/YYYY-MM/` folders by EXIF capture date (30+ image and 20+ video formats)
- **Windows 11 theme** — uses `sv_ttk` Sun Valley theme automatically; falls back to native Windows theme if unavailable

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.10 or later |
| OS | Windows 10 / Windows 11 |

---

## Standalone Executable (Recommended)

The recommended way to run SyncTool is as a self-contained Windows executable — no Python installation required on the target machine.

The `SyncTool.spec` PyInstaller spec file is committed to the repository for reproducible builds.

### 1. Set up the build environment (once)

```bash
git clone https://github.com/bnnair/synctool.git
cd synctool
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install pyinstaller
```

### 2. Build the executable

```bash
# Using the committed spec file (recommended — reproducible)
.venv\Scripts\pyinstaller SyncTool.spec

# Or build from scratch
.venv\Scripts\pyinstaller --noconsole --onefile --name SyncTool main.py
```

| Flag | Effect |
|---|---|
| `--noconsole` | No terminal window (GUI-only) |
| `--onefile` | Bundles everything into a single `SyncTool.exe` |
| `--name SyncTool` | Output file name |

The executable is written to `dist\SyncTool.exe`.

### 3. Add an icon (optional)

Place a 256×256 `.ico` file at `assets\icon.ico`, then rebuild:

```bash
.venv\Scripts\pyinstaller --noconsole --onefile --name SyncTool --icon assets\icon.ico main.py
```

### 4. Install to a permanent location

The `data\` folder (SQLite database and log file) is created **next to the executable** on first launch. Do not place `SyncTool.exe` directly on the Desktop — move it to a permanent folder first so the data folder has a stable home.

**Recommended install folder:** `C:\Users\<you>\AppData\Local\SyncTool\`

```powershell
# Create the install folder and copy the exe there
$dest = "$env:LOCALAPPDATA\SyncTool"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item "dist\SyncTool.exe" -Destination $dest
Write-Host "Installed to $dest"
```

After this, `SyncTool.exe` lives at `C:\Users\<you>\AppData\Local\SyncTool\SyncTool.exe` and all data files will be written to `C:\Users\<you>\AppData\Local\SyncTool\data\`.

### 5. Create a Desktop shortcut

```powershell
$exePath = "$env:LOCALAPPDATA\SyncTool\SyncTool.exe"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("$env:USERPROFILE\Desktop\SyncTool.lnk")
$sc.TargetPath       = $exePath
$sc.WorkingDirectory = "$env:LOCALAPPDATA\SyncTool"
$sc.Description      = "SyncTool — USB drive sync utility"
$sc.Save()
Write-Host "Shortcut created on Desktop."
```

Double-click **SyncTool** on the Desktop to launch. No console window, no Python required.

> **Note:** `dist\` and `build\` are excluded from git. Every developer builds their own local copy from the committed spec.

---

## Installation from Source

For development or running directly with Python — requires Python 3.10+ on the machine.

### 1. Clone the repository

```bash
git clone https://github.com/bnnair/synctool.git
cd synctool
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# Command Prompt
.venv\Scripts\activate

# PowerShell
.venv\Scripts\Activate.ps1

# Git Bash
source .venv/Scripts/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** If `Pillow` is not installed, the Organise tab will show an error when used — all sync functionality continues to work normally.

---

## Running from Source

```bash
# Terminal (with log output in console)
python main.py

# No console window
.venv\Scripts\pythonw.exe main.py
```

The `data\synctool.db` and `data\synctool.log` files are created automatically on the first launch.

---

## Usage

### Sync Tab

1. **Add sources** — click **+ Folder** or **+ File** to add one or more source paths
2. **Select drives** — click **Refresh Drives**; all connected removable drives appear in the Drive 1 / 2 / 3 rows; tick the checkbox next to each drive you want to sync to
3. **Set destination path** — enter the sub-folder on the drive where files will be placed (e.g. `Backup\Documents`)
4. **Choose sync direction**:
   - **→** Source → Drives — copies from your sources to the USB drives
   - **←** Drives → Source — copies from the USB drives back to your source folders
   - **↔** Bidirectional — syncs changes in both directions; conflicts are preserved with a timestamp suffix
5. **Start** — click **▶ Start Sync**
6. **Cancel** — click **✖ Cancel** at any time; the current file finishes, then the job stops gracefully

### History Tab

- Lists the 200 most recent sync runs (time, source, drive, status, files copied/skipped/deleted)
- Double-click any row to expand and view the per-file action log for that run
- **Clear history** removes all records from the database

### Settings Tab

| Setting | Default | Description |
|---|---|---|
| SHA-256 hash comparison | Off | Adds a hash check after size and timestamp match — more accurate on FAT32/exFAT drives where timestamps differ |
| Mirror mode | Off | Deletes files on the destination that no longer exist in the source |
| Conflict resolution | Keep both | For bidirectional sync: `keep both` renames the conflicting file with a timestamp; `prefer source` or `prefer destination` overwrites without keeping both |
| Vacuum database | — | Reclaims unused space from the SQLite file |

### Organise Tab

1. Select the **Source** folder containing images/videos
2. Select the **Destination** folder where the organized tree will be written
3. Choose **Copy** or **Move**
4. Click **Start**

Output structure:
```
dest/
  2024/
    2024-01/   ← files with EXIF date in January 2024
    2024-12/
  2025/
    2025-06/
  misc/        ← files with no readable date metadata
```

---

## Architecture

SyncTool is organized into four independent layers with a clean dependency direction:

```
ui/          ← presentation layer (Tkinter)
  │
  ├─ core/   ← sync and file-system logic
  ├─ db/     ← persistence (SQLite)
  └─ utils/  ← cross-cutting concerns (config, events, logging, platform)
```

**Thread model:**

```
Main thread (Tkinter event loop)
  │
  ├── DriveMonitor (daemon thread)             ← polls for drive changes every 2 s
  │
  └── ParallelSyncManager
        ├── drive-worker 1 → SyncEngine
        │     ├── scanner pool  (8 threads)   ← parallel subdirectory scan
        │     └── copy pool     (4 threads)   ← parallel file copy
        ├── drive-worker 2 → SyncEngine
        │     ├── scanner pool  (8 threads)
        │     └── copy pool     (4 threads)
        └── drive-worker 3 → SyncEngine
              ├── scanner pool  (8 threads)
              └── copy pool     (4 threads)

All worker threads → put events into queue.Queue
Main thread        → drains queue every 300 ms via root.after() → updates UI
```

**Data flow:**

```
User configures sources + drives
        ↓
ParallelSyncManager.start()
        ↓
SyncEngine (per drive):
  Scanner.scan(source)  →  {rel_path: FileStat}
  Scanner.scan(dest)    →  {rel_path: FileStat}
        ↓
  Comparator.build_plan()  →  SyncPlan
  (size diff → mtime diff → optional SHA-256 diff)
        ↓
  Execute plan:
    file_ops.atomic_copy()   (copy actions)
    os.remove()              (delete actions, mirror mode)
    FileStateRepository.save()
        ↓
  HistoryRepository.save()
        ↓
Events → queue → UI updates (progress bars, file feed, log)
```

---

## Project Structure

```
synctool/
├── main.py                    # Entry point — sets up logging, DB, and launches App
├── requirements.txt           # pip dependencies
├── README.md
│
├── core/                      # Sync and file-system logic (no UI imports)
│   ├── __init__.py
│   ├── comparator.py          # Three-level file diff → SyncPlan
│   ├── drive_detector.py      # Windows drive enumeration and monitoring
│   ├── file_ops.py            # Atomic copy with retry and progress callback
│   ├── image_organizer.py     # EXIF-based image/video folder organizer
│   ├── parallel_sync.py       # ThreadPoolExecutor across up to 3 drives
│   ├── scanner.py             # Fast recursive directory tree walker
│   └── sync_engine.py         # Orchestrates one source → destination sync job
│
├── db/                        # Persistence layer
│   ├── __init__.py
│   ├── database.py            # SQLite connection (WAL mode, thread-safe lock)
│   ├── models.py              # Dataclasses: DriveInfo, SyncPlan, FileStat, etc.
│   └── repository.py          # CRUD: settings, file states, sync history
│
├── ui/                        # Tkinter GUI (depends on core, db, utils)
│   ├── __init__.py
│   ├── app.py                 # Root Tk window, theme selection, window centering
│   ├── history_panel.py       # History tab with expandable per-file details
│   ├── main_window.py         # Notebook layout; wires panels together
│   ├── organize_panel.py      # Organise tab UI
│   ├── profile_panel.py       # Profile management panel (partial integration)
│   ├── settings_dialog.py     # Settings tab
│   ├── sync_panel.py          # Main sync controls, progress bars, live feed, log
│   └── widgets.py             # Reusable widgets: PathPicker, ProgressRow, SectionLabel
│
├── utils/                     # Cross-cutting utilities (no UI or core imports)
│   ├── __init__.py
│   ├── config.py              # App-wide constants (paths, timeouts, chunk size)
│   ├── events.py              # Thread-safe event bus (queue.Queue)
│   ├── logger.py              # Rotating file + console logger
│   └── platform_utils.py     # Windows API: volume serial, drive type, free space
│
└── data/                      # Runtime data (auto-created)
    ├── synctool.db            # SQLite database
    └── synctool.log           # Rotating log file (5 MB × 3 backups)
```

---

## File Descriptions

### `main.py`

Entry point. Adds the project root to `sys.path`, calls `setup_logging()` and `initialize()` (DB schema creation), then instantiates and runs the Tkinter `App`.

---

### `core/scanner.py`

Walks a directory tree with `os.scandir()` recursively. Returns a `dict[str, FileStat]` keyed by relative path.

**Parallel scanning:** the root level is scanned inline; each top-level subdirectory is then submitted to a `ThreadPoolExecutor` (up to `SCAN_WORKERS=8` threads) as an independent recursive walk. Every worker has its own `visited` set, keeping circular-link detection correct. On SSDs and NVMe drives this typically cuts scan time by 3–6× for wide or deep trees.

Detects circular symlinks and Windows NTFS junction points. Also handles individual file selection (non-directory sources).

### `core/comparator.py`

Builds a `SyncPlan` from two `dict[str, FileStat]` trees (source and destination).

**One-way sync algorithm:**
1. Files only in source → `to_copy`
2. Files in both, with differences → `to_copy` (re-copy)
3. Files only in destination → `to_delete` (mirror mode) or `to_skip`

**Difference check order:**
1. Size mismatch → different
2. `mtime_ns` mismatch → different
3. SHA-256 hash mismatch → different (only when hash mode is enabled)

**Bidirectional sync algorithm:**
- Compares source and destination against the last known `FileState` (stored after each sync)
- Classifies each file as: unchanged / modified on source / modified on dest / added / deleted / conflict
- Conflicts (modified on both sides) are renamed with a UTC timestamp suffix unless the user has set a preference

### `core/file_ops.py`

Atomic file copy:
1. Write to `<destination>.synctmp`
2. Copy metadata (timestamps, permissions) via `shutil.copystat`
3. Rename to the final destination path

Retries up to 3 times on `OSError` with a 1-second delay. Accepts a `progress_cb(bytes_written)` callback and a `cancel_event` for graceful interruption. Chunk size is 4 MB (configurable via `COPY_CHUNK_SIZE` in `utils/config.py`).

### `core/sync_engine.py`

Orchestrates one source → destination sync job:
1. Scans both trees
2. Calls `Comparator.build_plan()`
3. Executes the plan — copy and conflict ops run in a `ThreadPoolExecutor` (up to `COPY_WORKERS=4` concurrent files); deletes and skips remain sequential
4. Saves `FileState` records for future bidirectional comparisons
5. Records a `SyncHistory` entry with timing and per-file results
6. Emits `ProgressEvent`, `FileActionEvent`, `SyncCompleteEvent`, and `LogEvent` to the shared event queue

Shared progress counters (`files_done`, `bytes_done`) are protected by a `threading.Lock`. A `_CancelledError` raised in any worker sets the cancel event and the pool drains gracefully.

### `core/parallel_sync.py`

Manages concurrent sync across multiple drives using `concurrent.futures.ThreadPoolExecutor` (max 3 workers). Each worker runs a `SyncEngine` for one drive. Cancellation is coordinated via a shared `threading.Event`.

### `core/drive_detector.py`

Uses Windows API functions via `ctypes` (`GetVolumeInformation`, `GetDriveType`) to list all mounted drives and classify them as removable, fixed, CD-ROM, or network. Identifies drives by volume serial number so that drive-letter changes (e.g. after re-plugging) do not break saved configurations. Includes a background polling monitor.

### `core/image_organizer.py`

Reads EXIF metadata (via Pillow) from images and video files and sorts them into `dest/YYYY/YYYY-MM/` folders. Files without readable metadata go to `dest/misc/`. Supports 30+ image formats (JPEG, PNG, TIFF, HEIC, RAW variants) and 20+ video formats (MP4, MOV, MKV, AVI, WebM). Operates in a background thread; emits progress via a `queue.Queue`.

---

### `db/database.py`

Manages a single shared SQLite connection with:
- WAL (Write-Ahead Logging) mode for concurrent read safety
- `PRAGMA foreign_keys = ON`
- A `threading.Lock` around every statement

`initialize()` creates the schema on first run.

### `db/models.py`

Dataclasses used throughout the application:

| Class | Purpose |
|---|---|
| `DriveInfo` | Live drive metadata (letter, label, serial, type, free bytes) |
| `SyncDrive` | User-selected destination drive (serial, label, letter, dest_root) |
| `DriveJob` | All work for one drive (list of sources, direction, settings flags) |
| `FileStat` | Scanned file metadata (rel_path, size, mtime_ns) |
| `SyncPlan` | Planned actions (to_copy, to_delete, conflicts, to_skip) |
| `FileState` | Stored post-sync file state for bidirectional diffing |
| `SyncHistory` | Record of a completed sync run (source, drive, status, stats) |

### `db/repository.py`

Three repository classes:

- **`SettingsRepository`** — key-value store for app settings; also persists and restores the last session (sources, drives, direction)
- **`FileStateRepository`** — stores and queries `FileState` rows keyed by `(source_path, drive_serial, rel_path)`; used by the bidirectional comparator
- **`HistoryRepository`** — writes `SyncHistory` and per-file detail rows; reads history for the History tab

---

### `ui/app.py`

Root `Tk` window. Attempts to apply the `sv_ttk` (Sun Valley) dark/light theme; falls back to `vista` or `xpnative` on older Windows. Centers the window to 75% of the screen. Loads the application icon if present.

### `ui/main_window.py`

Composes the top-level layout: a `ttk.Notebook` with four tabs (Sync, History, Settings, Organise). Starts the drive monitor and wires drive-change callbacks to the sync panel.

### `ui/sync_panel.py`

The main tab. Contains:
- Source list (folders and individual files) with Add/Remove buttons
- Three drive rows (checkbox, label, destination path entry, progress bar with stats)
- Sync direction toggle (→ / ← / ↔)
- Start / Cancel buttons with elapsed time display
- Real-time file action feed (action, drive letter, file path, file size)
- Color-coded log output (INFO blue, WARNING orange, ERROR red)

Drains the event queue every 300 ms via `root.after()`.

### `ui/history_panel.py`

Displays the 200 most recent sync runs in a `ttk.Treeview`. Double-clicking a row fetches and shows per-file details. Status cells are color-coded (completed = green, error = red, cancelled = orange).

### `ui/organize_panel.py`

UI for the Organise tab. Validates that Pillow is installed before starting. Runs `image_organizer.organize_folder()` in a background thread; polls a queue for progress updates.

### `ui/settings_dialog.py`

Settings tab with checkboxes for hash mode, mirror mode, and a radio group for conflict resolution. Includes a **Vacuum** button to compact the database file.

### `ui/profile_panel.py`

Partial implementation of a named-profile system. Not fully wired into the main flow (the main Sync tab uses a session-based approach instead). Included for future development.

### `ui/widgets.py`

Shared Tkinter widgets:
- **`PathPicker`** — label + entry + Browse button for selecting a directory
- **`ProgressRow`** — drive label + `ttk.Progressbar` + stats label
- **`SectionLabel`** — bold section header
- **`Separator`** — horizontal `ttk.Separator`

---

### `utils/config.py`

Application-wide constants:

| Constant | Value | Purpose |
|---|---|---|
| `DB_PATH` | `data/synctool.db` | SQLite database location |
| `LOG_PATH` | `data/synctool.log` | Log file location |
| `COPY_CHUNK_SIZE` | 4 MB | Read/write chunk for copy and hash |
| `COPY_RETRY_COUNT` | 3 | Retry attempts on `OSError` |
| `COPY_RETRY_DELAY` | 1 s | Delay between retries |
| `SCAN_WORKERS` | 8 | Parallel threads for directory tree scanning |
| `COPY_WORKERS` | 4 | Parallel threads for file copy within one drive job |
| `DRIVE_POLL_INTERVAL_MS` | 2000 ms | Drive monitor polling interval |
| `UI_QUEUE_POLL_MS` | 300 ms | Event queue drain interval |
| `APP_WIDTH` / `APP_HEIGHT` | 920×640 | Initial window dimensions |

### `utils/events.py`

Thread-safe event bus built on `queue.Queue`. Event types:

| Class | Fields | Purpose |
|---|---|---|
| `ProgressEvent` | `drive, files_done, files_total, bytes_done, bytes_total` | Updates progress bars |
| `FileActionEvent` | `drive, action, rel_path, size` | Populates the live file feed |
| `SyncCompleteEvent` | `drive, status, stats` | Signals job completion |
| `LogEvent` | `level, message` | Appends to the log output widget |

Module-level `put(event)` and `drain()` functions are used by sync threads and the UI respectively.

### `utils/logger.py`

Configures a `logging.Logger` with:
- `RotatingFileHandler` — 5 MB per file, 3 backup files, written to `data/synctool.log`
- `StreamHandler` — console output

### `utils/platform_utils.py`

Thin wrappers around Windows API calls via `ctypes`:

| Function | Win32 API | Returns |
|---|---|---|
| `get_volume_serial(drive)` | `GetVolumeInformationW` | Hex serial string |
| `get_volume_label(drive)` | `GetVolumeInformationW` | Volume label string |
| `get_drive_type(drive)` | `GetDriveTypeW` | `"removable"`, `"fixed"`, `"cdrom"`, `"network"`, `"unknown"` |
| `list_drives()` | `GetLogicalDriveStringsW` | List of drive letter strings (`["C:\\", "D:\\", ...]`) |
| `drive_free_bytes(drive)` | `GetDiskFreeSpaceExW` | Free bytes as `int` |

---

## Design Patterns

| Pattern | Where used |
|---|---|
| **Layered architecture** | `utils` → `db`/`core` → `ui`; no upward imports |
| **Repository pattern** | `db/repository.py` isolates all SQL from business logic |
| **Dataclass models** | `db/models.py` — plain, immutable data containers |
| **Event bus** | `utils/events.py` — sync threads publish; UI main thread consumes via `root.after()` |
| **Atomic write** | `file_ops.py` — write to `.synctmp`, then rename; safe on power loss or disconnection |
| **Three-way merge** | `comparator.py` — bidirectional sync uses stored `FileState` as the base revision |
| **ThreadPoolExecutor** | `parallel_sync.py` (across drives), `scanner.py` (subdirectory scan), `sync_engine.py` (per-file copy) |
| **Cooperative cancellation** | `threading.Event` passed into every sync thread and copy worker; checked between chunks |
| **WAL + mutex** | `db/database.py` — SQLite WAL mode + `threading.Lock` for thread-safe access |
| **Polling monitor** | `drive_detector.py` — background thread polls for drive changes every 2 s |

---

## Database Schema

```sql
-- Application settings and last-session state
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Per-file state stored after each sync (used by bidirectional comparator)
CREATE TABLE IF NOT EXISTS file_states (
    source_path  TEXT NOT NULL,
    drive_serial TEXT NOT NULL,
    rel_path     TEXT NOT NULL,
    size         INTEGER,
    mtime_ns     INTEGER,
    file_hash    TEXT,
    synced_at    TEXT,
    PRIMARY KEY (source_path, drive_serial, rel_path)
);

-- Sync job records
CREATE TABLE IF NOT EXISTS sync_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path   TEXT,
    drive_serial  TEXT,
    drive_label   TEXT,
    drive_letter  TEXT,
    direction     TEXT,
    status        TEXT,
    started_at    TEXT,
    finished_at   TEXT,
    files_copied  INTEGER DEFAULT 0,
    files_skipped INTEGER DEFAULT 0,
    files_deleted INTEGER DEFAULT 0,
    files_error   INTEGER DEFAULT 0,
    bytes_copied  INTEGER DEFAULT 0
);

-- Per-file detail rows for each history entry
CREATE TABLE IF NOT EXISTS sync_history_files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    history_id INTEGER REFERENCES sync_history(id) ON DELETE CASCADE,
    action     TEXT,
    rel_path   TEXT,
    size       INTEGER,
    error      TEXT
);
```

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `pywin32` | ≥ 311 | Windows drive enumeration (`GetVolumeInformation`, `GetDriveType`, etc.) |
| `sv_ttk` | ≥ 2.6.1 | Windows 11 Sun Valley theme for Tkinter (optional — auto falls back) |
| `Pillow` | ≥ 12.0.0 | EXIF metadata reading for the Organise tab |

All other functionality uses the Python standard library: `tkinter`, `sqlite3`, `concurrent.futures`, `threading`, `queue`, `hashlib`, `shutil`, `os`, `ctypes`, `logging`.
