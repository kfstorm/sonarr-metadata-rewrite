"""Utility functions for handling .nfo/.NFO files and image filenames.

Centralizes image filename rules (poster/clearlogo/season posters) and supported
extensions so other modules can reuse the same logic consistently.
"""

import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

# Supported image extensions (lowercase with leading dot)
IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png"}


def parse_image_info(basename: str) -> tuple[str, int | None]:
    """Parse image basename to determine kind and season number.

    Args:
        basename: Image file basename (e.g., "poster.jpg")

    Returns:
        Tuple of (kind, season_number) where kind is "poster" or "clearlogo",
        season_number is an integer season (0 for specials) or None for
        series-level. Returns ("", None) if not recognized or extension
        unsupported.
    """
    suffix = Path(basename).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        return ("", None)

    name = Path(basename).stem.lower()

    # Series-level poster/clearlogo
    if name == "poster":
        return ("poster", None)
    if name == "clearlogo":
        return ("clearlogo", None)

    # Specials poster
    if name == "season-specials-poster":
        return ("poster", 0)

    # Season poster like season01-poster
    m = re.match(r"^season(\d+)-poster$", name)
    if m:
        return ("poster", int(m.group(1)))

    return ("", None)


def is_nfo_file(file_path: Path) -> bool:
    """Check if a file is an NFO file (case-insensitive).

    Args:
        file_path: Path to the file to check

    Returns:
        True if the file has .nfo or .NFO extension, False otherwise
    """
    return file_path.suffix.lower() == ".nfo"


def is_rewritable_image(file_path: Path) -> bool:
    """Check if an image file matches patterns for poster or clearlogo.

    Args:
        file_path: Path to the image file to check

    Returns:
        True if filename matches poster.* or seasonNN-poster.*
        or clearlogo.*, False otherwise
    """
    kind, _ = parse_image_info(file_path.name)
    return bool(kind)


def find_target_files(directory: Path, recursive: bool = True) -> list[Path]:
    """Find all target files (.nfo and rewritable images) in one pass.

    This consolidates file system traversal to avoid duplicated logic.

    Args:
        directory: Directory to search in
        recursive: Whether to search recursively in subdirectories

    Returns:
        List of paths to all NFO files and rewritable image files found
    """
    if not directory.exists():
        return []

    all_entries = directory.rglob("*") if recursive else directory.glob("*")

    results: list[Path] = []
    for file_path in all_entries:
        if not file_path.is_file():
            continue

        if is_target_file(file_path):
            results.append(file_path)

    return results


def is_target_file(file_path: Path) -> bool:
    """Return True if path is a target file (.nfo or rewritable image)."""
    return is_nfo_file(file_path) or is_rewritable_image(file_path)


def extract_tmdb_id(nfo_path: Path) -> int | None:
    """Extract TMDB ID from an NFO file.

    Args:
        nfo_path: Path to NFO file

    Returns:
        TMDB series ID if found, None otherwise
    """
    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        # Look for uniqueid with type="tmdb"
        for uniqueid in root.findall(".//uniqueid"):
            if uniqueid.get("type", "").lower() == "tmdb":
                id_value = uniqueid.text
                if id_value and id_value.strip():
                    return int(id_value.strip())
    except Exception:
        pass

    return None


def create_backup(file_path: Path, backup_dir: Path | None, root_dir: Path) -> bool:
    """Create backup of a file maintaining directory structure.

    Args:
        file_path: Path to file to backup
        backup_dir: Backup directory root (None to skip backup)
        root_dir: Root directory for calculating relative path

    Returns:
        True if backup was created or already exists, False if backup disabled
    """
    if backup_dir is None:
        return False

    if not file_path.exists():
        return False

    # Calculate backup path maintaining directory structure
    relative_path = file_path.relative_to(root_dir)
    backup_path = backup_dir / relative_path

    # Don't overwrite existing backup
    if backup_path.exists():
        return True

    # Ensure backup directory exists
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy file to backup location
    shutil.copy2(file_path, backup_path)
    return True
