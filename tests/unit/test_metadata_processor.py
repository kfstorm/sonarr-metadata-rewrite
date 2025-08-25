"""Unit tests for metadata processor."""

import shutil
from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock

import pytest

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.metadata_processor import MetadataProcessor
from sonarr_metadata_rewrite.models import TranslatedContent
from sonarr_metadata_rewrite.translator import Translator
from tests.conftest import assert_process_result


@pytest.fixture
def mock_translator() -> Mock:
    """Create mock translator."""
    translator = Mock(spec=Translator)
    translator.get_translations.return_value = {
        "zh-CN": TranslatedContent(
            title="示例剧集", description="这是一个示例描述", language="zh-CN"
        )
    }
    return translator


@pytest.fixture
def processor(test_settings: Settings, mock_translator: Mock) -> MetadataProcessor:
    """Create metadata processor with mocks."""
    return MetadataProcessor(test_settings, mock_translator)


def test_process_file_series_success(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[Path, Path], Path],
) -> None:
    """Test successful processing of series .nfo files."""
    sample_path = test_data_dir / "samples" / "tvshow.nfo"
    test_path = create_test_files(sample_path, test_data_dir / "test_series.nfo")

    result = processor.process_file(test_path)

    assert_process_result(
        result,
        expected_success=True,
        expected_series_id=1396,
        expected_file_modified=True,
        expected_language="zh-CN",
        expected_message_contains="Successfully translated",
    )


def test_process_file_episode_success(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[Path, Path], Path],
) -> None:
    """Test successful processing of episode .nfo files."""
    sample_path = test_data_dir / "samples" / "episode.nfo"
    test_path = create_test_files(sample_path, test_data_dir / "test_episode.nfo")

    result = processor.process_file(test_path)

    assert_process_result(
        result,
        expected_success=True,
        expected_series_id=1396,
        expected_season=1,
        expected_episode=1,
        expected_file_modified=True,
        expected_language="zh-CN",
        expected_message_contains="Successfully translated",
    )


def test_process_file_language_preference(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[Path, Path], Path],
) -> None:
    """Test language preference selection through process_file."""
    # Create mock translator with multiple languages
    assert isinstance(processor.translator, Mock)
    processor.translator.get_translations.return_value = {
        "en": TranslatedContent("English Title", "English Description", "en"),
        "zh-CN": TranslatedContent("中文标题", "中文描述", "zh-CN"),
        "ja-JP": TranslatedContent("日本語タイトル", "日本語の説明", "ja-JP"),
    }

    sample_path = test_data_dir / "samples" / "tvshow.nfo"
    test_path = create_test_files(sample_path, test_data_dir / "test_lang_pref.nfo")

    result = processor.process_file(test_path)

    assert_process_result(
        result,
        expected_success=True,
        expected_language="zh-CN",  # First in preferred_languages list
        expected_file_modified=True,
    )


def test_process_file_no_tmdb_id(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[Path, Path], Path],
) -> None:
    """Test processing when no TMDB ID is present."""
    sample_path = test_data_dir / "samples" / "no_tmdb_id.nfo"
    test_path = create_test_files(sample_path, test_data_dir / "test_no_tmdb.nfo")

    result = processor.process_file(test_path)

    assert_process_result(
        result,
        expected_success=False,
        expected_file_modified=False,
        expected_message_contains="No TMDB ID found",
    )


def test_process_file_invalid_xml(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[Path, Path], Path],
) -> None:
    """Test processing with malformed XML."""
    sample_path = test_data_dir / "samples" / "invalid.nfo"
    test_path = create_test_files(sample_path, test_data_dir / "test_invalid.nfo")

    result = processor.process_file(test_path)

    assert_process_result(
        result,
        expected_success=False,
        expected_file_modified=False,
        expected_message_contains="Processing error",
    )


def test_process_file_nonexistent_file(
    processor: MetadataProcessor, test_data_dir: Path
) -> None:
    """Test processing with nonexistent file."""
    nonexistent_path = test_data_dir / "nonexistent_file.nfo"

    result = processor.process_file(nonexistent_path)

    assert_process_result(
        result,
        expected_success=False,
        expected_file_modified=False,
        expected_message_contains="Processing error",
    )


def test_process_file_no_preferred_translation(
    processor: MetadataProcessor, mock_translator: Mock, test_data_dir: Path
) -> None:
    """Test processing when translations exist but none match preferred languages."""
    sample_path = test_data_dir / "samples" / "tvshow.nfo"

    # Mock translator to return translations that don't match preferred languages
    mock_translator.get_translations.return_value = {
        "en": TranslatedContent(
            title="English Title", description="English Description", language="en"
        ),
        "ja-JP": TranslatedContent(
            title="Japanese Title", description="Japanese Description", language="ja-JP"
        ),
    }

    # Copy sample to test data directory for processing
    test_path = test_data_dir / "test_no_preferred.nfo"
    shutil.copy2(sample_path, test_path)

    try:
        result = processor.process_file(test_path)

        assert result.success is False  # No work was accomplished
        assert result.file_path == test_path
        assert "File unchanged" in result.message
        assert "preferred languages [zh-CN]" in result.message
        assert "Available: [en, ja-JP]" in result.message
        assert result.tmdb_ids is not None
        assert result.tmdb_ids.series_id == 1396
        assert (
            result.translations_found is True
        )  # Translations were found, just not preferred
        assert result.file_modified is False  # File was not changed
        assert result.selected_language is None
    finally:
        # Clean up test file
        if test_path.exists():
            test_path.unlink()
