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

import os
import shutil
import tempfile
from pathlib import Path

from sonarr_metadata_rewrite.file_utils import (
    IMAGE_EXTENSIONS,
    atomic_write_bytes,
    check_file_unchanged,
    is_rewritable_image,
    stat_regular_file,
)


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

    if stat_regular_file(backup_path) is not None:
        return backup_path

    if backup_path.parent.exists():
        stem = backup_path.stem
        for existing_file in backup_path.parent.iterdir():
            if existing_file.stem == stem and stat_regular_file(existing_file):
                return existing_file

    # --- Legacy format fallback (backward compat) ---
    if root_dirs:
        for root_dir in root_dirs:
            legacy = _legacy_backup_path(file_path, backup_dir, root_dir)
            if legacy is None:
                continue
            if stat_regular_file(legacy) is not None:
                return legacy
            if legacy.parent.exists():
                stem = legacy.stem
                for existing_file in legacy.parent.iterdir():
                    if existing_file.stem == stem and stat_regular_file(existing_file):
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
        True if backup was created or already exists, False if backup disabled.
        Enabled backup failures raise and must stop the rewrite.
    """
    if backup_dir is None:
        return False

    source_state = stat_regular_file(file_path)
    if source_state is None:
        raise FileNotFoundError(file_path)

    if get_backup_path(file_path, backup_dir, root_dirs) is not None:
        return True

    # --- Create new backup at new-format path ---
    backup_path = backup_dir / file_path.relative_to("/")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        dir=backup_path.parent, prefix=".backup_", suffix=".tmp"
    )
    os.close(fd)
    temporary = Path(name)
    try:
        # copyfile deliberately avoids copystat/listxattr, including on FUSE mounts.
        shutil.copyfile(file_path, temporary)
        check_file_unchanged(file_path, source_state)
        try:
            # A hard link publishes complete bytes without replacing a racing backup.
            os.link(temporary, backup_path)
        except FileExistsError:
            if stat_regular_file(backup_path) is None:
                raise
    finally:
        temporary.unlink()
    return True


def restore_from_backup(
    file_path: Path,
    backup_dir: Path | None,
    root_dirs: list[Path] | None = None,
) -> bool:
    """Restore file from backup, handling stem-matching and extension changes.

    Image contents are published under the backup's extension. Access attributes
    come from the requested current file, the final target, or the first sorted
    supported image variant, in that order. Without a current file, normal
    creation permissions apply. Only after publication are obsolete supported
    image variants removed; cleanup failures raise and leave restored bytes intact.

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

    target = file_path
    variants: dict[Path, os.stat_result] = {}
    if is_rewritable_image(file_path):
        if backup_path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported backup image extension: {backup_path}")
        target = file_path.with_suffix(backup_path.suffix)
        if file_path.parent.exists():
            for path in sorted(file_path.parent.iterdir()):
                if (
                    path.stem == file_path.stem
                    and path.suffix.lower() in IMAGE_EXTENSIONS
                ):
                    state = stat_regular_file(path)
                    if state is not None:
                        variants[path] = state

    current = None
    for candidate in (file_path, target, *variants):
        if stat_regular_file(candidate) is not None:
            current = candidate
            break

    backup_state = stat_regular_file(backup_path)
    content = backup_path.read_bytes()
    check_file_unchanged(backup_path, backup_state)
    atomic_write_bytes(target, content, mode_from=current)
    for path, state in variants.items():
        if path != target:
            try:
                check_file_unchanged(path, state)
                path.unlink()
            except OSError as error:
                raise OSError(
                    f"Restored {target}, but could not remove obsolete variant {path}"
                ) from error
    return True
