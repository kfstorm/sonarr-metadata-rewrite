"""Metadata format handlers for different media center providers."""

import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from pathlib import Path

from sonarr_metadata_rewrite.models import TmdbIds, TranslatedContent


class MetadataFormat(ABC):
    """Abstract base class for metadata format handlers."""

    @abstractmethod
    def extract_tmdb_ids(self, nfo_path: Path) -> TmdbIds | None:
        """Extract TMDB IDs from .nfo XML file.

        Args:
            nfo_path: Path to .nfo file

        Returns:
            TmdbIds object if found, None otherwise
        """
        pass

    @abstractmethod
    def extract_content(self, nfo_path: Path) -> tuple[str, str]:
        """Extract title and description from .nfo file.

        Args:
            nfo_path: Path to .nfo file

        Returns:
            Tuple of (title, description)
        """
        pass

    @abstractmethod
    def write_translated_metadata(
        self, nfo_path: Path, translation: TranslatedContent
    ) -> None:
        """Write translated metadata to .nfo file.

        Args:
            nfo_path: Path to .nfo file to update
            translation: Translated content

        Raises:
            Exception: If write operation fails
        """
        pass

    @abstractmethod
    def supports_file(self, nfo_path: Path) -> bool:
        """Check if this format handler supports the given file.

        Args:
            nfo_path: Path to .nfo file

        Returns:
            True if this format can handle the file, False otherwise
        """
        pass


class KodiMetadataFormat(MetadataFormat):
    """Metadata format handler for Kodi (XBMC) .nfo files."""

    def extract_tmdb_ids(self, nfo_path: Path) -> TmdbIds | None:
        """Extract TMDB IDs from Kodi .nfo XML file."""
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        # Find TMDB uniqueid
        tmdb_id = None
        uniqueid_elements = root.findall('.//uniqueid[@type="tmdb"]')
        if uniqueid_elements:
            tmdb_id_text = uniqueid_elements[0].text
            if tmdb_id_text and tmdb_id_text.strip():
                tmdb_id = int(tmdb_id_text.strip())

        if tmdb_id is None:
            return None

        # Determine if this is a series or episode file
        if root.tag == "tvshow":
            # Series file
            return TmdbIds(series_id=tmdb_id)
        elif root.tag == "episodedetails":
            # Episode file - extract season and episode numbers
            season_element = root.find("season")
            episode_element = root.find("episode")

            if season_element is not None and episode_element is not None:
                season_text = season_element.text
                episode_text = episode_element.text
                if season_text is not None and episode_text is not None:
                    season = int(season_text.strip())
                    episode = int(episode_text.strip())
                    return TmdbIds(series_id=tmdb_id, season=season, episode=episode)
                else:
                    return None
            else:
                # Missing season/episode information
                return None
        else:
            # Unknown file type
            return None

    def extract_content(self, nfo_path: Path) -> tuple[str, str]:
        """Extract title and description from Kodi .nfo file."""
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        # Extract title
        title = ""
        title_element = root.find("title")
        if title_element is not None and title_element.text:
            title = title_element.text.strip()

        # Extract plot/description
        description = ""
        plot_element = root.find("plot")
        if plot_element is not None and plot_element.text:
            description = plot_element.text.strip()

        return title, description

    def write_translated_metadata(
        self, nfo_path: Path, translation: TranslatedContent
    ) -> None:
        """Write translated metadata to Kodi .nfo file."""
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        # Update title element
        title_element = root.find("title")
        if title_element is not None:
            title_element.text = translation.title

        # Update plot/description element
        plot_element = root.find("plot")
        if plot_element is not None:
            plot_element.text = translation.description

        # Write the updated XML back to file atomically
        # Use a temporary file to ensure atomic writes
        temp_path = nfo_path.with_suffix(".nfo.tmp")
        try:
            # Configure XML formatting
            ET.indent(tree, space="  ", level=0)
            tree.write(temp_path, encoding="utf-8", xml_declaration=True, method="xml")

            # Atomic replacement
            temp_path.replace(nfo_path)

        except Exception:
            # Clean up temporary file if something went wrong
            if temp_path.exists():
                temp_path.unlink()
            raise

    def supports_file(self, nfo_path: Path) -> bool:
        """Check if this file is a Kodi format file."""
        try:
            tree = ET.parse(nfo_path)
            root = tree.getroot()
            return root.tag in ("tvshow", "episodedetails")
        except Exception:
            return False


class EmbyMetadataFormat(MetadataFormat):
    """Metadata format handler for Emby .nfo files.

    Emby uses a similar format to Kodi but with some differences:
    - May use 'overview' instead of 'plot' for descriptions
    - May have different root element names
    - Similar uniqueid structure for TMDB IDs
    """

    def extract_tmdb_ids(self, nfo_path: Path) -> TmdbIds | None:
        """Extract TMDB IDs from Emby .nfo XML file."""
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        # Find TMDB uniqueid (same as Kodi)
        tmdb_id = None
        uniqueid_elements = root.findall('.//uniqueid[@type="tmdb"]')
        if uniqueid_elements:
            tmdb_id_text = uniqueid_elements[0].text
            if tmdb_id_text and tmdb_id_text.strip():
                tmdb_id = int(tmdb_id_text.strip())

        if tmdb_id is None:
            return None

        # Emby uses similar structure to Kodi
        if root.tag in ("tvshow", "series"):
            # Series file
            return TmdbIds(series_id=tmdb_id)
        elif root.tag in ("episodedetails", "episode"):
            # Episode file - extract season and episode numbers
            season_element = root.find("season")
            episode_element = root.find("episode")

            if season_element is not None and episode_element is not None:
                season_text = season_element.text
                episode_text = episode_element.text
                if season_text is not None and episode_text is not None:
                    season = int(season_text.strip())
                    episode = int(episode_text.strip())
                    return TmdbIds(series_id=tmdb_id, season=season, episode=episode)
                else:
                    return None
            else:
                # Missing season/episode information
                return None
        else:
            # Unknown file type
            return None

    def extract_content(self, nfo_path: Path) -> tuple[str, str]:
        """Extract title and description from Emby .nfo file."""
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        # Extract title (same as Kodi)
        title = ""
        title_element = root.find("title")
        if title_element is not None and title_element.text:
            title = title_element.text.strip()

        # Extract description - try both 'overview' and 'plot'
        description = ""
        # Try 'overview' first (Emby preference)
        overview_element = root.find("overview")
        if overview_element is not None and overview_element.text:
            description = overview_element.text.strip()
        else:
            # Fallback to 'plot' (Kodi compatibility)
            plot_element = root.find("plot")
            if plot_element is not None and plot_element.text:
                description = plot_element.text.strip()

        return title, description

    def write_translated_metadata(
        self, nfo_path: Path, translation: TranslatedContent
    ) -> None:
        """Write translated metadata to Emby .nfo file."""
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        # Update title element
        title_element = root.find("title")
        if title_element is not None:
            title_element.text = translation.title

        # Update description - prefer 'overview' but fallback to 'plot'
        overview_element = root.find("overview")
        plot_element = root.find("plot")

        if overview_element is not None:
            overview_element.text = translation.description
        elif plot_element is not None:
            plot_element.text = translation.description

        # Write the updated XML back to file atomically
        temp_path = nfo_path.with_suffix(".nfo.tmp")
        try:
            # Configure XML formatting
            ET.indent(tree, space="  ", level=0)
            tree.write(temp_path, encoding="utf-8", xml_declaration=True, method="xml")

            # Atomic replacement
            temp_path.replace(nfo_path)

        except Exception:
            # Clean up temporary file if something went wrong
            if temp_path.exists():
                temp_path.unlink()
            raise

    def supports_file(self, nfo_path: Path) -> bool:
        """Check if this file is an Emby format file."""
        try:
            tree = ET.parse(nfo_path)
            root = tree.getroot()
            
            # Check for pure Emby tags first
            if root.tag in ("series", "episode"):
                return True
                
            # For Kodi-style tags, check if it has Emby-specific elements
            if root.tag in ("tvshow", "episodedetails"):
                # If it has overview instead of plot, it's likely Emby format
                overview_element = root.find("overview")
                if overview_element is not None:
                    return True
                    
            return False
        except Exception:
            return False


# Registry of available metadata formats
METADATA_FORMATS = {
    "kodi": KodiMetadataFormat,
    "emby": EmbyMetadataFormat,
}


def get_metadata_format(format_name: str) -> MetadataFormat:
    """Get a metadata format instance by name.

    Args:
        format_name: Name of the format ("kodi", "emby", etc.)

    Returns:
        MetadataFormat instance

    Raises:
        ValueError: If format_name is not supported
    """
    if format_name not in METADATA_FORMATS:
        available = ", ".join(METADATA_FORMATS.keys())
        raise ValueError(f"Unsupported format '{format_name}'. Available: {available}")

    return METADATA_FORMATS[format_name]()


def detect_metadata_format(nfo_path: Path) -> MetadataFormat | None:
    """Auto-detect the metadata format of a .nfo file.

    Args:
        nfo_path: Path to .nfo file

    Returns:
        MetadataFormat instance that supports the file, or None if none found
    """
    # Check formats in order of specificity (most specific first)
    format_order = ["emby", "kodi"]
    
    for format_name in format_order:
        if format_name in METADATA_FORMATS:
            format_instance = METADATA_FORMATS[format_name]()
            if format_instance.supports_file(nfo_path):
                return format_instance
    
    return None
