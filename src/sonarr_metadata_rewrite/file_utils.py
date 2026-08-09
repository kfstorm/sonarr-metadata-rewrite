"""Utility functions for handling .nfo/.NFO files and image filenames.

Centralizes image filename rules (poster/clearlogo/season posters) and supported
extensions so other modules can reuse the same logic consistently.
"""

import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import cast

from sonarr_metadata_rewrite.models import EpisodeMetadataInfo, MetadataInfo
from sonarr_metadata_rewrite.retry_utils import retry

# Supported image extensions (lowercase with leading dot)
IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png"}
TRAILING_SCRAPER_URLS_RE = re.compile(
    r"(?P<suffix>(?:[ \t]*\r?\n)+[ \t]*https?://[^\s<>]+"
    r"(?:[ \t]*\r?\n[ \t]*https?://[^\s<>]+)*(?:[ \t]*\r?\n)*)\Z"
)


class UnsupportedNfoRootError(ValueError):
    """Raised when a valid NFO has a root tag the service does not translate."""

    def __init__(self, root_tag: str) -> None:
        """Initialize the error for the unsupported root tag."""
        super().__init__(f"Unsupported NFO root tag: {root_tag}")


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


def find_root_dir_for_file(file_path: Path, root_dirs: list[Path]) -> Path | None:
    """Find which root directory a file belongs to.

    Args:
        file_path: Path to the file
        root_dirs: List of candidate root directories

    Returns:
        The first root directory that contains the file, or None if none match
    """
    for root_dir in root_dirs:
        if file_path == root_dir or root_dir in file_path.parents:
            return root_dir
    return None


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


def parse_nfo_with_retry(nfo_path: Path) -> MetadataInfo:
    """Parse NFO file with retry logic for incomplete/corrupt files.

    Args:
        nfo_path: Path to .nfo file to parse

    Returns:
        Parsed metadata information

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
    def parse_file() -> MetadataInfo:
        return _parse_nfo_documents(nfo_path)

    return cast(MetadataInfo, parse_file())


def extract_metadata_info(nfo_path: Path) -> MetadataInfo:
    """Extract all metadata information from NFO file in single parse.

    Args:
        nfo_path: Path to .nfo file

    Returns:
        MetadataInfo object with all extracted data
    """
    return parse_nfo_with_retry(nfo_path)


def _parse_nfo_documents(nfo_path: Path) -> MetadataInfo:
    """Parse one or more adjacent XML documents from an NFO file."""
    raw_content = nfo_path.read_bytes().decode("utf-8").replace("\ufeff", "")
    xml_content, scraper_urls = _split_trailing_scraper_urls(raw_content)
    normalized_content = xml_content.strip()
    normalized_content = re.sub(r"<\?xml[^>]*\?>", "", normalized_content).strip()
    wrapped_content = f"<nfo-root>{normalized_content}</nfo-root>"
    wrapped_root = ET.fromstring(wrapped_content)

    if not list(wrapped_root):
        raise ET.ParseError("No XML document found")
    if wrapped_root.text and not wrapped_root.text.isspace():
        raise ET.ParseError("Invalid text outside NFO XML document")
    if any(child.tail and not child.tail.isspace() for child in wrapped_root):
        raise ET.ParseError("Invalid text outside NFO XML document")

    if len(wrapped_root) == 1:
        root = wrapped_root[0]
        if root.tag == "tvshow":
            metadata = _extract_tvshow_metadata(root)
            metadata.trailing_scraper_urls = scraper_urls
            return metadata
        if root.tag == "movie":
            metadata = _extract_movie_metadata(root)
            metadata.trailing_scraper_urls = scraper_urls
            return metadata

    if all(child.tag == "episodedetails" for child in wrapped_root):
        metadata = _extract_episode_metadata(wrapped_root)
        metadata.trailing_scraper_urls = scraper_urls
        return metadata

    if len(wrapped_root) == 1:
        raise UnsupportedNfoRootError(wrapped_root[0].tag)

    raise ET.ParseError("Unsupported NFO root structure")


def _split_trailing_scraper_urls(content: str) -> tuple[str, str]:
    """Separate Kodi combination-NFO scraper URLs from XML content."""
    match = TRAILING_SCRAPER_URLS_RE.search(content)
    if match is None:
        return content, ""
    return content[: match.start()], match.group("suffix")


def _extract_tvshow_metadata(root: ET.Element) -> MetadataInfo:
    """Extract metadata from a single tvshow document."""
    info = MetadataInfo(
        file_type="tvshow",
        xml_tree=ET.ElementTree(ET.fromstring(ET.tostring(root, encoding="unicode"))),
    )
    _populate_common_metadata(info, root)
    return info


def _extract_movie_metadata(root: ET.Element) -> MetadataInfo:
    """Extract metadata from a single movie document."""
    info = MetadataInfo(
        file_type="movie",
        xml_tree=ET.ElementTree(ET.fromstring(ET.tostring(root, encoding="unicode"))),
    )
    _populate_common_metadata(info, root)
    return info


def _extract_episode_metadata(root: ET.Element) -> MetadataInfo:
    """Extract metadata from one or more episode documents."""
    episode_entries = [_build_episode_entry(child) for child in root]
    first_entry = episode_entries[0]
    info = MetadataInfo(
        tmdb_id=first_entry.tmdb_id,
        tvdb_id=first_entry.tvdb_id,
        imdb_id=first_entry.imdb_id,
        file_type="episodedetails",
        season=first_entry.season,
        episode=first_entry.episode,
        release_date=first_entry.release_date,
        title=first_entry.title,
        description=first_entry.description,
        tagline=first_entry.tagline,
        xml_tree=first_entry.xml_tree,
        episode_entries=episode_entries,
    )

    for entry in episode_entries[1:]:
        if info.tmdb_id is None:
            info.tmdb_id = entry.tmdb_id
        if info.tvdb_id is None:
            info.tvdb_id = entry.tvdb_id
        if info.imdb_id is None:
            info.imdb_id = entry.imdb_id

    return info


def _build_episode_entry(root: ET.Element) -> EpisodeMetadataInfo:
    """Build a single episode metadata entry from an XML root."""
    tree = ET.ElementTree(ET.fromstring(ET.tostring(root, encoding="unicode")))
    entry = EpisodeMetadataInfo(xml_tree=tree)
    _populate_common_metadata(entry, root)

    # For episode files, extract season/episode numbers
    season_element = root.find("season")
    episode_element = root.find("episode")
    if season_element is not None and season_element.text:
        entry.season = int(season_element.text.strip())
    if episode_element is not None and episode_element.text:
        entry.episode = int(episode_element.text.strip())

    return entry


def _populate_common_metadata(
    info: MetadataInfo | EpisodeMetadataInfo, root: ET.Element
) -> None:
    """Populate shared metadata fields from a root element."""
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

    tagline_element = root.find("tagline")
    if tagline_element is not None and tagline_element.text:
        info.tagline = tagline_element.text.strip()

    release_dates = [
        parsed_date
        for tag in ("premiered", "aired")
        for element in root.findall(tag)
        if (parsed_date := _parse_nfo_date(element.text)) is not None
    ]
    info.release_date = max(release_dates, default=None)


def _parse_nfo_date(value: str | None) -> date | None:
    """Parse an optional NFO date without rejecting the whole document."""
    if not value or not value.strip():
        return None

    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None
