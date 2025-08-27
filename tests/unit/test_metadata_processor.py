"""Unit tests for metadata processor."""

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
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test successful processing of series .nfo files."""
    test_path = create_test_files("tvshow.nfo", test_data_dir / "test_series.nfo")

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
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test successful processing of episode .nfo files."""
    test_path = create_test_files("episode.nfo", test_data_dir / "test_episode.nfo")

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
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test language preference selection through process_file."""
    # Create mock translator with multiple languages
    assert isinstance(processor.translator, Mock)
    processor.translator.get_translations.return_value = {
        "en": TranslatedContent("English Title", "English Description", "en"),
        "zh-CN": TranslatedContent("中文标题", "中文描述", "zh-CN"),
        "ja-JP": TranslatedContent("日本語タイトル", "日本語の説明", "ja-JP"),
    }

    test_path = create_test_files("tvshow.nfo", test_data_dir / "test_lang_pref.nfo")

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
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test processing when no TMDB ID is present."""
    test_path = create_test_files("no_tmdb_id.nfo", test_data_dir / "test_no_tmdb.nfo")

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
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test processing with malformed XML."""
    test_path = create_test_files("invalid.nfo", test_data_dir / "test_invalid.nfo")

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
    processor: MetadataProcessor,
    mock_translator: Mock,
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test processing when translations exist but none match preferred languages."""
    # Mock translator to return translations that don't match preferred languages
    mock_translator.get_translations.return_value = {
        "en": TranslatedContent(
            title="English Title", description="English Description", language="en"
        ),
        "ja-JP": TranslatedContent(
            title="Japanese Title", description="Japanese Description", language="ja-JP"
        ),
    }

    test_path = create_test_files("tvshow.nfo", test_data_dir / "test_no_preferred.nfo")

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


def test_apply_fallback_to_translation_no_fallback_needed(
    processor: MetadataProcessor, create_test_files: Callable[[str, Path], Path]
) -> None:
    """Test fallback logic when translation has both title and description."""
    from sonarr_metadata_rewrite.models import TranslatedContent

    # Create test .nfo file with original content
    test_path = create_test_files(
        "tvshow.nfo", Path(__file__).parent / "data" / "tvshow.nfo"
    )

    translation = TranslatedContent(
        title="完整标题", description="完整描述", language="zh-CN"
    )

    result = processor._apply_fallback_to_translation(test_path, translation)

    # Should return the same translation since both fields are present
    assert result.title == "完整标题"
    assert result.description == "完整描述"
    assert result.language == "zh-CN"


def test_apply_fallback_to_translation_empty_title(
    processor: MetadataProcessor, create_test_files: Callable[[str, Path], Path]
) -> None:
    """Test fallback logic when translation has empty title."""
    from sonarr_metadata_rewrite.models import TranslatedContent

    # Create test .nfo file with original content
    test_path = create_test_files(
        "tvshow.nfo", Path(__file__).parent / "data" / "tvshow.nfo"
    )

    translation = TranslatedContent(title="", description="翻译描述", language="zh-CN")

    result = processor._apply_fallback_to_translation(test_path, translation)

    # Should use original title but keep translated description
    assert result.title == "Breaking Bad"  # Original title from test data
    assert result.description == "翻译描述"  # Translated description
    assert result.language == "zh-CN"


def test_apply_fallback_to_translation_empty_description(
    processor: MetadataProcessor, create_test_files: Callable[[str, Path], Path]
) -> None:
    """Test fallback logic when translation has empty description."""
    from sonarr_metadata_rewrite.models import TranslatedContent

    # Create test .nfo file with original content
    test_path = create_test_files(
        "tvshow.nfo", Path(__file__).parent / "data" / "tvshow.nfo"
    )

    translation = TranslatedContent(title="绝命毒师", description="", language="zh-CN")

    result = processor._apply_fallback_to_translation(test_path, translation)

    # Should use translated title but fallback to original description
    assert result.title == "绝命毒师"  # Translated title
    assert (
        "high school chemistry teacher" in result.description
    )  # Original description from test data
    assert result.language == "zh-CN"


def test_apply_fallback_to_translation_both_empty(
    processor: MetadataProcessor, create_test_files: Callable[[str, Path], Path]
) -> None:
    """Test fallback logic when translation has both empty title and description."""
    from sonarr_metadata_rewrite.models import TranslatedContent

    # Create test .nfo file with original content
    test_path = create_test_files(
        "tvshow.nfo", Path(__file__).parent / "data" / "tvshow.nfo"
    )

    translation = TranslatedContent(title="", description="", language="zh-CN")

    result = processor._apply_fallback_to_translation(test_path, translation)

    # Should use both original title and description
    assert result.title == "Breaking Bad"  # Original title from test data
    assert (
        "high school chemistry teacher" in result.description
    )  # Original description from test data
    assert result.language == "zh-CN"


def test_process_file_multiple_preferred_languages_first_match(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test that first available preferred language is selected."""
    from unittest.mock import Mock

    from sonarr_metadata_rewrite.config import Settings
    from sonarr_metadata_rewrite.metadata_processor import MetadataProcessor
    from sonarr_metadata_rewrite.models import TranslatedContent

    # Setup settings with multiple preferred languages
    settings = Settings(
        tmdb_api_key="test_key_12345",
        rewrite_root_dir=test_data_dir,
        preferred_languages="ko-KR,ja-JP,zh-CN",  # Korean -> Japanese -> Chinese
        periodic_scan_interval_seconds=1,
        original_files_backup_dir=test_data_dir / "backups",
        cache_dir=test_data_dir / "cache",
    )

    # Mock translator with available translations (missing Korean)
    mock_translator = Mock()
    mock_translator.get_translations.return_value = {
        "ja-JP": TranslatedContent("日本語タイトル", "日本語の説明", "ja-JP"),
        "zh-CN": TranslatedContent("中文标题", "中文描述", "zh-CN"),
        "en": TranslatedContent("English Title", "English Description", "en"),
    }

    processor = MetadataProcessor(settings, mock_translator)
    test_path = create_test_files("tvshow.nfo", test_data_dir / "test_multi_lang.nfo")

    result = processor.process_file(test_path)

    # Should select Japanese (ja-JP) as it's first available in preferred languages
    assert_process_result(
        result,
        expected_success=True,
        expected_language="ja-JP",  # Should pick Japanese, not Chinese
        expected_file_modified=True,
        expected_message_contains="Successfully translated",
    )


def test_process_file_multiple_preferred_languages_no_matches(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test when none of the preferred languages are available."""
    from unittest.mock import Mock

    from sonarr_metadata_rewrite.config import Settings
    from sonarr_metadata_rewrite.metadata_processor import MetadataProcessor
    from sonarr_metadata_rewrite.models import TranslatedContent

    # Setup settings with preferred languages that don't match available translations
    settings = Settings(
        tmdb_api_key="test_key_12345",
        rewrite_root_dir=test_data_dir,
        preferred_languages="ko-KR,th-TH,vi-VN",  # Korean, Thai, Vietnamese
        periodic_scan_interval_seconds=1,
        original_files_backup_dir=test_data_dir / "backups",
        cache_dir=test_data_dir / "cache",
    )

    # Mock translator with only different languages available
    mock_translator = Mock()
    mock_translator.get_translations.return_value = {
        "ja-JP": TranslatedContent("日本語タイトル", "日本語の説明", "ja-JP"),
        "zh-CN": TranslatedContent("中文标题", "中文描述", "zh-CN"),
        "en": TranslatedContent("English Title", "English Description", "en"),
        "fr": TranslatedContent("Titre français", "Description française", "fr"),
    }

    processor = MetadataProcessor(settings, mock_translator)
    test_path = create_test_files("tvshow.nfo", test_data_dir / "test_no_preferred.nfo")

    result = processor.process_file(test_path)

    # Should fail with detailed message about preferred vs available languages
    assert result.success is False
    assert result.file_modified is False
    assert result.selected_language is None
    assert "preferred languages [ko-KR, th-TH, vi-VN]" in result.message
    assert "Available: [en, fr, ja-JP, zh-CN]" in result.message  # Should be sorted
    assert "File unchanged" in result.message


def test_process_file_multiple_preferred_languages_partial_matches(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test when some but not all preferred languages are available."""
    from unittest.mock import Mock

    from sonarr_metadata_rewrite.config import Settings
    from sonarr_metadata_rewrite.metadata_processor import MetadataProcessor
    from sonarr_metadata_rewrite.models import TranslatedContent

    # Setup settings with mixed preferred languages (some available, some not)
    settings = Settings(
        tmdb_api_key="test_key_12345",
        rewrite_root_dir=test_data_dir,
        preferred_languages="ar,zh-CN,th-TH,ja-JP",  # Arabic, Chinese, Thai, Japanese
        periodic_scan_interval_seconds=1,
        original_files_backup_dir=test_data_dir / "backups",
        cache_dir=test_data_dir / "cache",
    )

    # Mock translator with some matching languages (missing Arabic and Thai)
    mock_translator = Mock()
    mock_translator.get_translations.return_value = {
        "zh-CN": TranslatedContent("中文标题", "中文描述", "zh-CN"),
        "ja-JP": TranslatedContent("日本語タイトル", "日本語の説明", "ja-JP"),
        "en": TranslatedContent("English Title", "English Description", "en"),
        "de": TranslatedContent("Deutscher Titel", "Deutsche Beschreibung", "de"),
    }

    processor = MetadataProcessor(settings, mock_translator)
    test_path = create_test_files(
        "tvshow.nfo", test_data_dir / "test_partial_match.nfo"
    )

    result = processor.process_file(test_path)

    # Should select Chinese (zh-CN) as it's the first available in preferred order
    assert_process_result(
        result,
        expected_success=True,
        expected_language="zh-CN",  # Should pick Chinese, not Japanese
        expected_file_modified=True,
        expected_message_contains="Successfully translated",
    )


def test_process_file_single_preferred_language_available(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test when only one preferred language is specified and it's available."""
    from unittest.mock import Mock

    from sonarr_metadata_rewrite.config import Settings
    from sonarr_metadata_rewrite.metadata_processor import MetadataProcessor
    from sonarr_metadata_rewrite.models import TranslatedContent

    settings = Settings(
        tmdb_api_key="test_key_12345",
        rewrite_root_dir=test_data_dir,
        preferred_languages="fr",  # Only French
        periodic_scan_interval_seconds=1,
        original_files_backup_dir=test_data_dir / "backups",
        cache_dir=test_data_dir / "cache",
    )

    mock_translator = Mock()
    mock_translator.get_translations.return_value = {
        "fr": TranslatedContent("Titre français", "Description française", "fr"),
        "en": TranslatedContent("English Title", "English Description", "en"),
        "de": TranslatedContent("Deutscher Titel", "Deutsche Beschreibung", "de"),
    }

    processor = MetadataProcessor(settings, mock_translator)
    test_path = create_test_files("tvshow.nfo", test_data_dir / "test_single_lang.nfo")

    result = processor.process_file(test_path)

    assert_process_result(
        result,
        expected_success=True,
        expected_language="fr",
        expected_file_modified=True,
        expected_message_contains="Successfully translated",
    )


def test_process_file_single_preferred_language_not_available(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test when only one preferred language is specified and it's not available."""
    from unittest.mock import Mock

    from sonarr_metadata_rewrite.config import Settings
    from sonarr_metadata_rewrite.metadata_processor import MetadataProcessor
    from sonarr_metadata_rewrite.models import TranslatedContent

    settings = Settings(
        tmdb_api_key="test_key_12345",
        rewrite_root_dir=test_data_dir,
        preferred_languages="ar",  # Only Arabic
        periodic_scan_interval_seconds=1,
        original_files_backup_dir=test_data_dir / "backups",
        cache_dir=test_data_dir / "cache",
    )

    mock_translator = Mock()
    mock_translator.get_translations.return_value = {
        "fr": TranslatedContent("Titre français", "Description française", "fr"),
        "en": TranslatedContent("English Title", "English Description", "en"),
        "zh-CN": TranslatedContent("中文标题", "中文描述", "zh-CN"),
    }

    processor = MetadataProcessor(settings, mock_translator)
    test_path = create_test_files(
        "tvshow.nfo", test_data_dir / "test_single_missing.nfo"
    )

    result = processor.process_file(test_path)

    assert result.success is False
    assert result.file_modified is False
    assert result.selected_language is None
    assert "preferred languages [ar]" in result.message
    assert "Available: [en, fr, zh-CN]" in result.message
    assert "File unchanged" in result.message
