# install_shortcut.ps1
# Creates a SyncTool shortcut on the current user's Desktop.
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File install_shortcut.ps1

$ErrorActionPreference = "Stop"

# ── Resolve project root (the folder this script lives in) ──────────────────
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Pythonw     = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
$Script      = Join-Path $ProjectRoot "main.py"
$IconPath    = Join-Path $ProjectRoot "assets\icon.ico"
$Shortcut    = Join-Path ([Environment]::GetFolderPath("Desktop")) "SyncTool.lnk"

# ── Validate venv ────────────────────────────────────────────────────────────
if (-not (Test-Path $Pythonw)) {
    Write-Error "Virtual environment not found at '$Pythonw'.`nRun: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

# ── Create shortcut ──────────────────────────────────────────────────────────
$Shell = New-Object -ComObject WScript.Shell
$Lnk   = $Shell.CreateShortcut($Shortcut)

$Lnk.TargetPath       = $Pythonw
$Lnk.Arguments        = "`"$Script`""
$Lnk.WorkingDirectory = $ProjectRoot
$Lnk.Description      = "SyncTool — USB drive sync utility"

if (Test-Path $IconPath) {
    $Lnk.IconLocation = $IconPath
} else {
    # Fall back to the Python icon bundled with the venv
    $Lnk.IconLocation = $Pythonw + ",0"
}

$Lnk.Save()

Write-Host "Shortcut created: $Shortcut" -ForegroundColor Green
