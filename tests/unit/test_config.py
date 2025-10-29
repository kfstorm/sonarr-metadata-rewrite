"""Unit tests for configuration module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from sonarr_metadata_rewrite.config import Settings, get_settings


def test_settings_with_required_fields(test_data_dir: Path) -> None:
    """Test Settings with required fields."""
    settings = Settings(
        tmdb_api_key="test_api_key_1234567890abcdef",
        rewrite_root_dir=test_data_dir,
        preferred_languages=["zh-CN"],
    )
    assert settings.tmdb_api_key == "test_api_key_1234567890abcdef"
    assert settings.rewrite_root_dir == test_data_dir
    assert settings.preferred_languages == ["zh-CN"]
    assert settings.periodic_scan_interval_seconds == 86400  # default
    assert settings.service_mode == "rewrite"  # default


def test_settings_with_all_fields(test_data_dir: Path) -> None:
    """Test Settings with all fields specified."""
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=test_data_dir,
        preferred_languages=["ja-JP", "ko-KR"],
        periodic_scan_interval_seconds=1800,
        cache_duration_hours=168,
        cache_dir=test_data_dir / "custom_cache",
        original_files_backup_dir=test_data_dir / "custom_backups",
    )
    assert settings.preferred_languages == ["ja-JP", "ko-KR"]
    assert settings.periodic_scan_interval_seconds == 1800
    assert settings.cache_duration_hours == 168
    assert settings.cache_dir == test_data_dir / "custom_cache"
    assert settings.original_files_backup_dir == test_data_dir / "custom_backups"


def test_get_settings_from_env(test_data_dir: Path) -> None:
    """Test get_settings from environment variables."""
    env_vars = {
        "TMDB_API_KEY": "env_test_key",
        "REWRITE_ROOT_DIR": str(test_data_dir),
        "PREFERRED_LANGUAGES": "en,fr",
    }
    with patch.dict(os.environ, env_vars):
        settings = get_settings()
        assert settings.tmdb_api_key == "env_test_key"
        assert settings.rewrite_root_dir == test_data_dir
        assert settings.preferred_languages == ["en", "fr"]


def test_settings_backup_disabled(test_data_dir: Path) -> None:
    """Test Settings with backup disabled."""
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=test_data_dir,
        preferred_languages=["zh-CN"],
        original_files_backup_dir=None,
    )
    assert settings.original_files_backup_dir is None


def test_preferred_languages_comma_separated(tmp_path: Path) -> None:
    """Test preferred_languages parsing from comma-separated string via environment."""
    env_vars = {
        "TMDB_API_KEY": "test_key",
        "REWRITE_ROOT_DIR": str(tmp_path),
        "PREFERRED_LANGUAGES": "zh-CN, ja-JP , ko-KR",
    }
    with patch.dict(os.environ, env_vars):
        settings = get_settings()
        assert settings.preferred_languages == ["zh-CN", "ja-JP", "ko-KR"]


def test_preferred_languages_single_language(tmp_path: Path) -> None:
    """Test preferred_languages with single language via environment."""
    env_vars = {
        "TMDB_API_KEY": "test_key",
        "REWRITE_ROOT_DIR": str(tmp_path),
        "PREFERRED_LANGUAGES": "fr",
    }
    with patch.dict(os.environ, env_vars):
        settings = get_settings()
        assert settings.preferred_languages == ["fr"]


def test_preferred_languages_empty_string_fails(tmp_path: Path) -> None:
    """Test preferred_languages with empty string via env fails validation."""
    env_vars = {
        "TMDB_API_KEY": "test_key",
        "REWRITE_ROOT_DIR": str(tmp_path),
        "PREFERRED_LANGUAGES": "",
    }
    with patch.dict(os.environ, env_vars):
        with pytest.raises(ValueError):
            get_settings()


def test_preferred_languages_required_field(tmp_path: Path) -> None:
    """Test preferred_languages is required in environment."""
    env_vars = {
        "TMDB_API_KEY": "test_key",
        "REWRITE_ROOT_DIR": str(tmp_path),
        # No PREFERRED_LANGUAGES
    }
    with patch.dict(os.environ, env_vars):
        with pytest.raises(ValueError):
            get_settings()


def test_service_mode_default(test_data_dir: Path) -> None:
    """Test service_mode defaults to 'rewrite'."""
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=test_data_dir,
        preferred_languages=["zh-CN"],
    )
    assert settings.service_mode == "rewrite"


def test_service_mode_rewrite(test_data_dir: Path) -> None:
    """Test service_mode can be set to 'rewrite'."""
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=test_data_dir,
        preferred_languages=["zh-CN"],
        service_mode="rewrite",
    )
    assert settings.service_mode == "rewrite"


def test_service_mode_rollback(test_data_dir: Path) -> None:
    """Test service_mode can be set to 'rollback'."""
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=test_data_dir,
        preferred_languages=["zh-CN"],
        service_mode="rollback",
    )
    assert settings.service_mode == "rollback"


def test_service_mode_invalid_value_fails() -> None:
    """Test service_mode with invalid value fails validation."""

    with pytest.raises(ValidationError):
        Settings(
            tmdb_api_key="test_key",
            rewrite_root_dir=Path("/tmp"),
            preferred_languages=["zh-CN"],
            service_mode="invalid",
        )


def test_enable_image_rewrite_defaults_true(test_data_dir: Path) -> None:
    """Image rewrite should be enabled by default."""
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=test_data_dir,
        preferred_languages=["zh-CN"],
    )
    assert settings.enable_image_rewrite is True


def test_enable_image_rewrite_can_be_disabled_via_env(tmp_path: Path) -> None:
    """Image rewrite can be disabled via environment variable."""
    env_vars = {
        "TMDB_API_KEY": "test_key",
        "REWRITE_ROOT_DIR": str(tmp_path),
        "PREFERRED_LANGUAGES": "zh-CN",
        "ENABLE_IMAGE_REWRITE": "false",
    }
    with patch.dict(os.environ, env_vars):
        settings = get_settings()
        assert settings.enable_image_rewrite is False
