"""Unit tests for metadata processor."""

import xml.etree.ElementTree as ET
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


# Reprocessing Prevention Tests


def create_custom_nfo(path: Path, title: str, plot: str, tmdb_id: int = 1396) -> None:
    """Helper to create custom .nfo files for reprocessing tests."""
    content = f"""<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>{title}</title>
  <plot>{plot}</plot>
  <uniqueid type="tmdb" default="true">{tmdb_id}</uniqueid>
</tvshow>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_content_matches_preferred_translation_skips_processing(
    test_data_dir: Path, mock_translator: Mock
) -> None:
    """Test that processing is skipped when content matches translation."""
    # Create processor with backup enabled
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=test_data_dir,
        preferred_languages="zh-CN",
        original_files_backup_dir=test_data_dir / "backups",
        cache_dir=test_data_dir / "cache",
    )
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo file with Chinese content that matches expected translation
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "中文标题", "中文剧情描述")

    # Mock translator to return the same Chinese translation
    mock_translator.get_translations.return_value = {
        "zh-CN": TranslatedContent(
            title="中文标题", description="中文剧情描述", language="zh-CN"
        )
    }

    result = processor.process_file(nfo_path)

    assert_process_result(
        result,
        expected_success=True,
        expected_file_modified=False,
        expected_language="zh-CN",
        expected_message_contains="already matches preferred translation",
    )


def test_preference_changed_better_translation_available_reprocesses(
    test_data_dir: Path, mock_translator: Mock
) -> None:
    """Test that file is reprocessed when better translation becomes available."""
    # Create processor with backup enabled
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=test_data_dir,
        preferred_languages="zh-CN,ja-JP",  # Chinese preferred over Japanese
        original_files_backup_dir=test_data_dir / "backups",
        cache_dir=test_data_dir / "cache",
    )
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo file with Japanese content
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "日本語タイトル", "日本語の説明")

    # Mock translator: Chinese is now available and preferred over Japanese
    mock_translator.get_translations.return_value = {
        "zh-CN": TranslatedContent(
            title="中文标题", description="中文剧情描述", language="zh-CN"
        ),
        "ja-JP": TranslatedContent(
            title="日本語タイトル", description="日本語の説明", language="ja-JP"
        ),
    }

    result = processor.process_file(nfo_path)

    # Should reprocess to get better Chinese translation
    assert_process_result(
        result,
        expected_success=True,
        expected_file_modified=True,
        expected_language="zh-CN",
        expected_message_contains="Successfully translated",
    )

    # Verify file was actually updated with Chinese content
    tree = ET.parse(nfo_path)
    root = tree.getroot()
    title_elem = root.find("title")
    plot_elem = root.find("plot")
    assert title_elem is not None and title_elem.text == "中文标题"
    assert plot_elem is not None and plot_elem.text == "中文剧情描述"


def test_preference_change_no_translation_reverts_to_original_with_backup(
    test_data_dir: Path,
) -> None:
    """Test reversion to original content when preferences change to unavailable."""
    # Create processor with preferences that won't match available translations
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=test_data_dir,
        preferred_languages="ko-KR,zh-TW",  # Neither available in translations
        original_files_backup_dir=test_data_dir / "backups",
        cache_dir=test_data_dir / "cache",
    )
    mock_translator = Mock(spec=Translator)
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo file with Japanese content
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "日本語タイトル", "日本語の説明")

    # Create backup with original English content
    backup_path = test_data_dir / "backups" / "tvshow.nfo"
    create_custom_nfo(backup_path, "Original Title", "Original plot")

    # Mock translator: No preferred languages available
    mock_translator.get_translations.return_value = {
        "ja-JP": TranslatedContent(
            title="日本語タイトル", description="日本語の説明", language="ja-JP"
        )
    }

    result = processor.process_file(nfo_path)

    # Should revert to original content from backup
    assert_process_result(
        result,
        expected_success=True,
        expected_file_modified=True,
        expected_language="original",
        expected_message_contains="Successfully translated",
    )

    # Verify file was reverted to original English content
    tree = ET.parse(nfo_path)
    root = tree.getroot()
    title_elem = root.find("title")
    plot_elem = root.find("plot")
    assert title_elem is not None and title_elem.text == "Original Title"
    assert plot_elem is not None and plot_elem.text == "Original plot"


def test_multiple_rapid_processing_only_first_modifies(
    test_data_dir: Path, mock_translator: Mock
) -> None:
    """Test that multiple rapid calls to process same file only modify it once."""
    # Create processor with backup enabled
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=test_data_dir,
        preferred_languages="zh-CN",
        original_files_backup_dir=test_data_dir / "backups",
        cache_dir=test_data_dir / "cache",
    )
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo with English content
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "English Title", "English description")

    # Mock translator returns Chinese translation
    mock_translator.get_translations.return_value = {
        "zh-CN": TranslatedContent(
            title="中文标题", description="中文剧情描述", language="zh-CN"
        )
    }

    # First processing - should modify file
    result1 = processor.process_file(nfo_path)
    assert_process_result(
        result1,
        expected_success=True,
        expected_file_modified=True,
        expected_language="zh-CN",
    )

    # Second processing immediately after - should skip
    result2 = processor.process_file(nfo_path)
    assert_process_result(
        result2,
        expected_success=True,
        expected_file_modified=False,
        expected_message_contains="already matches preferred translation",
    )

    # Third processing - still should skip
    result3 = processor.process_file(nfo_path)
    assert_process_result(
        result3,
        expected_success=True,
        expected_file_modified=False,
    )


def test_file_ownership_preserved_during_rewrite(
    test_data_dir: Path, mock_translator: Mock
) -> None:
    """Test that file ownership is preserved when rewriting metadata."""
    import os
    from unittest.mock import patch

    # Create processor
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=test_data_dir,
        preferred_languages="zh-CN",
        cache_dir=test_data_dir / "cache",
    )
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo file with English content
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "English Title", "English description")

    # Get original file ownership
    original_stat = nfo_path.stat()

    # Mock translator returns Chinese translation
    mock_translator.get_translations.return_value = {
        "zh-CN": TranslatedContent(
            title="中文标题", description="中文剧情描述", language="zh-CN"
        )
    }

    # Track calls to os.chown and os.chmod to verify ownership/permissions preservation is attempted
    chown_calls = []
    chmod_calls = []
    original_chown = os.chown
    original_chmod = os.chmod

    def mock_chown(path, uid, gid):
        chown_calls.append((str(path), uid, gid))
        return original_chown(path, uid, gid)

    def mock_chmod(*args, **kwargs):
        # Only track calls to .tmp files (our metadata rewrite calls)
        if len(args) >= 1 and str(args[0]).endswith('.tmp'):
            chmod_calls.append(args)
        return original_chmod(*args, **kwargs)

    with patch("sonarr_metadata_rewrite.metadata_processor.os.chown", side_effect=mock_chown), \
         patch("sonarr_metadata_rewrite.metadata_processor.os.chmod", side_effect=mock_chmod):
        result = processor.process_file(nfo_path)

    # Should succeed
    assert_process_result(
        result,
        expected_success=True,
        expected_file_modified=True,
        expected_language="zh-CN",
    )

    # Verify that os.chown was called with original ownership
    assert len(chown_calls) == 1
    chown_path, chown_uid, chown_gid = chown_calls[0]
    assert chown_path.endswith(".nfo.tmp")
    assert chown_uid == original_stat.st_uid
    assert chown_gid == original_stat.st_gid

    # Verify that os.chmod was called with original permissions
    assert len(chmod_calls) == 1
    chmod_path, chmod_mode = chmod_calls[0]
    assert str(chmod_path).endswith(".nfo.tmp")
    assert chmod_mode == original_stat.st_mode

    # Verify final file has correct ownership and permissions
    final_stat = nfo_path.stat()
    assert final_stat.st_uid == original_stat.st_uid
    assert final_stat.st_gid == original_stat.st_gid
    assert final_stat.st_mode == original_stat.st_mode


def test_graceful_handling_of_ownership_permission_errors(
    test_data_dir: Path, mock_translator: Mock
) -> None:
    """Test that permission errors during ownership preservation are handled gracefully."""
    import os
    from unittest.mock import patch

    # Create processor
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=test_data_dir,
        preferred_languages="zh-CN",
        cache_dir=test_data_dir / "cache",
    )
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo file with English content
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "English Title", "English description")

    # Mock translator returns Chinese translation
    mock_translator.get_translations.return_value = {
        "zh-CN": TranslatedContent(
            title="中文标题", description="中文剧情描述", language="zh-CN"
        )
    }

    # Mock os.chown to raise PermissionError
    with patch("os.chown", side_effect=PermissionError("Permission denied")):
        # Should still succeed despite permission error
        result = processor.process_file(nfo_path)

    # Processing should succeed despite the permission error
    assert_process_result(
        result,
        expected_success=True,
        expected_file_modified=True,
        expected_language="zh-CN",
    )

    # Verify content was updated correctly
    tree = ET.parse(nfo_path)
    root = tree.getroot()
    title_elem = root.find("title")
    plot_elem = root.find("plot")
    assert title_elem is not None and title_elem.text == "中文标题"
    assert plot_elem is not None and plot_elem.text == "中文剧情描述"
