"""Utility functions for handling .nfo/.NFO files with case sensitivity."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path


def is_nfo_file(file_path: Path) -> bool:
    """Check if a file is an NFO file (case-insensitive).

    Args:
        file_path: Path to the file to check

    Returns:
        True if the file has .nfo or .NFO extension, False otherwise
    """
    return file_path.suffix.lower() == ".nfo"


def is_image_file(file_path: Path) -> bool:
    """Check if a file is an image file (jpg/jpeg/png, case-insensitive).

    Args:
        file_path: Path to the file to check

    Returns:
        True if the file has .jpg/.jpeg/.png extension, False otherwise
    """
    suffix = file_path.suffix.lower()
    return suffix in {".jpg", ".jpeg", ".png"}


def is_rewritable_image(file_path: Path) -> bool:
    """Check if an image file matches patterns for poster or logo.

    Args:
        file_path: Path to the image file to check

    Returns:
        True if filename matches poster.* or seasonNN-poster.*
        or logo.*, False otherwise
    """
    if not is_image_file(file_path):
        return False

    name = file_path.stem.lower()
    # Match: poster, seasonNN-poster (e.g., season01-poster), logo
    return bool(
        re.match(r"^poster$", name)
        or re.match(r"^season\d+-poster$", name)
        or re.match(r"^logo$", name)
    )


def find_nfo_files(directory: Path, recursive: bool = True) -> list[Path]:
    """Find all .nfo and .NFO files in a directory (case-insensitive).

    Args:
        directory: Directory to search in
        recursive: Whether to search recursively in subdirectories

    Returns:
        List of paths to all NFO files found
    """
    if not directory.exists():
        return []

    if recursive:
        # Use rglob to find all files, then filter by case-insensitive extension
        all_files = directory.rglob("*")
    else:
        # Use glob for non-recursive search
        all_files = directory.glob("*")

    # Filter files that have .nfo extension (case-insensitive)
    nfo_files = []
    for file_path in all_files:
        if file_path.is_file() and is_nfo_file(file_path):
            nfo_files.append(file_path)

    return nfo_files


def find_rewritable_images(directory: Path, recursive: bool = True) -> list[Path]:
    """Find all rewritable image files in a directory.

    Args:
        directory: Directory to search in
        recursive: Whether to search recursively in subdirectories

    Returns:
        List of paths to all rewritable image files found
    """
    if not directory.exists():
        return []

    if recursive:
        all_files = directory.rglob("*")
    else:
        all_files = directory.glob("*")

    # Filter for rewritable images (poster/logo patterns)
    images = []
    for file_path in all_files:
        if file_path.is_file() and is_rewritable_image(file_path):
            images.append(file_path)

    return images


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
