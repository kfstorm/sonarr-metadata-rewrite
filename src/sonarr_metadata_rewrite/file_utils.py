"""Utility functions for handling .nfo/.NFO files and image filenames.

Centralizes image filename rules (poster/clearlogo/season posters) and supported
extensions so other modules can reuse the same logic consistently.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.etree.ElementTree import ElementTree  # noqa: F401

from sonarr_metadata_rewrite.models import MetadataInfo
from sonarr_metadata_rewrite.retry_utils import retry

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


def parse_nfo_with_retry(nfo_path: Path) -> "ElementTree[ET.Element]":
    """Parse NFO file with retry logic for incomplete/corrupt files.

    Args:
        nfo_path: Path to .nfo file to parse

    Returns:
        Parsed XML tree

    Raises:
        ET.ParseError: If file remains corrupt after retries
        OSError: If file cannot be accessed after retries
    """

    @retry(
        timeout=3.0,
        interval=0.5,
        log_interval=3.0,
        exceptions=(ET.ParseError, OSError),
    )
    def parse_file() -> "ElementTree[ET.Element]":
        return ET.parse(nfo_path)

    return parse_file()


def extract_metadata_info(nfo_path: Path) -> MetadataInfo:
    """Extract all metadata information from NFO file in single parse.

    Args:
        nfo_path: Path to .nfo file

    Returns:
        MetadataInfo object with all extracted data
    """
    tree = parse_nfo_with_retry(nfo_path)
    root = tree.getroot()

    # Determine file type from root tag
    file_type = root.tag if root.tag in ("tvshow", "episodedetails") else "unknown"

    info = MetadataInfo(file_type=file_type, xml_tree=tree)  # type: ignore[arg-type]

    # Extract all uniqueid elements
    for uniqueid in root.findall(".//uniqueid"):
        id_type = uniqueid.get("type", "").lower()
        id_value = uniqueid.text

        if not id_value or not id_value.strip():
            continue

        if id_type == "tmdb":
            info.tmdb_id = int(id_value.strip())
        elif id_type == "tvdb":
            info.tvdb_id = int(id_value.strip())
        elif id_type == "imdb":
            info.imdb_id = id_value.strip()

    # Extract title
    title_element = root.find("title")
    if title_element is not None and title_element.text:
        info.title = title_element.text.strip()

    # Extract plot/description
    plot_element = root.find("plot")
    if plot_element is not None and plot_element.text:
        info.description = plot_element.text.strip()

    # For episode files, extract season/episode numbers
    if file_type == "episodedetails":
        season_element = root.find("season")
        episode_element = root.find("episode")

        if season_element is not None and season_element.text:
            info.season = int(season_element.text.strip())
        if episode_element is not None and episode_element.text:
            info.episode = int(episode_element.text.strip())

    return info
