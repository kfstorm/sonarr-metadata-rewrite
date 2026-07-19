"""Data models for sonarr-metadata-rewrite."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class TmdbIds:
    """TMDB identifiers extracted from .nfo files."""

    tmdb_id: int
    media_type: Literal["tv", "movie"]
    season: int | None = None
    episode: int | None = None

    def __post_init__(self) -> None:
        """Reject invalid media and episode combinations."""
        if self.media_type == "movie" and (
            self.season is not None or self.episode is not None
        ):
            raise ValueError("Movie TMDB IDs cannot include season or episode")
        if self.episode is not None and self.season is None:
            raise ValueError("TV episode TMDB IDs require a season")

    def __str__(self) -> str:
        """Return TMDB resource path."""
        if self.media_type == "movie":
            return f"movie/{self.tmdb_id}"
        if self.season is not None and self.episode is not None:
            return f"tv/{self.tmdb_id}/season/{self.season}/episode/{self.episode}"
        return f"tv/{self.tmdb_id}"


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
    tagline: TranslatedString = field(
        default_factory=lambda: TranslatedString(content="", language="unknown")
    )


@dataclass
class MetadataInfo:
    """Complete metadata information extracted from NFO file."""

    # IDs
    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None

    # File structure
    file_type: str = "unknown"  # "tvshow", "movie", "episodedetails", or "unknown"
    season: int | None = None
    episode: int | None = None

    # Content
    title: str = ""
    description: str = ""
    tagline: str = ""

    # Raw XML for writing
    xml_tree: ET.ElementTree | None = None
    episode_entries: list[EpisodeMetadataInfo] | None = None


@dataclass
class EpisodeMetadataInfo:
    """Episode metadata extracted from an episode NFO document."""

    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None
    season: int | None = None
    episode: int | None = None
    title: str = ""
    description: str = ""
    tagline: str = ""
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
