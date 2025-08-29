"""Shared test configuration and fixtures."""

import tempfile
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.models import ProcessResult

# Inline test data constants
SAMPLE_TVSHOW_NFO = """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Breaking Bad</title>
  <plot>A high school chemistry teacher diagnosed with inoperable lung cancer turns to manufacturing and selling methamphetamine in order to secure his family's future.</plot>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <uniqueid type="imdb">tt0903747</uniqueid>
  <genre>Drama</genre>
  <genre>Crime</genre>
  <premiered>2008-01-20</premiered>
  <year>2008</year>
  <status>Ended</status>
  <mpaa>TV-MA</mpaa>
  <studio>AMC</studio>
  <runtime>47</runtime>
  <actor>
    <name>Bryan Cranston</name>
    <role>Walter White</role>
    <order>0</order>
  </actor>
  <actor>
    <name>Aaron Paul</name>
    <role>Jesse Pinkman</role>
    <order>1</order>
  </actor>
</tvshow>
"""  # noqa: E501

SAMPLE_EPISODE_NFO = """<?xml version="1.0" encoding="utf-8"?>
<episodedetails>
  <title>Pilot</title>
  <plot>Walter White, a struggling high school chemistry teacher, is diagnosed with advanced lung cancer. He turns to a life of crime, producing and selling methamphetamine with a former student, Jesse Pinkman, with the goal of securing his family's financial future before he dies.</plot>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <uniqueid type="imdb">tt0959621</uniqueid>
  <aired>2008-01-20</aired>
  <season>1</season>
  <episode>1</episode>
  <runtime>58</runtime>
  <director>Vince Gilligan</director>
  <writer>Vince Gilligan</writer>
  <mpaa>TV-MA</mpaa>
  <rating>8.2</rating>
  <votes>25487</votes>
  <actor>
    <name>Bryan Cranston</name>
    <role>Walter White</role>
  </actor>
  <actor>
    <name>Aaron Paul</name>
    <role>Jesse Pinkman</role>
  </actor>
</episodedetails>
"""  # noqa: E501

SAMPLE_NO_TMDB_ID_NFO = """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Series Without TMDB ID</title>
  <plot>This series only has IMDB and TVDB IDs, no TMDB ID for testing</plot>
  <uniqueid type="imdb" default="true">tt1234567</uniqueid>
  <uniqueid type="tvdb">123456</uniqueid>
  <genre>Drama</genre>
  <premiered>2020-01-01</premiered>
</tvshow>
"""

SAMPLE_TVDB_ONLY_NFO = """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Series With TVDB ID Only</title>
  <plot>This series only has TVDB ID for testing TVDB lookup</plot>
  <uniqueid type="tvdb" default="true">123456</uniqueid>
  <genre>Drama</genre>
  <premiered>2020-01-01</premiered>
</tvshow>
"""

SAMPLE_IMDB_ONLY_NFO = """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Series With IMDB ID Only</title>
  <plot>This series only has IMDB ID for testing IMDB lookup</plot>
  <uniqueid type="imdb" default="true">tt1234567</uniqueid>
  <genre>Drama</genre>
  <premiered>2020-01-01</premiered>
</tvshow>
"""

SAMPLE_INVALID_NFO = """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Broken XML Test</title>
  <plot>This file has malformed XML for error testing</plot>
  <uniqueid type="tmdb" default="true">999</uniqueid>
  <genre>Test
  <!-- Missing closing tag for genre -->
</tvshow>
"""

SAMPLE_EPISODE_NO_TMDB_ID_NFO = """<?xml version="1.0" encoding="utf-8"?>
<episodedetails>
  <title>The Journey</title>
  <season>1</season>
  <episode>1</episode>
  <aired>2013-02-11</aired>
  <plot>Emperor penguins cross a treacherous frozen sea to reach their
  breeding grounds.</plot>
  <uniqueid type="tvdb" default="true">4499792</uniqueid>
  <uniqueid type="sonarr">1548</uniqueid>
  <watched>false</watched>
  <runtime>58</runtime>
  <director>John Downer</director>
</episodedetails>
"""

# Map of sample names to content
SAMPLE_DATA = {
    "tvshow.nfo": SAMPLE_TVSHOW_NFO,
    "episode.nfo": SAMPLE_EPISODE_NFO,
    "no_tmdb_id.nfo": SAMPLE_NO_TMDB_ID_NFO,
    "tvdb_only.nfo": SAMPLE_TVDB_ONLY_NFO,
    "imdb_only.nfo": SAMPLE_IMDB_ONLY_NFO,
    "invalid.nfo": SAMPLE_INVALID_NFO,
    "episode_no_tmdb_id.nfo": SAMPLE_EPISODE_NO_TMDB_ID_NFO,
}


@pytest.fixture
def test_data_dir() -> Generator[Path, None, None]:
    """Create a temporary test data directory for all tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


def create_test_settings(test_data_dir: Path, **kwargs: Any) -> Settings:
    """Create test settings with safe defaults and custom overrides.

    Args:
        test_data_dir: Temporary test directory path
        **kwargs: Settings overrides (e.g., preferred_languages="zh-CN,ja-JP")

    Returns:
        Settings object with safe test defaults and any custom overrides
    """
    # Build explicit parameters for Settings constructor
    params = {
        "tmdb_api_key": kwargs.get("tmdb_api_key", "test_key_12345"),
        "rewrite_root_dir": kwargs.get("rewrite_root_dir", test_data_dir),
        "preferred_languages": kwargs.get("preferred_languages", "zh-CN"),
        "periodic_scan_interval_seconds": kwargs.get(
            "periodic_scan_interval_seconds", 1
        ),
        "original_files_backup_dir": kwargs.get(
            "original_files_backup_dir", test_data_dir / "backups"
        ),
        "cache_dir": kwargs.get("cache_dir", test_data_dir / "cache"),
    }

    return Settings(**params)


@pytest.fixture
def test_settings(test_data_dir: Path) -> Settings:
    """Standard test settings using temporary test data directory."""
    return create_test_settings(test_data_dir)


@pytest.fixture
def create_test_files() -> Generator[Callable[[str, Path], Path], None, None]:
    """Factory fixture to create test files from inline data with cleanup."""
    created_files = []

    def _create_file(sample_name: str, dest_path: Path) -> Path:
        """Create a test file from inline sample data."""
        if sample_name not in SAMPLE_DATA:
            raise ValueError(f"Unknown sample: {sample_name}")

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(SAMPLE_DATA[sample_name])
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
