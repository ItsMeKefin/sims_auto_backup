# Sims Auto Backup

Python script for Windows that watches for The Sims 4 / Die Sims 4 to close, then creates a timestamped zip backup of your save data.

By default it backs up:

- `%USERPROFILE%\Documents\Electronic Arts\Die Sims 4\Saves`

Backups are written to:

- `%USERPROFILE%\Documents\Sims 4 Backups`

## Requirements

- Windows
- Python 3.10 or newer
- No third-party Python packages

## Quick Start

Run this from the project folder:

```powershell
python auto_backup.py
```

Leave the window open while you play. When The Sims 4 process closes, the script creates a backup zip.

To test a backup immediately:

```powershell
python auto_backup.py --backup-now
```

## Configuration

Create a config file:

```powershell
python auto_backup.py --init-config
```

On Windows this writes:

```text
config.json
```

The config file is stored in the same folder as `auto_backup.py`.

Example config:

```json
{
  "game_process_names": [
    "TS4_x64.exe",
    "TS4_DX9_x64.exe",
    "TS4.exe"
  ],
  "sims_folder": "%USERPROFILE%\\Documents\\Electronic Arts\\Die Sims 4",
  "backup_destination": "%USERPROFILE%\\Documents\\Sims 4 Backups",
  "backup_folders": [
    "Saves"
  ],
  "poll_seconds": 10,
  "keep_last_backups": 20,
  "backup_when_started_if_game_is_not_running": false
}
```

Set `keep_last_backups` to `0` to keep every backup.

## Start Automatically With Windows

Use Task Scheduler:

1. Open **Task Scheduler**.
2. Choose **Create Basic Task**.
3. Trigger: **When I log on**.
4. Action: **Start a program**.
5. Program: your `python.exe` path.
6. Arguments: full path to `auto_backup.py`.
7. Start in: this project folder.

If the script opens and closes immediately, run `python auto_backup.py --backup-now` in PowerShell first to see the error.
