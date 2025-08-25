"""Shared test configuration and fixtures."""

import shutil
from collections.abc import Callable, Generator
from pathlib import Path
from unittest.mock import Mock

import pytest

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.models import ProcessResult


@pytest.fixture
def test_data_dir() -> Path:
    """Shared test data directory for all tests."""
    return Path(__file__).parent / "data"


@pytest.fixture
def test_settings(test_data_dir: Path) -> Settings:
    """Standard test settings using shared test data directory."""
    return Settings(
        tmdb_api_key="test_key_12345",
        rewrite_root_dir=test_data_dir,
        preferred_languages=["zh-CN"],
        periodic_scan_interval_seconds=1,  # Fast interval for testing
        original_files_backup_dir=test_data_dir / "backups",
        cache_dir=test_data_dir / "cache",
    )


@pytest.fixture
def temp_nfo_file(test_data_dir: Path) -> Generator[Path, None, None]:
    """Create a temporary .nfo file within test_data_dir for testing with cleanup."""
    import uuid

    temp_file = test_data_dir / f"temp_{uuid.uuid4().hex[:8]}.nfo"
    try:
        yield temp_file
    finally:
        if temp_file.exists():
            temp_file.unlink()


@pytest.fixture
def create_test_files() -> Generator[Callable[[Path, Path], Path], None, None]:
    """Factory fixture to create test files from samples with cleanup."""
    created_files = []

    def _create_file(source_path: Path, dest_path: Path) -> Path:
        """Copy a sample file to destination for testing."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest_path)
        created_files.append(dest_path)
        return dest_path

    yield _create_file

    # Cleanup
    for file_path in created_files:
        if file_path.exists():
            file_path.unlink()


@pytest.fixture
def callback_tracker() -> Mock:
    """Mock callback that tracks invocations for file scanning tests."""
    return Mock()


def assert_process_result(
    result: ProcessResult,
    expected_success: bool,
    expected_series_id: int | None = None,
    expected_season: int | None = None,
    expected_episode: int | None = None,
    expected_file_modified: bool | None = None,
    expected_language: str | None = None,
    expected_message_contains: str | None = None,
) -> None:
    """Shared assertion helper for ProcessResult validation."""
    assert result.success == expected_success

    if expected_series_id is not None:
        assert result.tmdb_ids is not None
        assert result.tmdb_ids.series_id == expected_series_id

    if expected_season is not None:
        assert result.tmdb_ids is not None
        assert result.tmdb_ids.season == expected_season

    if expected_episode is not None:
        assert result.tmdb_ids is not None
        assert result.tmdb_ids.episode == expected_episode

    if expected_file_modified is not None:
        assert result.file_modified == expected_file_modified

    if expected_language is not None:
        assert result.selected_language == expected_language

    if expected_message_contains is not None:
        assert expected_message_contains in result.message
