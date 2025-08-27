"""Configuration management using Pydantic Settings."""

from pathlib import Path

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # TMDB API
    tmdb_api_key: str = Field(description="TMDB API key for translation requests")

    # Directory monitoring
    rewrite_root_dir: Path = Field(
        description="Root directory to monitor and rewrite .nfo files"
    )
    periodic_scan_interval_seconds: int = Field(
        default=86400, description="How often to scan the directory (seconds)"
    )

    # Translation preferences
    preferred_languages: str = Field(
        description="Preferred languages in priority order (comma-separated)"
    )

    # Universal caching configuration
    cache_duration_hours: int = Field(
        default=720, description="How long to cache API responses (hours)"
    )
    cache_dir: Path = Field(
        default=Path("./cache"),
        description="Universal cache directory for all cached data",
    )

    # Original file backup
    original_files_backup_dir: Path | None = Field(
        default=Path("./backups"),
        description="Directory to backup original files (None disables backup)",
    )

    # Component control
    enable_file_monitor: bool = Field(
        default=True, description="Enable real-time file monitoring"
    )
    enable_file_scanner: bool = Field(
        default=True, description="Enable periodic directory scanning"
    )

    @field_validator("preferred_languages")
    @classmethod
    def parse_preferred_languages(cls, v: str) -> list[str]:
        """Parse preferred languages from comma-separated string."""
        if isinstance(v, str):
            languages = [lang.strip() for lang in v.split(",") if lang.strip()]
            if not languages:
                raise ValueError("preferred_languages cannot be empty")
            return languages
        raise ValueError("preferred_languages must be a comma-separated string")


def get_settings() -> Settings:
    """Get application settings."""
    try:
        # Pydantic BaseSettings automatically loads from environment variables
        return Settings()
    except ValidationError as e:
        raise ValueError(f"Configuration error: {e}") from e
