"""Data models for sonarr-metadata-rewrite."""

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
class TranslatedContent:
    """Translated content for TV series or episodes."""

    title: str
    description: str
    language: str


@dataclass
class ProcessResult:
    """Result of processing a metadata file."""

    success: bool
    file_path: Path
    message: str
    tmdb_ids: TmdbIds | None = None
    translations_found: bool = False
    backup_created: bool = False
    file_modified: bool = False
    selected_language: str | None = None
