"""Configuration management using Pydantic Settings."""

import os
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class CustomEnvSettings(PydanticBaseSettingsSource):
    """Custom environment settings source that handles comma-separated lists."""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        """Get field value from environment, handling preferred_languages specially."""
        env_name = field_name.upper()
        env_val = os.getenv(env_name)

        if env_val is None:
            return None, env_name, False

        # Handle preferred_languages as comma-separated string (not JSON)
        if field_name == "preferred_languages":
            return env_val, env_name, False

        # For other fields, use default behavior
        return env_val, env_name, False

    def prepare_field_value(
        self, field_name: str, field: Any, value: Any, value_is_complex: bool
    ) -> Any:
        """Prepare field value, skipping JSON parsing for preferred_languages."""
        if field_name == "preferred_languages":
            return value
        return super().prepare_field_value(field_name, field, value, value_is_complex)

    def __call__(self) -> dict[str, Any]:
        """Load settings from environment variables."""
        d: dict[str, Any] = {}

        for field_name, field_info in self.settings_cls.model_fields.items():
            field_value, _, value_is_complex = self.get_field_value(
                field_info, field_name
            )
            if field_value is not None:
                prepared_value = self.prepare_field_value(
                    field_name,
                    field_info,
                    field_value,
                    value_is_complex,
                )
                d[field_name] = prepared_value

        return d


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize settings sources to use custom environment handler."""
        return (
            init_settings,
            CustomEnvSettings(settings_cls),
            dotenv_settings,
            file_secret_settings,
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
    preferred_languages: list[str] = Field(
        description="Preferred languages in priority order (comma-separated)"
    )

    @field_validator("preferred_languages", mode="before")
    @classmethod
    def parse_preferred_languages(cls, v: str | list[str]) -> list[str]:
        """Parse preferred languages from comma-separated string or list."""
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            languages = [lang.strip() for lang in v.split(",") if lang.strip()]
            if not languages:
                raise ValueError("preferred_languages cannot be empty")
            return languages
        raise ValueError("preferred_languages must be a comma-separated string or list")

    # Universal caching configuration
    cache_duration_hours: int = Field(
        default=720, description="How long to cache API responses (hours)"
    )
    cache_dir: Path = Field(
        default=Path("./cache"),
        description="Universal cache directory for all cached data",
    )

    # TMDB API rate limiting
    tmdb_max_retries: int = Field(
        default=3, description="Maximum retry attempts for rate-limited requests"
    )
    tmdb_initial_retry_delay: float = Field(
        default=1.0, description="Initial delay for rate limit retries (seconds)"
    )
    tmdb_max_retry_delay: float = Field(
        default=60.0, description="Maximum delay for rate limit retries (seconds)"
    )

    # Original file backup
    original_files_backup_dir: Path | None = Field(
        default=Path("./backups"),
        description="Directory to backup original files (None disables backup)",
    )

    # Service mode
    service_mode: str = Field(
        default="rewrite", description="Service mode: 'rewrite' or 'rollback'"
    )

    # Component control
    enable_file_monitor: bool = Field(
        default=True, description="Enable real-time file monitoring"
    )
    enable_file_scanner: bool = Field(
        default=True, description="Enable periodic directory scanning"
    )
    enable_image_rewrite: bool = Field(
        default=True, description="Enable image rewriting (posters and clearlogos)"
    )

    @field_validator("service_mode")
    @classmethod
    def validate_service_mode(cls, v: str) -> str:
        """Validate service mode value."""
        if v not in ["rewrite", "rollback"]:
            raise ValueError("service_mode must be either 'rewrite' or 'rollback'")
        return v


def get_settings() -> Settings:
    """Get application settings."""
    try:
        # Pydantic BaseSettings automatically loads from environment variables
        return Settings()
    except ValidationError as e:
        raise ValueError(f"Configuration error: {e}") from e
