"""Data models for sonarr-metadata-rewrite."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TmdbIds:
    """TMDB identifiers extracted from .nfo files."""

    series_id: int
    season: int | None = None  # None for tvshow.nfo
    episode: int | None = None  # None for tvshow.nfo

    def __str__(self) -> str:
        """Return TMDB resource path."""
        if self.season is not None and self.episode is not None:
            return f"tv/{self.series_id}/season/{self.season}/episode/{self.episode}"
        else:
            return f"tv/{self.series_id}"


@dataclass
class TranslatedString:
    """A translated string with its source language."""

    content: str
    language: str


@dataclass
class TranslatedContent:
    """Translated content for TV series or episodes."""

    title: TranslatedString
    description: TranslatedString


@dataclass
class MetadataInfo:
    """Complete metadata information extracted from NFO file."""

    # IDs
    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None

    # File structure
    file_type: str = "unknown"  # "tvshow" or "episodedetails" or "unknown"
    season: int | None = None
    episode: int | None = None

    # Content
    title: str = ""
    description: str = ""

    # Raw XML for writing
    xml_tree: ET.ElementTree | None = None


@dataclass
class ProcessResult:
    """Base result of processing a file."""

    success: bool
    file_path: Path
    message: str
    exception: Exception | None = None
    backup_created: bool = False
    file_modified: bool = False


@dataclass
class MetadataProcessResult(ProcessResult):
    """Result of processing a metadata file."""

    tmdb_ids: TmdbIds | None = None
    translated_content: TranslatedContent | None = None


@dataclass
class ImageCandidate:
    """TMDB image candidate information."""

    file_path: str
    iso_639_1: str | None
    iso_3166_1: str | None


@dataclass
class ImageProcessResult(ProcessResult):
    """Result of processing an image file."""

    kind: str = ""  # "poster" or "clearlogo"
    selected_language: str = ""
    selected_file_path: str = ""
