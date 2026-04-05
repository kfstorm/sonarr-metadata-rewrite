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

Legacy format (backward compatibility)
---------------------------------------
Versions prior to multi-root-dir support stored backups relative to the single
configured root directory, e.g. ``<BACKUP_DIR>/Show A/tvshow.nfo`` (with root
``/media/sonarr``).  The functions below accept an optional ``root_dirs``
parameter: when the new-format path is not found in the backup directory, they
fall back to the legacy relative path under each provided root directory.  This
ensures that users who upgrade retain access to their existing backups.

New backups are always written in the new format; the legacy path is only ever
*read*, never written.
"""

import shutil
from pathlib import Path


def _legacy_backup_path(
    file_path: Path, backup_dir: Path, root_dir: Path
) -> Path | None:
    """Return the legacy (root-dir-relative) backup path, or None if not applicable.

    This only checks whether ``file_path`` is under ``root_dir``; it does not
    verify whether the resulting path exists.

    Args:
        file_path: Absolute path to the file
        backup_dir: Backup directory root
        root_dir: Root directory to compute the legacy relative path from

    Returns:
        The legacy backup path, or None if file_path is not under root_dir
    """
    try:
        relative = file_path.relative_to(root_dir)
    except ValueError:
        return None
    return backup_dir / relative


def get_backup_path(
    file_path: Path,
    backup_dir: Path | None,
    root_dirs: list[Path] | None = None,
) -> Path | None:
    """Get backup file path for a given file.

    Checks the new absolute-path format first, then falls back to the legacy
    root-dir-relative format when ``root_dirs`` is supplied.

    Args:
        file_path: Absolute path to the file to get backup path for
        backup_dir: Backup directory root (None to skip)
        root_dirs: Optional list of root directories used as a legacy-format
            fallback for backups created by earlier versions of this tool.

    Returns:
        Path to backup file if backup directory is configured and backup exists,
        None otherwise. For files with different extensions (e.g., images),
        returns any existing backup with the same stem.
    """
    if backup_dir is None:
        return None

    # --- New format: full absolute path under backup_dir ---
    backup_path = backup_dir / file_path.relative_to("/")

    if backup_path.exists():
        return backup_path

    if backup_path.parent.exists():
        stem = backup_path.stem
        for existing_file in backup_path.parent.iterdir():
            if existing_file.is_file() and existing_file.stem == stem:
                return existing_file

    # --- Legacy format fallback (backward compat) ---
    if root_dirs:
        for root_dir in root_dirs:
            legacy = _legacy_backup_path(file_path, backup_dir, root_dir)
            if legacy is None:
                continue
            if legacy.exists():
                return legacy
            if legacy.parent.exists():
                stem = legacy.stem
                for existing_file in legacy.parent.iterdir():
                    if existing_file.is_file() and existing_file.stem == stem:
                        return existing_file

    return None


def create_backup(
    file_path: Path,
    backup_dir: Path | None,
    root_dirs: list[Path] | None = None,
) -> bool:
    """Create backup of a file maintaining its full absolute path structure.

    Checks the new absolute-path format first and the legacy root-dir-relative
    format second before creating a new backup, so that existing backups are
    never overwritten regardless of which format they use.

    Args:
        file_path: Absolute path to file to backup
        backup_dir: Backup directory root (None to skip backup)
        root_dirs: Optional list of root directories used as a legacy-format
            fallback for backups created by earlier versions of this tool.

    Returns:
        True if backup was created or already exists, False if backup disabled
    """
    if backup_dir is None:
        return False

    if not file_path.exists():
        return False

    # --- New format path ---
    backup_path = backup_dir / file_path.relative_to("/")

    if backup_path.exists():
        return True

    if backup_path.parent.exists():
        stem = backup_path.stem
        for existing_file in backup_path.parent.iterdir():
            if existing_file.is_file() and existing_file.stem == stem:
                return True

    # --- Legacy format check (backward compat): don't create a new backup if
    #     an old-format backup already covers this file. ---
    if root_dirs:
        for root_dir in root_dirs:
            legacy = _legacy_backup_path(file_path, backup_dir, root_dir)
            if legacy is None:
                continue
            if legacy.exists():
                return True  # Legacy backup present; preserve it, don't overwrite
            if legacy.parent.exists():
                stem = legacy.stem
                for existing_file in legacy.parent.iterdir():
                    if existing_file.is_file() and existing_file.stem == stem:
                        return True  # Legacy stem-match found

    # --- Create new backup at new-format path ---
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, backup_path)
    return True


def restore_from_backup(
    file_path: Path,
    backup_dir: Path | None,
    root_dirs: list[Path] | None = None,
) -> bool:
    """Restore file from backup, handling stem-matching and extension changes.

    This function handles the case where a backup might have a different extension
    than the current file (e.g., poster.png backup for poster.jpg current).
    It will:
    1. Find the backup using stem-matching (new format first, then legacy)
    2. Delete any files with the same stem but different extensions
    3. Copy the backup to the original location

    Args:
        file_path: Absolute path to file to restore
        backup_dir: Backup directory root (None to skip)
        root_dirs: Optional list of root directories for legacy-format fallback.

    Returns:
        True if file was restored from backup, False otherwise
    """
    # Find backup path (new format first, then legacy)
    backup_path = get_backup_path(file_path, backup_dir, root_dirs)
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
