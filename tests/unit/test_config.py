"""Unit tests for configuration module."""

import os
from pathlib import Path
from unittest.mock import patch

from sonarr_metadata_rewrite.config import Settings, get_settings


def test_settings_with_required_fields(test_data_dir: Path) -> None:
    """Test Settings with required fields."""
    settings = Settings(
        tmdb_api_key="test_api_key_1234567890abcdef",
        rewrite_root_dir=test_data_dir,
    )
    assert settings.tmdb_api_key == "test_api_key_1234567890abcdef"
    assert settings.rewrite_root_dir == test_data_dir
    assert settings.preferred_languages == ["zh-CN"]  # default
    assert settings.periodic_scan_interval_seconds == 3600  # default


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
        "PREFERRED_LANGUAGES": '["en", "fr"]',
    }
    with patch.dict(os.environ, env_vars):
        settings = get_settings()
        assert settings.tmdb_api_key == "env_test_key"
        assert settings.rewrite_root_dir == test_data_dir


def test_settings_backup_disabled(test_data_dir: Path) -> None:
    """Test Settings with backup disabled."""
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=test_data_dir,
        original_files_backup_dir=None,
    )
    assert settings.original_files_backup_dir is None
