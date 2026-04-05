"""Utility functions for backup and restore operations.

Provides functions to create backups, retrieve backup paths, and restore files
from backups, with support for stem-matching across different file extensions.

Backup storage structure
------------------------
Each file is stored under the backup directory using its full absolute path
(with the leading ``/`` stripped).  For example, the file
``/media/sonarr/Show A/tvshow.nfo`` is backed up as
``<BACKUP_DIR>/media/sonarr/Show A/tvshow.nfo``.  Using the full absolute path
as the key guarantees that files from different root directories never collide,
even when those directories contain identically-named entries.
"""

import shutil
from pathlib import Path


def get_backup_path(file_path: Path, backup_dir: Path | None) -> Path | None:
    """Get backup file path for a given file.

    Args:
        file_path: Absolute path to the file to get backup path for
        backup_dir: Backup directory root (None to skip)

    Returns:
        Path to backup file if backup directory is configured and backup exists,
        None otherwise. For files with different extensions (e.g., images),
        returns any existing backup with the same stem.
    """
    if backup_dir is None:
        return None

    # Mirror the full absolute path under backup_dir (strip leading /)
    backup_path = backup_dir / file_path.relative_to("/")

    # Check for exact path match first
    if backup_path.exists():
        return backup_path

    # For files that might have different extensions (e.g., images),
    # check if any file with the same stem already exists in backup dir
    if backup_path.parent.exists():
        stem = backup_path.stem
        for existing_file in backup_path.parent.iterdir():
            if existing_file.is_file() and existing_file.stem == stem:
                # Found backup with same filename stem
                return existing_file

    return None


def create_backup(file_path: Path, backup_dir: Path | None) -> bool:
    """Create backup of a file maintaining its full absolute path structure.

    Args:
        file_path: Absolute path to file to backup
        backup_dir: Backup directory root (None to skip backup)

    Returns:
        True if backup was created or already exists, False if backup disabled
    """
    if backup_dir is None:
        return False

    if not file_path.exists():
        return False

    # Mirror the full absolute path under backup_dir (strip leading /)
    backup_path = backup_dir / file_path.relative_to("/")

    # Don't overwrite existing backup with exact same path
    if backup_path.exists():
        return True

    # For files that might have different extensions (e.g., images),
    # check if any file with the same stem already exists in backup dir
    if backup_path.parent.exists():
        stem = backup_path.stem
        for existing_file in backup_path.parent.iterdir():
            if existing_file.is_file() and existing_file.stem == stem:
                # Backup with same filename stem already exists
                return True

    # Ensure backup directory exists
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy file to backup location
    shutil.copy2(file_path, backup_path)
    return True


def restore_from_backup(file_path: Path, backup_dir: Path | None) -> bool:
    """Restore file from backup, handling stem-matching and extension changes.

    This function handles the case where a backup might have a different extension
    than the current file (e.g., poster.png backup for poster.jpg current).
    It will:
    1. Find the backup using stem-matching
    2. Delete any files with the same stem but different extensions
    3. Copy the backup to the original location

    Args:
        file_path: Absolute path to file to restore
        backup_dir: Backup directory root (None to skip)

    Returns:
        True if file was restored from backup, False otherwise
    """
    # Find backup path
    backup_path = get_backup_path(file_path, backup_dir)
    if not backup_path:
        return False

    # Delete files with same stem but different extensions
    # This handles cases like poster.jpg existing when restoring poster.png
    if file_path.parent.exists():
        stem = file_path.stem
        for existing_file in file_path.parent.iterdir():
            if existing_file.is_file() and existing_file.stem == stem:
                existing_file.unlink()

    # Copy backup to original location
    shutil.copy2(backup_path, file_path)
    return True
