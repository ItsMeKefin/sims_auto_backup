from __future__ import annotations

import argparse
import csv
import json
import logging
import subprocess
import sys
import time
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


DEFAULT_CONFIG_NAME = "config.json"
DEFAULT_GAME_PROCESSES = (
    "TS4_x64.exe",
    "TS4_DX9_x64.exe",
    "TS4.exe",
)
DEFAULT_BACKUP_FOLDERS = ("Saves", "Mods")
SIMS_FOLDER_CANDIDATES = (
    r"%USERPROFILE%\Documents\Electronic Arts\Die Sims 4",
    r"%USERPROFILE%\Documents\Electronic Arts\The Sims 4",
)


@dataclass
class BackupConfig:
    game_process_names: list[str] = field(default_factory=lambda: list(DEFAULT_GAME_PROCESSES))
    sims_folder: str = r"%USERPROFILE%\Documents\Electronic Arts\Die Sims 4"
    backup_destination: str = r"%USERPROFILE%\Documents\Sims 4 Backups"
    backup_folders: list[str] = field(default_factory=lambda: list(DEFAULT_BACKUP_FOLDERS))
    poll_seconds: int = 10
    keep_last_backups: int = 20
    backup_when_started_if_game_is_not_running: bool = False


def expand_path(path: str) -> Path:
    return Path(path).expanduser()


def expand_windows_env(path: str) -> Path:
    import os

    return expand_path(os.path.expandvars(path))


def resolve_sims_folder(configured_path: str) -> Path:
    sims_folder = expand_windows_env(configured_path)
    if sims_folder.exists():
        return sims_folder

    for candidate in SIMS_FOLDER_CANDIDATES:
        candidate_path = expand_windows_env(candidate)
        if candidate_path.exists():
            logging.info("Using detected Sims folder: %s", candidate_path)
            return candidate_path

    return sims_folder


def default_config_path() -> Path:
    return Path(__file__).resolve().parent / DEFAULT_CONFIG_NAME


def load_config(path: Path) -> BackupConfig:
    if not path.exists():
        return BackupConfig()

    with path.open("r", encoding="utf-8") as config_file:
        raw_config = json.load(config_file)

    defaults = asdict(BackupConfig())
    defaults.update(raw_config)
    return BackupConfig(**defaults)


def write_default_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Config already exists: {path}")

    with path.open("w", encoding="utf-8") as config_file:
        json.dump(asdict(BackupConfig()), config_file, indent=2)
        config_file.write("\n")


def running_process_names() -> set[str]:
    if sys.platform != "win32":
        return set()

    result = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        check=False,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "tasklist failed")

    names: set[str] = set()
    for row in csv.reader(result.stdout.splitlines()):
        if not row:
            continue
        names.add(row[0].casefold())
    return names


def is_game_running(process_names: list[str]) -> bool:
    process_name_set = {process.casefold() for process in process_names}
    return bool(running_process_names().intersection(process_name_set))


def add_folder_to_zip(zip_file: zipfile.ZipFile, folder: Path, archive_root: str) -> int:
    files_added = 0
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        zip_file.write(path, Path(archive_root) / path.relative_to(folder))
        files_added += 1
    return files_added


def create_backup(config: BackupConfig) -> Path:
    sims_folder = resolve_sims_folder(config.sims_folder)
    backup_destination = expand_windows_env(config.backup_destination)

    if not sims_folder.exists():
        raise FileNotFoundError(f"Sims folder does not exist: {sims_folder}")

    backup_destination.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = backup_destination / f"sims4-backup_{timestamp}.zip"

    files_added = 0
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
        for folder_name in config.backup_folders:
            source = sims_folder / folder_name
            if not source.exists():
                logging.warning("Skipping missing folder: %s", source)
                continue
            files_added += add_folder_to_zip(zip_file, source, folder_name)

    if files_added == 0:
        backup_path.unlink(missing_ok=True)
        raise RuntimeError("No files were backed up. Check backup_folders in the config.")

    logging.info("Created backup: %s (%s files)", backup_path, files_added)
    prune_old_backups(backup_destination, config.keep_last_backups)
    return backup_path


def prune_old_backups(backup_destination: Path, keep_last_backups: int) -> None:
    if keep_last_backups <= 0:
        return

    backups = sorted(
        backup_destination.glob("sims4-backup_*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[keep_last_backups:]:
        logging.info("Removing old backup: %s", old_backup)
        old_backup.unlink()


def watch_for_game_close(config: BackupConfig) -> None:
    logging.info("Watching for: %s", ", ".join(config.game_process_names))
    logging.info("Sims folder: %s", resolve_sims_folder(config.sims_folder))
    logging.info("Backup destination: %s", expand_windows_env(config.backup_destination))

    was_running = is_game_running(config.game_process_names)

    if not was_running and config.backup_when_started_if_game_is_not_running:
        create_backup(config)

    while True:
        running = is_game_running(config.game_process_names)
        if was_running and not running:
            logging.info("Game closed. Starting backup.")
            try:
                create_backup(config)
            except Exception:
                logging.exception("Backup failed")

        was_running = running
        time.sleep(max(config.poll_seconds, 1))


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Back up The Sims 4 save data and mods after the game closes."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Path to the JSON config file.",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Write a default config file and exit.",
    )
    parser.add_argument(
        "--backup-now",
        action="store_true",
        help="Create one backup immediately and exit.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print debug logging.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    if sys.platform != "win32":
        logging.warning("This script is intended to run on Windows. Backup creation can still work if paths exist.")

    if args.init_config:
        write_default_config(args.config)
        logging.info("Wrote config: %s", args.config)
        return 0

    config = load_config(args.config)

    if args.backup_now:
        create_backup(config)
        return 0

    try:
        watch_for_game_close(config)
    except KeyboardInterrupt:
        logging.info("Stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
