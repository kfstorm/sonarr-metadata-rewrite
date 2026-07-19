"""Unit tests for metadata processor."""

import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock

import pytest

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.metadata_processor import MetadataProcessor
from sonarr_metadata_rewrite.models import (
    EpisodeMetadataInfo,
    MetadataInfo,
    TmdbIds,
    TranslatedContent,
    TranslatedString,
)
from sonarr_metadata_rewrite.translator import Translator
from tests.conftest import (
    SAMPLE_MULTI_EPISODE_NFO,
    assert_process_result,
    create_test_settings,
)


def translated_content(
    title: str, description: str, language: str, tagline: str = ""
) -> TranslatedContent:
    """Create translated content with one language for both fields."""
    return TranslatedContent(
        title=TranslatedString(content=title, language=language),
        description=TranslatedString(content=description, language=language),
        tagline=TranslatedString(content=tagline, language=language),
    )


def multi_episode_processor(
    test_data_dir: Path, create_test_files: Callable[[str, Path], Path]
) -> tuple[MetadataProcessor, Mock, Path]:
    """Create processor and series directory for multi-episode tests."""
    mock_translator = Mock(spec=Translator)
    processor = MetadataProcessor(create_test_settings(test_data_dir), mock_translator)
    series_dir = test_data_dir / "Breaking Bad"
    series_dir.mkdir(parents=True, exist_ok=True)
    create_test_files("tvshow.nfo", series_dir / "tvshow.nfo")
    return processor, mock_translator, series_dir


@pytest.fixture
def mock_translator() -> Mock:
    """Create mock translator."""
    translator = Mock(spec=Translator)
    translator.get_translations.return_value = {
        "zh-CN": translated_content("示例剧集", "这是一个示例描述", "zh-CN")
    }
    # Mock external ID lookup to return None (no external mapping)
    translator.find_tmdb_id_by_external_id.return_value = None
    return translator


@pytest.fixture
def processor(test_settings: Settings, mock_translator: Mock) -> MetadataProcessor:
    """Create metadata processor with mocks."""
    return MetadataProcessor(test_settings, mock_translator)


@pytest.fixture
def test_metadata_info() -> MetadataInfo:
    """Create test MetadataInfo for fallback tests."""
    return MetadataInfo(
        tmdb_id=1396,
        file_type="tvshow",
        title="Breaking Bad",
        description="A high school chemistry teacher diagnosed with lung cancer...",
    )


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
        expected_tmdb_id=1396,
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
        expected_tmdb_id=1396,
        expected_season=1,
        expected_episode=1,
        expected_file_modified=True,
        expected_language="zh-CN",
        expected_message_contains="Successfully translated",
    )


def test_process_file_movie_parses_and_preserves_other_xml_fields(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test movie NFO translation uses movie IDs and changes only title and plot."""
    test_path = create_test_files("movie.nfo", test_data_dir / "movie.nfo")

    result = processor.process_file(test_path)

    assert_process_result(
        result,
        expected_success=True,
        expected_tmdb_id=550,
        expected_file_modified=True,
        expected_language="zh-CN",
    )
    assert result.tmdb_ids is not None
    assert result.tmdb_ids.media_type == "movie"
    root = ET.parse(test_path).getroot()
    assert root.tag == "movie"
    assert root.findtext("title") == "示例剧集"
    assert root.findtext("plot") == "这是一个示例描述"
    assert root.findtext("originaltitle") == "Original Movie Title"
    assert root.findtext("sorttitle") == "Movie, Original"
    assert root.findtext("uniqueid[@type='tmdb']") == "550"
    assert root.findtext("rating") == "8.4"
    assert root.findtext("watched") == "false"


def test_process_file_movie_without_tmdb_id_skips_external_resolution(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test movie NFOs require a direct TMDB ID."""
    test_path = create_test_files("movie_no_tmdb_id.nfo", test_data_dir / "movie.nfo")

    result = processor.process_file(test_path)

    assert_process_result(
        result,
        expected_success=False,
        expected_file_modified=False,
        expected_message_contains="No TMDB ID found",
    )
    assert isinstance(processor.translator, Mock)
    processor.translator.find_tmdb_id_by_external_id.assert_not_called()
    processor.translator.get_translations.assert_not_called()


def test_process_file_language_preference(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test language preference selection through process_file."""
    # Create mock translator with multiple languages
    assert isinstance(processor.translator, Mock)
    processor.translator.get_translations.return_value = {
        "en": translated_content("English Title", "English Description", "en"),
        "zh-CN": translated_content("中文标题", "中文描述", "zh-CN"),
        "ja-JP": translated_content("日本語タイトル", "日本語の説明", "ja-JP"),
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


def test_process_file_episode_no_tmdb_id_with_parent_tvshow(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test processing episode file without TMDB ID but with parent tvshow.nfo."""
    # Create a directory structure like: Series/Season 1/episode.nfo and
    # Series/tvshow.nfo
    series_dir = test_data_dir / "Test Series"
    season_dir = series_dir / "Season 1"
    season_dir.mkdir(parents=True, exist_ok=True)

    # Create tvshow.nfo in the series root with TMDB ID
    create_test_files("tvshow.nfo", series_dir / "tvshow.nfo")

    # Create episode file without TMDB ID in the season directory
    episode_path = create_test_files(
        "episode_no_tmdb_id.nfo", season_dir / "episode.nfo"
    )

    result = processor.process_file(episode_path)

    # Should find TMDB series ID from parent tvshow.nfo and successfully process
    assert_process_result(
        result,
        expected_success=True,
        expected_tmdb_id=1396,  # From tvshow.nfo
        expected_season=1,
        expected_episode=1,
        expected_file_modified=True,
        expected_language="zh-CN",
        expected_message_contains="Successfully translated",
    )


def test_process_file_episode_no_tmdb_id_no_parent_tvshow(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test processing episode file without TMDB ID and no parent tvshow.nfo."""
    # Create episode file without TMDB ID and no parent tvshow.nfo
    episode_path = create_test_files(
        "episode_no_tmdb_id.nfo", test_data_dir / "episode.nfo"
    )

    result = processor.process_file(episode_path)

    # Should fail because no TMDB ID can be found
    assert_process_result(
        result,
        expected_success=False,
        expected_file_modified=False,
        expected_message_contains="No TMDB ID found",
    )


def test_find_parent_metadata_ignores_malformed_nfo(
    processor: MetadataProcessor, test_data_dir: Path
) -> None:
    """Test parent lookup skips malformed NFO files while searching upward."""
    series_dir = test_data_dir / "Series"
    season_dir = series_dir / "Season 1"
    season_dir.mkdir(parents=True)
    episode_path = season_dir / "episode.nfo"
    episode_path.write_text("<episodedetails />", encoding="utf-8")
    (season_dir / "broken.nfo").write_text("<tvshow>", encoding="utf-8")
    (series_dir / "Series.nfo").write_text(
        '<tvshow><uniqueid type="tmdb">1396</uniqueid></tvshow>',
        encoding="utf-8",
    )

    parent = processor._find_parent_metadata_info(episode_path)

    assert parent is not None
    assert parent.tmdb_id == 1396


def test_find_parent_metadata_rejects_ambiguous_roots(
    processor: MetadataProcessor, test_data_dir: Path
) -> None:
    """Test parent lookup rejects directories with multiple TV roots."""
    episode_path = test_data_dir / "Season 1" / "episode.nfo"
    episode_path.parent.mkdir()
    episode_path.write_text("<episodedetails />", encoding="utf-8")
    for name, tmdb_id in (("Series.nfo", 1396), ("tvshow.nfo", 999)):
        (episode_path.parent / name).write_text(
            f'<tvshow><uniqueid type="tmdb">{tmdb_id}</uniqueid></tvshow>',
            encoding="utf-8",
        )

    assert processor._find_parent_metadata_info(episode_path) is None


@pytest.mark.parametrize(
    ("season", "episode"),
    [(None, 1), (1, None)],
)
def test_build_tmdb_ids_rejects_episode_without_numbers(
    processor: MetadataProcessor,
    test_data_dir: Path,
    season: int | None,
    episode: int | None,
) -> None:
    """Test episodes need both season and episode numbers."""
    metadata_info = MetadataInfo(
        tmdb_id=1396,
        file_type="episodedetails",
        season=season,
        episode=episode,
    )

    assert (
        processor._build_tmdb_ids_from_metadata(
            metadata_info, test_data_dir / "episode.nfo"
        )
        is None
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
            title=TranslatedString(content="English Title", language="en"),
            description=TranslatedString(content="English Description", language="en"),
        ),
        "ja-JP": TranslatedContent(
            title=TranslatedString(content="Japanese Title", language="ja-JP"),
            description=TranslatedString(
                content="Japanese Description", language="ja-JP"
            ),
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
    assert result.tmdb_ids.tmdb_id == 1396
    assert result.file_modified is False  # File was not changed
    assert result.translated_content is None


@pytest.fixture
def test_nfo_file(create_test_files: Callable[[str, Path], Path]) -> Path:
    """Create a shared test .nfo file for fallback tests."""
    return create_test_files(
        "tvshow.nfo", Path(__file__).parent / "data" / "tvshow.nfo"
    )


def test_apply_fallback_to_translation_no_fallback_needed(
    processor: MetadataProcessor, test_metadata_info: MetadataInfo
) -> None:
    """Test fallback logic when translation has both title and description."""
    translation = TranslatedContent(
        title=TranslatedString(content="完整标题", language="zh-CN"),
        description=TranslatedString(content="完整描述", language="zh-CN"),
    )

    result = processor._apply_fallback_to_translation(test_metadata_info, translation)

    # Should return the same translation since both fields are present
    assert result.title.content == "完整标题"
    assert result.description.content == "完整描述"
    assert result.title.language == "zh-CN"
    assert result.description.language == "zh-CN"


def test_apply_fallback_to_translation_empty_title(
    processor: MetadataProcessor, test_metadata_info: MetadataInfo
) -> None:
    """Test fallback logic when translation has empty title."""
    translation = TranslatedContent(
        title=TranslatedString(content="", language="zh-CN"),
        description=TranslatedString(content="翻译描述", language="zh-CN"),
    )

    result = processor._apply_fallback_to_translation(test_metadata_info, translation)

    # Should use original title but keep translated description
    assert result.title.content == "Breaking Bad"  # Original title from test data
    assert result.description.content == "翻译描述"  # Translated description
    assert result.title.language == "original"
    assert result.description.language == "zh-CN"


def test_apply_fallback_to_translation_empty_description(
    processor: MetadataProcessor, test_metadata_info: MetadataInfo
) -> None:
    """Test fallback logic when translation has empty description."""
    translation = TranslatedContent(
        title=TranslatedString(content="绝命毒师", language="zh-CN"),
        description=TranslatedString(content="", language="zh-CN"),
    )

    result = processor._apply_fallback_to_translation(test_metadata_info, translation)

    # Should use translated title but fallback to original description
    assert result.title.content == "绝命毒师"  # Translated title
    assert (
        "high school chemistry teacher" in result.description.content
    )  # Original description from test data
    assert result.title.language == "zh-CN"
    assert result.description.language == "original"


def test_apply_fallback_to_translation_both_empty(
    processor: MetadataProcessor, test_metadata_info: MetadataInfo
) -> None:
    """Test fallback logic when translation has both empty title and description."""
    translation = TranslatedContent(
        title=TranslatedString(content="", language="zh-CN"),
        description=TranslatedString(content="", language="zh-CN"),
    )

    result = processor._apply_fallback_to_translation(test_metadata_info, translation)

    # Should use both original title and description
    assert result.title.content == "Breaking Bad"  # Original title from test data
    assert (
        "high school chemistry teacher" in result.description.content
    )  # Original description from test data
    assert result.title.language == "original"
    assert result.description.language == "original"


def test_select_preferred_translation_single_language_complete(
    test_data_dir: Path, mock_translator: Mock
) -> None:
    """Test that complete single-language translation is selected without merging."""
    # Create processor with zh-CN,ja-JP preferences
    settings = create_test_settings(test_data_dir, preferred_languages="zh-CN,ja-JP")
    processor = MetadataProcessor(settings, mock_translator)

    all_translations = {
        "zh-CN": translated_content("中文标题", "中文描述", "zh-CN"),
        "ja-JP": translated_content("日本語タイトル", "日本語の説明", "ja-JP"),
    }

    result = processor._select_preferred_translation(all_translations)

    # Should select complete zh-CN translation without merging
    assert result is not None
    assert result.title.content == "中文标题"
    assert result.title.language == "zh-CN"
    assert result.description.content == "中文描述"
    assert result.description.language == "zh-CN"


def test_select_preferred_translation_partial_with_fallback(
    test_data_dir: Path, mock_translator: Mock
) -> None:
    """Test merging stops once complete translation is found."""
    # Create processor with fr-CA,fr-FR,es preferences
    settings = create_test_settings(test_data_dir, preferred_languages="fr-CA,fr-FR,es")
    processor = MetadataProcessor(settings, mock_translator)

    all_translations = {
        "fr-CA": TranslatedContent(
            title=TranslatedString(content="Titre français-canadien", language="fr-CA"),
            description=TranslatedString(
                content="", language="fr-CA"
            ),  # Empty description
        ),
        "fr-FR": TranslatedContent(
            title=TranslatedString(content="", language="fr-FR"),  # Empty title
            description=TranslatedString(
                content="Description française", language="fr-FR"
            ),
        ),
        "es": TranslatedContent(
            title=TranslatedString(content="Título español", language="es"),
            description=TranslatedString(content="Descripción española", language="es"),
        ),
    }

    result = processor._select_preferred_translation(all_translations)

    # Should merge fr-CA title with fr-FR description, not use es
    assert result is not None
    assert result.title.content == "Titre français-canadien"
    assert result.title.language == "fr-CA"
    assert result.description.content == "Description française"
    assert result.description.language == "fr-FR"


def test_build_success_message_single_language(
    processor: MetadataProcessor,
) -> None:
    """Test _build_success_message for single language translation."""
    translation = TranslatedContent(
        title=TranslatedString(content="中文标题", language="zh-CN"),
        description=TranslatedString(content="中文描述", language="zh-CN"),
    )

    message = processor._build_success_message(translation)

    assert message == "Successfully translated to zh-CN"


def test_build_success_message_mixed_languages(
    processor: MetadataProcessor,
) -> None:
    """Test _build_success_message for mixed language translation."""
    translation = TranslatedContent(
        title=TranslatedString(content="Génération V", language="fr-CA"),
        description=TranslatedString(content="Description française", language="fr-FR"),
    )

    message = processor._build_success_message(translation)

    assert message == "Successfully translated (title: fr-CA, description: fr-FR)"


def test_build_success_message_partial_translation(
    processor: MetadataProcessor,
) -> None:
    """Test _build_success_message when only one field has content."""
    translation = TranslatedContent(
        title=TranslatedString(content="Only Title", language="en"),
        description=TranslatedString(content="", language="unknown"),
    )

    message = processor._build_success_message(translation)

    assert message == "Successfully translated (title: en)"


def test_process_file_multiple_preferred_languages_first_match(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test that first available preferred language is selected."""
    # Setup settings with multiple preferred languages
    settings = create_test_settings(
        test_data_dir,
        preferred_languages="ko-KR,ja-JP,zh-CN",  # Korean -> Japanese -> Chinese
    )

    # Mock translator with available translations (missing Korean)
    mock_translator = Mock()
    mock_translator.get_translations.return_value = {
        "ja-JP": translated_content("日本語タイトル", "日本語の説明", "ja-JP"),
        "zh-CN": translated_content("中文标题", "中文描述", "zh-CN"),
        "en": translated_content("English Title", "English Description", "en"),
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
    # Setup settings with preferred languages that don't match available translations
    settings = create_test_settings(
        test_data_dir,
        preferred_languages="ko-KR,th-TH,vi-VN",  # Korean, Thai, Vietnamese
    )

    # Mock translator with only different languages available
    mock_translator = Mock()
    mock_translator.get_translations.return_value = {
        "ja-JP": TranslatedContent(
            title=TranslatedString(content="日本語タイトル", language="ja-JP"),
            description=TranslatedString(content="日本語の説明", language="ja-JP"),
        ),
        "zh-CN": TranslatedContent(
            title=TranslatedString(content="中文标题", language="zh-CN"),
            description=TranslatedString(content="中文描述", language="zh-CN"),
        ),
        "en": TranslatedContent(
            title=TranslatedString(content="English Title", language="en"),
            description=TranslatedString(content="English Description", language="en"),
        ),
        "fr": TranslatedContent(
            title=TranslatedString(content="Titre français", language="fr"),
            description=TranslatedString(
                content="Description française", language="fr"
            ),
        ),
    }

    processor = MetadataProcessor(settings, mock_translator)
    test_path = create_test_files("tvshow.nfo", test_data_dir / "test_no_preferred.nfo")

    result = processor.process_file(test_path)

    # Should fail with detailed message about preferred vs available languages
    assert result.success is False
    assert result.file_modified is False
    assert result.translated_content is None
    assert "preferred languages [ko-KR, th-TH, vi-VN]" in result.message
    assert "Available: [en, fr, ja-JP, zh-CN]" in result.message  # Should be sorted
    assert "File unchanged" in result.message


def test_process_file_multiple_preferred_languages_partial_matches(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test when some but not all preferred languages are available."""
    # Setup settings with mixed preferred languages (some available, some not)
    settings = create_test_settings(
        test_data_dir,
        preferred_languages="ar,zh-CN,th-TH,ja-JP",  # Arabic, Chinese, Thai, Japanese
    )

    # Mock translator with some matching languages (missing Arabic and Thai)
    mock_translator = Mock()
    mock_translator.get_translations.return_value = {
        "zh-CN": translated_content("中文标题", "中文描述", "zh-CN"),
        "ja-JP": translated_content("日本語タイトル", "日本語の説明", "ja-JP"),
        "en": translated_content("English Title", "English Description", "en"),
        "de": translated_content("Deutscher Titel", "Deutsche Beschreibung", "de"),
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
    settings = create_test_settings(
        test_data_dir,
        preferred_languages="fr",  # Only French
    )

    mock_translator = Mock()
    mock_translator.get_translations.return_value = {
        "fr": translated_content("Titre français", "Description française", "fr"),
        "en": translated_content("English Title", "English Description", "en"),
        "de": translated_content("Deutscher Titel", "Deutsche Beschreibung", "de"),
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
    settings = create_test_settings(
        test_data_dir,
        preferred_languages="ar",  # Only Arabic
    )

    mock_translator = Mock()
    mock_translator.get_translations.return_value = {
        "fr": translated_content("Titre français", "Description française", "fr"),
        "en": translated_content("English Title", "English Description", "en"),
        "zh-CN": translated_content("中文标题", "中文描述", "zh-CN"),
    }

    processor = MetadataProcessor(settings, mock_translator)
    test_path = create_test_files(
        "tvshow.nfo", test_data_dir / "test_single_missing.nfo"
    )

    result = processor.process_file(test_path)

    assert result.success is False
    assert result.file_modified is False
    assert result.translated_content is None
    assert "preferred languages [ar]" in result.message
    assert "Available: [en, fr, zh-CN]" in result.message
    assert "File unchanged" in result.message


# Reprocessing Prevention Tests


def create_custom_nfo(
    path: Path,
    title: str,
    plot: str,
    tmdb_id: int = 1396,
    tagline: str | None = None,
) -> None:
    """Helper to create custom .nfo files for reprocessing tests."""
    tagline_element = f"  <tagline>{tagline}</tagline>\n" if tagline is not None else ""
    content = f"""<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>{title}</title>
  <plot>{plot}</plot>
{tagline_element}  <uniqueid type="tmdb" default="true">{tmdb_id}</uniqueid>
</tvshow>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def parse_nfo_content(nfo_path: Path) -> tuple[str, str]:
    """Helper to parse title and plot from .nfo file."""
    tree = ET.parse(nfo_path)
    root = tree.getroot()
    title_elem = root.find("title")
    plot_elem = root.find("plot")
    title = (title_elem.text or "") if title_elem is not None else ""
    plot = (plot_elem.text or "") if plot_elem is not None else ""
    return title, plot


def test_process_file_adds_tagline_after_plot(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test a translated tagline is added after plot when missing from the NFO."""
    assert isinstance(processor.translator, Mock)
    processor.translator.get_translations.return_value = {
        "zh-CN": translated_content(
            "示例剧集", "这是一个示例描述", "zh-CN", "命运由你掌握。"
        )
    }
    nfo_path = create_test_files("tvshow.nfo", test_data_dir / "tvshow.nfo")

    result = processor.process_file(nfo_path)

    assert result.file_modified is True
    root = ET.parse(nfo_path).getroot()
    assert root.findtext("tagline") == "命运由你掌握。"
    assert [element.tag for element in root].index("tagline") == [
        element.tag for element in root
    ].index("plot") + 1


def test_process_file_tagline_only_preserves_title_and_plot(
    processor: MetadataProcessor, test_data_dir: Path
) -> None:
    """Test a tagline-only translation leaves title and plot unchanged."""
    assert isinstance(processor.translator, Mock)
    processor.translator.get_translations.return_value = {
        "zh-CN": translated_content("", "", "zh-CN", "命运由你掌握。")
    }
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(
        nfo_path, "Original Title", "Original plot", tagline="Old tagline"
    )

    first_result = processor.process_file(nfo_path)
    second_result = processor.process_file(nfo_path)

    assert first_result.file_modified is True
    assert second_result.file_modified is False
    title, plot = parse_nfo_content(nfo_path)
    assert title == "Original Title"
    assert plot == "Original plot"
    assert ET.parse(nfo_path).getroot().findtext("tagline") == "命运由你掌握。"


def test_process_file_preserves_tagline_when_tmdb_value_is_empty(
    processor: MetadataProcessor, test_data_dir: Path
) -> None:
    """Test an empty TMDB tagline cannot overwrite the existing NFO value."""
    assert isinstance(processor.translator, Mock)
    processor.translator.get_translations.return_value = {
        "zh-CN": translated_content("中文标题", "中文剧情", "zh-CN")
    }
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(
        nfo_path, "Original Title", "Original plot", tagline="Old tagline"
    )

    result = processor.process_file(nfo_path)

    assert result.file_modified is True
    assert ET.parse(nfo_path).getroot().findtext("tagline") == "Old tagline"


def test_process_file_restores_and_removes_added_tagline_from_backup(
    processor: MetadataProcessor, test_data_dir: Path
) -> None:
    """Test restoring a backup without a tagline removes an added tagline."""
    nfo_path = test_data_dir / "tvshow.nfo"
    backup_path = test_data_dir / "backups" / nfo_path.relative_to("/")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    create_custom_nfo(backup_path, "Original Title", "Original plot")
    create_custom_nfo(
        nfo_path,
        "中文标题",
        "中文剧情",
        tagline="命运由你掌握。",
    )
    assert isinstance(processor.translator, Mock)
    processor.translator.get_translations.return_value = {}

    result = processor.process_file(nfo_path)

    assert result.file_modified is True
    root = ET.parse(nfo_path).getroot()
    assert root.findtext("title") == "Original Title"
    assert root.findtext("plot") == "Original plot"
    assert root.findall("tagline") == []


def test_process_file_episode_adds_tagline(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test episode NFOs receive non-empty TMDB taglines."""
    assert isinstance(processor.translator, Mock)
    processor.translator.get_translations.return_value = {
        "zh-CN": translated_content(
            "示例剧集", "这是一个示例描述", "zh-CN", "命运由你掌握。"
        )
    }
    nfo_path = create_test_files("episode.nfo", test_data_dir / "episode.nfo")

    result = processor.process_file(nfo_path)

    assert result.file_modified is True
    assert ET.parse(nfo_path).getroot().findtext("tagline") == "命运由你掌握。"


def test_process_file_replaces_duplicate_taglines(
    processor: MetadataProcessor, test_data_dir: Path
) -> None:
    """Test rewriting collapses duplicate tagline elements into one value."""
    assert isinstance(processor.translator, Mock)
    processor.translator.get_translations.return_value = {
        "zh-CN": translated_content("中文标题", "中文剧情", "zh-CN", "新宣传语")
    }
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(
        nfo_path, "Original Title", "Original plot", tagline="Old tagline"
    )
    nfo_path.write_text(
        nfo_path.read_text(encoding="utf-8").replace(
            "  <tagline>Old tagline</tagline>",
            "  <tagline>Old tagline</tagline>\n  <tagline>Duplicate tagline</tagline>",
        ),
        encoding="utf-8",
    )

    processor.process_file(nfo_path)

    taglines = ET.parse(nfo_path).getroot().findall("tagline")
    assert len(taglines) == 1
    assert taglines[0].text == "新宣传语"


def test_process_file_appends_tagline_when_plot_is_missing(
    processor: MetadataProcessor, test_data_dir: Path
) -> None:
    """Test a tagline is appended when an NFO has no plot element."""
    assert isinstance(processor.translator, Mock)
    processor.translator.get_translations.return_value = {
        "zh-CN": translated_content("", "", "zh-CN", "命运由你掌握。")
    }
    nfo_path = test_data_dir / "tvshow.nfo"
    nfo_path.write_text(
        """<tvshow>
  <title>Original Title</title>
  <uniqueid type="tmdb">1396</uniqueid>
</tvshow>
""",
        encoding="utf-8",
    )

    processor.process_file(nfo_path)

    root = ET.parse(nfo_path).getroot()
    assert root[-1].tag == "tagline"
    assert root[-1].text == "命运由你掌握。"


def test_content_matches_preferred_translation_skips_processing(
    test_data_dir: Path, mock_translator: Mock
) -> None:
    """Test that processing is skipped when content matches translation."""
    # Create processor with backup enabled
    settings = create_test_settings(
        test_data_dir,
        tmdb_api_key="test_key",
        preferred_languages="zh-CN",
    )
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo file with Chinese content that matches expected translation
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "中文标题", "中文剧情描述")

    # Mock translator to return the same Chinese translation
    mock_translator.get_translations.return_value = {
        "zh-CN": TranslatedContent(
            title=TranslatedString(content="中文标题", language="zh-CN"),
            description=TranslatedString(content="中文剧情描述", language="zh-CN"),
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
    settings = create_test_settings(
        test_data_dir,
        tmdb_api_key="test_key",
        preferred_languages="zh-CN,ja-JP",  # Chinese preferred over Japanese
    )
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo file with Japanese content
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "日本語タイトル", "日本語の説明")

    # Mock translator: Chinese is now available and preferred over Japanese
    mock_translator.get_translations.return_value = {
        "zh-CN": TranslatedContent(
            title=TranslatedString(content="中文标题", language="zh-CN"),
            description=TranslatedString(content="中文剧情描述", language="zh-CN"),
        ),
        "ja-JP": TranslatedContent(
            title=TranslatedString(content="日本語タイトル", language="ja-JP"),
            description=TranslatedString(content="日本語の説明", language="ja-JP"),
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
    title, plot = parse_nfo_content(nfo_path)
    assert title == "中文标题"
    assert plot == "中文剧情描述"


def test_preference_change_no_translation_reverts_to_original_with_backup(
    test_data_dir: Path,
) -> None:
    """Test reversion to original content when preferences change to unavailable."""
    # Create processor with preferences that won't match available translations
    settings = create_test_settings(
        test_data_dir,
        preferred_languages="ko-KR,zh-TW",  # Neither available in translations
    )
    mock_translator = Mock(spec=Translator)
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo file with Japanese content
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "日本語タイトル", "日本語の説明")

    # Create backup with original English content at the correct absolute-path structure
    backup_root = test_data_dir / "backups"
    backup_path = backup_root / nfo_path.relative_to("/")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    create_custom_nfo(backup_path, "Original Title", "Original plot")

    # Mock translator: No preferred languages available
    mock_translator.get_translations.return_value = {
        "ja-JP": TranslatedContent(
            title=TranslatedString(content="日本語タイトル", language="ja-JP"),
            description=TranslatedString(content="日本語の説明", language="ja-JP"),
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
    title, plot = parse_nfo_content(nfo_path)
    assert title == "Original Title"
    assert plot == "Original plot"


def test_multiple_rapid_processing_only_first_modifies(
    test_data_dir: Path, mock_translator: Mock
) -> None:
    """Test that multiple rapid calls to process same file only modify it once."""
    # Create processor with backup enabled
    settings = create_test_settings(test_data_dir)
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo with English content
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "English Title", "English description")

    # Mock translator returns Chinese translation
    mock_translator.get_translations.return_value = {
        "zh-CN": TranslatedContent(
            title=TranslatedString(content="中文标题", language="zh-CN"),
            description=TranslatedString(content="中文剧情描述", language="zh-CN"),
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


def test_backup_not_overwritten_on_subsequent_processing(
    test_data_dir: Path,
) -> None:
    """Test that backup files are not overwritten on subsequent processing."""
    # Create processor with backup enabled
    settings = create_test_settings(test_data_dir)
    mock_translator = Mock(spec=Translator)
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo with original English content
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "Original English Title", "Original English plot")

    # Mock translator returns Chinese translation
    mock_translator.get_translations.return_value = {
        "zh-CN": TranslatedContent(
            title=TranslatedString(content="中文标题", language="zh-CN"),
            description=TranslatedString(content="中文剧情描述", language="zh-CN"),
        )
    }

    # First processing - should create backup and translate
    result1 = processor.process_file(nfo_path)
    assert_process_result(
        result1,
        expected_success=True,
        expected_file_modified=True,
        expected_language="zh-CN",
    )

    # Verify backup was created with original content
    nfo_path_for_backup = test_data_dir / "tvshow.nfo"
    backup_root = test_data_dir / "backups"
    backup_path = backup_root / nfo_path_for_backup.relative_to("/")
    assert backup_path.exists(), "Backup file should exist"

    title, plot = parse_nfo_content(backup_path)
    assert title == "Original English Title"
    assert plot == "Original English plot"

    # Manually change the file to simulate external modification
    # (e.g., different translation)
    create_custom_nfo(nfo_path, "日本語タイトル", "日本語の説明")

    # Second processing - should NOT overwrite the backup
    result2 = processor.process_file(nfo_path)
    assert_process_result(
        result2,
        expected_success=True,
        expected_file_modified=True,
        expected_language="zh-CN",
    )

    # Verify backup still contains ORIGINAL content, not the Japanese content
    title, plot = parse_nfo_content(backup_path)
    assert title == "Original English Title"
    assert plot == "Original English plot"

    # Verify that backup was NOT overwritten with Japanese content
    backup_content = backup_path.read_text()
    assert "日本語タイトル" not in backup_content, (
        "Backup should not contain Japanese content"
    )
    assert "日本語の説明" not in backup_content, (
        "Backup should not contain Japanese content"
    )


def test_original_language_fallback_selects_original_title(
    test_data_dir: Path,
) -> None:
    """Use original title when matching language has no localized title.

    The original title is valid when its language family matches preference.
    """
    # Create processor with zh-CN as preferred language
    settings = create_test_settings(
        test_data_dir,
        preferred_languages="zh-CN,ja-JP",  # zh-CN is preferred
        original_files_backup_dir=None,  # Disable backups for this test
    )
    mock_translator = Mock(spec=Translator)
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo file with English content
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "Ming Dynasty in 1566", "English description", 68034)

    # Mock translator with zh-CN having empty title
    mock_translator.get_translations.return_value = {
        "zh-CN": TranslatedContent(
            title=TranslatedString(
                content="", language="zh-CN"
            ),  # Empty title - this is the problem!
            description=TranslatedString(
                content="本剧讲述的是嘉靖与海瑞的故事。", language="zh-CN"
            ),
        ),
        "en-US": TranslatedContent(
            title=TranslatedString(content="Ming Dynasty in 1566", language="en-US"),
            description=TranslatedString(
                content="A series based on the events.", language="en-US"
            ),
        ),
    }

    # Mock the original details API call to return Chinese original language
    mock_translator.get_original_details.return_value = ("zh", "大明王朝1566")

    result = processor.process_file(nfo_path)

    # Should successfully use original Chinese title since language families match
    assert_process_result(
        result,
        expected_success=True,
        expected_file_modified=True,
        expected_language="zh-CN",  # Should still report zh-CN as selected
        expected_message_contains="Successfully translated",
    )

    # Verify the file content shows original Chinese title
    tree = ET.parse(nfo_path)
    root = tree.getroot()
    title_elem = root.find("title")
    plot_elem = root.find("plot")

    assert title_elem is not None and title_elem.text == "大明王朝1566"
    assert (
        plot_elem is not None
        and plot_elem.text is not None
        and "本剧讲述" in plot_elem.text
    )


def test_original_language_fallback_does_not_apply_for_different_family(
    test_data_dir: Path,
) -> None:
    """Use standard fallback when original and preferred language families differ.

    Original title fallback only applies within matching language families.
    """
    settings = create_test_settings(
        test_data_dir,
        preferred_languages="zh-CN,ja-JP",
        original_files_backup_dir=None,  # Disable backups for this test
    )
    mock_translator = Mock(spec=Translator)
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo file with English content
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "Breaking Bad", "English description")

    # Mock translator with zh-CN having empty title
    mock_translator.get_translations.return_value = {
        "zh-CN": TranslatedContent(
            title=TranslatedString(content="", language="zh-CN"),  # Empty title
            description=TranslatedString(content="中文描述", language="zh-CN"),
        ),
    }

    # Mock original details to return English original language (different family)
    mock_translator.get_original_details.return_value = ("en", "Breaking Bad")

    result = processor.process_file(nfo_path)

    # Should use standard fallback (original English title from .nfo file)
    assert_process_result(
        result,
        expected_success=True,
        expected_file_modified=True,
        expected_message_contains="Successfully translated",
    )
    assert result.translated_content is not None
    assert (
        result.translated_content.title.content == "Breaking Bad"
    )  # Original from .nfo
    assert result.translated_content.title.language == "original"
    assert (
        result.translated_content.description.content == "中文描述"
    )  # Chinese description
    assert result.translated_content.description.language == "zh-CN"


def test_process_file_tvdb_id_only_success(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test successful processing with only TVDB ID (no TMDB ID)."""
    # Mock external ID lookup to return TMDB ID for TVDB lookup
    assert isinstance(processor.translator, Mock)
    processor.translator.find_tmdb_id_by_external_id.return_value = 1396

    # Use the dedicated TVDB-only fixture
    test_path = create_test_files("tvdb_only.nfo", test_data_dir / "test_tvdb.nfo")
    result = processor.process_file(test_path)

    # Should successfully resolve TMDB ID via TVDB and process
    assert_process_result(
        result,
        expected_success=True,
        expected_tmdb_id=1396,
        expected_file_modified=True,
        expected_language="zh-CN",
        expected_message_contains="Successfully translated",
    )

    # Verify external ID lookup was called with correct parameters
    processor.translator.find_tmdb_id_by_external_id.assert_called_with(
        "123456", "tvdb_id"
    )


def test_process_file_imdb_id_only_success(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
    mock_translator: Mock,
) -> None:
    """Test successful processing with only IMDB ID (no TMDB ID)."""
    # Create processor with mock that returns TMDB ID for IMDB lookup

    settings = create_test_settings(test_data_dir)

    # Mock external ID lookup to return TMDB ID for IMDB lookup
    mock_translator.find_tmdb_id_by_external_id.return_value = 1396
    processor = MetadataProcessor(settings, mock_translator)

    # Use the dedicated IMDB-only fixture
    test_path = create_test_files("imdb_only.nfo", test_data_dir / "test_imdb.nfo")
    result = processor.process_file(test_path)

    # Should successfully resolve TMDB ID via IMDB and process
    assert_process_result(
        result,
        expected_success=True,
        expected_tmdb_id=1396,
        expected_file_modified=True,
        expected_language="zh-CN",
        expected_message_contains="Successfully translated",
    )

    # Verify external ID lookup was called with correct IMDB ID
    mock_translator.find_tmdb_id_by_external_id.assert_called_with(
        "tt1234567", "imdb_id"
    )


def test_process_file_episode_inherits_parent_tvdb_id(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test episode without IDs inheriting TVDB ID from parent tvshow.nfo."""
    settings = create_test_settings(test_data_dir)

    mock_translator = Mock(spec=Translator)
    mock_translator.get_translations.return_value = {
        "zh-CN": translated_content("示例剧集", "这是一个示例描述", "zh-CN")
    }
    # Mock external ID lookup to return TMDB ID for TVDB lookup
    mock_translator.find_tmdb_id_by_external_id.return_value = 1396
    processor = MetadataProcessor(settings, mock_translator)

    # Create directory structure: Series/Season 1/episode.nfo and Series/tvshow.nfo
    series_dir = test_data_dir / "Test Series"
    season_dir = series_dir / "Season 1"
    season_dir.mkdir(parents=True, exist_ok=True)

    # Create tvshow.nfo with only external IDs (no TMDB ID)
    create_test_files("no_tmdb_id.nfo", series_dir / "tvshow.nfo")

    # Create episode file without any IDs
    episode_nfo = """<?xml version="1.0" encoding="utf-8"?>
<episodedetails>
  <title>Episode Title</title>
  <plot>Episode description</plot>
  <season>1</season>
  <episode>1</episode>
</episodedetails>
"""
    episode_path = season_dir / "episode.nfo"
    episode_path.write_text(episode_nfo)

    result = processor.process_file(episode_path)

    # Should successfully resolve TMDB ID via parent's TVDB ID
    assert_process_result(
        result,
        expected_success=True,
        expected_tmdb_id=1396,
        expected_season=1,
        expected_episode=1,
        expected_file_modified=True,
        expected_language="zh-CN",
    )

    # Verify external ID lookup was called for parent's TVDB ID
    mock_translator.find_tmdb_id_by_external_id.assert_called_with("123456", "tvdb_id")


def test_process_file_external_id_lookup_fails(
    processor: MetadataProcessor,
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test graceful failure when external ID lookup fails."""
    # Mock external ID lookup to return None (lookup fails)
    assert isinstance(processor.translator, Mock)
    processor.translator.find_tmdb_id_by_external_id.return_value = None

    # Use the existing no_tmdb_id fixture which has external IDs but no TMDB ID
    test_path = create_test_files("no_tmdb_id.nfo", test_data_dir / "test_fail.nfo")
    result = processor.process_file(test_path)

    # Should fail gracefully when no TMDB ID can be resolved
    assert_process_result(
        result,
        expected_success=False,
        expected_file_modified=False,
        expected_message_contains="No TMDB ID found",
    )

    # Verify both external ID lookups were attempted
    calls = processor.translator.find_tmdb_id_by_external_id.call_args_list
    assert len(calls) == 2  # Should try both TVDB and IMDB
    assert ("123456", "tvdb_id") in [call.args for call in calls]
    assert ("tt1234567", "imdb_id") in [call.args for call in calls]


def test_process_file_mixed_id_scenarios(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test episode with external ID while parent has TMDB ID (parent wins)."""
    settings = create_test_settings(test_data_dir)

    mock_translator = Mock(spec=Translator)
    mock_translator.get_translations.return_value = {
        "zh-CN": translated_content("示例剧集", "这是一个示例描述", "zh-CN")
    }
    # Mock external ID lookup to return different TMDB ID
    mock_translator.find_tmdb_id_by_external_id.return_value = 2468
    processor = MetadataProcessor(settings, mock_translator)

    # Create directory structure
    series_dir = test_data_dir / "Mixed ID Series"
    season_dir = series_dir / "Season 1"
    season_dir.mkdir(parents=True, exist_ok=True)

    # Create parent tvshow.nfo with direct TMDB ID
    create_test_files("tvshow.nfo", series_dir / "tvshow.nfo")

    # Create episode file with external ID but no TMDB ID
    create_test_files("episode_no_tmdb_id.nfo", season_dir / "episode.nfo")

    result = processor.process_file(season_dir / "episode.nfo")

    # Should use parent TMDB ID (1396) rather than external ID lookup (2468)
    # This tests the hierarchical resolution: parent TMDB ID has higher priority
    assert_process_result(
        result,
        expected_success=True,
        expected_tmdb_id=1396,  # From parent TMDB ID, not external lookup
        expected_season=1,
        expected_episode=1,
        expected_file_modified=True,
        expected_language="zh-CN",
    )

    # Verify external ID lookup was NOT called since parent TMDB ID was available
    mock_translator.find_tmdb_id_by_external_id.assert_not_called()


def test_process_file_episode_external_id_priority_over_parent_external_id(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test episode external ID takes priority over parent external ID."""
    settings = create_test_settings(test_data_dir)

    mock_translator = Mock(spec=Translator)
    mock_translator.get_translations.return_value = {
        "zh-CN": translated_content("示例剧集", "这是一个示例描述", "zh-CN")
    }
    # Mock external ID lookup to return TMDB ID for episode's external ID
    mock_translator.find_tmdb_id_by_external_id.return_value = 2468
    processor = MetadataProcessor(settings, mock_translator)

    # Create directory structure
    series_dir = test_data_dir / "External Priority Series"
    season_dir = series_dir / "Season 1"
    season_dir.mkdir(parents=True, exist_ok=True)

    # Create parent tvshow.nfo with only external IDs (no TMDB ID)
    create_test_files("no_tmdb_id.nfo", series_dir / "tvshow.nfo")

    # Create episode file with different external ID but no TMDB ID
    create_test_files("episode_no_tmdb_id.nfo", season_dir / "episode.nfo")

    result = processor.process_file(season_dir / "episode.nfo")

    # Should use episode's external ID lookup result (2468)
    assert_process_result(
        result,
        expected_success=True,
        expected_tmdb_id=2468,  # From episode's external ID lookup
        expected_season=1,
        expected_episode=1,
        expected_file_modified=True,
        expected_language="zh-CN",
    )

    # Verify external ID lookup was called for episode's TVDB ID (4499792)
    # Should NOT be called for parent's IDs since episode has its own
    mock_translator.find_tmdb_id_by_external_id.assert_called_with("4499792", "tvdb_id")


def test_content_matches_after_fallback_skips_processing(
    test_data_dir: Path,
) -> None:
    """Test that content matching works correctly after fallback fills empty fields."""
    # Create processor with zh-CN as preferred language
    settings = create_test_settings(
        test_data_dir,
        preferred_languages="zh-CN",
    )
    mock_translator = Mock(spec=Translator)
    processor = MetadataProcessor(settings, mock_translator)

    # Create .nfo file with Chinese content that matches final result after fallback
    # Current content: Chinese title + Chinese description
    nfo_path = test_data_dir / "tvshow.nfo"
    create_custom_nfo(nfo_path, "示例剧集", "这是一个示例描述")

    # Mock translator: zh-CN translation has Chinese description but empty title
    # After fallback: title="示例剧集" (from original), description="这是一个示例描述"
    mock_translator.get_translations.return_value = {
        "zh-CN": TranslatedContent(
            title=TranslatedString(
                content="", language="zh-CN"
            ),  # Empty - will fallback to original
            description=TranslatedString(content="这是一个示例描述", language="zh-CN"),
        )
    }

    result = processor.process_file(nfo_path)

    # Should detect content matches final result after fallback and skip processing
    assert_process_result(
        result,
        expected_success=True,
        expected_file_modified=False,  # Key test: should NOT modify file
        expected_message_contains="already matches preferred translation",
    )

    # Verify the translated content reflects the fallback result
    assert result.translated_content is not None
    assert (
        result.translated_content.title.content == "示例剧集"
    )  # From fallback (original)
    assert result.translated_content.title.language == "original"  # Fallback language
    assert result.translated_content.description.content == "这是一个示例描述"
    assert result.translated_content.description.language == "zh-CN"  # From translation


def test_process_file_multi_episode_partial_update(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test partial translation updates for multi-episode NFO files."""
    processor, mock_translator, series_dir = multi_episode_processor(
        test_data_dir, create_test_files
    )
    nfo_path = create_test_files("multi_episode.nfo", series_dir / "episodes.nfo")

    def get_translations(tmdb_ids: TmdbIds) -> dict[str, TranslatedContent]:
        if tmdb_ids.episode == 1:
            return {
                "zh-CN": translated_content("试播集", "沃尔特开始了犯罪生涯。", "zh-CN")
            }
        return {}

    mock_translator.get_translations.side_effect = get_translations
    mock_translator.find_tmdb_id_by_external_id.return_value = None

    result = processor.process_file(nfo_path)

    assert_process_result(
        result,
        expected_success=True,
        expected_tmdb_id=1396,
        expected_season=1,
        expected_episode=1,
        expected_file_modified=True,
        expected_language="zh-CN",
        expected_message_contains="1 of 2 episodes updated",
    )

    content = nfo_path.read_text(encoding="utf-8")
    assert "试播集" in content
    assert "沃尔特开始了犯罪生涯。" in content
    assert "Cat's in the Bag..." in content
    assert "Walt and Jesse deal with the aftermath." in content


def test_process_file_multi_episode_restore_from_backup_when_translation_missing(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test multi-episode file restores individual episodes from backup."""
    settings = create_test_settings(test_data_dir)
    mock_translator = Mock(spec=Translator)
    processor = MetadataProcessor(settings, mock_translator)

    series_dir = test_data_dir / "Breaking Bad"
    series_dir.mkdir(parents=True, exist_ok=True)

    nfo_path = series_dir / "episodes.nfo"

    # Create backup at the correct absolute-path structure
    backup_root = test_data_dir / "backups"
    backup_path = backup_root / nfo_path.relative_to("/")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    create_test_files("multi_episode.nfo", backup_path)

    create_test_files("tvshow.nfo", series_dir / "tvshow.nfo")

    translated_multi_episode = """<?xml version="1.0" encoding="utf-8"?>
<episodedetails>
  <title>试播集</title>
  <plot>沃尔特开始了犯罪生涯。</plot>
  <season>1</season>
  <episode>1</episode>
  <uniqueid type="tvdb" default="true">349232</uniqueid>
</episodedetails>
<episodedetails>
  <title>猫在袋中</title>
  <plot>沃尔特和杰西处理后果。</plot>
  <season>1</season>
  <episode>2</episode>
  <uniqueid type="tvdb" default="true">349233</uniqueid>
</episodedetails>
"""
    nfo_path = series_dir / "episodes.nfo"
    nfo_path.write_text(translated_multi_episode, encoding="utf-8")

    mock_translator.get_translations.return_value = {}
    mock_translator.find_tmdb_id_by_external_id.return_value = None

    result = processor.process_file(nfo_path)

    assert_process_result(
        result,
        expected_success=True,
        expected_tmdb_id=1396,
        expected_season=1,
        expected_episode=1,
        expected_file_modified=True,
        expected_message_contains="2 of 2 episodes updated",
    )

    restored_content = nfo_path.read_text(encoding="utf-8")
    assert "Pilot" in restored_content
    assert "Cat's in the Bag..." in restored_content
    assert "试播集" not in restored_content


def test_process_file_multi_episode_no_translation_available(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test multi-episode file returns unchanged when no entries are translatable."""
    settings = create_test_settings(test_data_dir)
    mock_translator = Mock(spec=Translator)
    processor = MetadataProcessor(settings, mock_translator)

    series_dir = test_data_dir / "Breaking Bad"
    backup_dir = test_data_dir / "backups" / "Breaking Bad"
    series_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    create_test_files("tvshow.nfo", series_dir / "tvshow.nfo")
    create_test_files("multi_episode.nfo", backup_dir / "episodes.nfo")
    nfo_path = create_test_files("multi_episode.nfo", series_dir / "episodes.nfo")

    mock_translator.get_translations.return_value = {}
    mock_translator.find_tmdb_id_by_external_id.return_value = None

    result = processor.process_file(nfo_path)

    assert_process_result(
        result,
        expected_success=False,
        expected_tmdb_id=1396,
        expected_season=1,
        expected_episode=1,
        expected_file_modified=False,
        expected_message_contains="no episode translation available",
    )


def test_process_file_multi_episode_skips_entry_without_episode_numbers(
    test_data_dir: Path,
) -> None:
    """Test multi-episode processing skips entries missing season or episode."""
    settings = create_test_settings(test_data_dir)
    mock_translator = Mock(spec=Translator)
    processor = MetadataProcessor(settings, mock_translator)

    series_dir = test_data_dir / "Breaking Bad"
    series_dir.mkdir(parents=True, exist_ok=True)
    (series_dir / "tvshow.nfo").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Breaking Bad</title>
  <plot>A chemistry teacher turns to crime.</plot>
  <uniqueid type="tmdb">1396</uniqueid>
</tvshow>
""",
        encoding="utf-8",
    )
    nfo_path = series_dir / "episodes.nfo"
    nfo_path.write_text(
        SAMPLE_MULTI_EPISODE_NFO.replace(
            "<season>1</season>\n  <episode>2</episode>",
            "<season>1</season>",
        ),
        encoding="utf-8",
    )

    mock_translator.get_translations.return_value = {
        "zh-CN": translated_content("试播集", "沃尔特开始了犯罪生涯。", "zh-CN")
    }
    mock_translator.find_tmdb_id_by_external_id.return_value = None

    result = processor.process_file(nfo_path)

    assert_process_result(
        result,
        expected_success=True,
        expected_tmdb_id=1396,
        expected_season=1,
        expected_episode=1,
        expected_file_modified=True,
        expected_message_contains="1 left unchanged",
    )


def test_process_file_multi_episode_reports_already_matched_entries(
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test multi-episode message includes already matched entries."""
    processor, mock_translator, series_dir = multi_episode_processor(
        test_data_dir, create_test_files
    )
    nfo_path = series_dir / "episodes.nfo"
    nfo_path.write_text(
        SAMPLE_MULTI_EPISODE_NFO.replace("Pilot", "试播集").replace(
            "Walter White begins a new life in crime.", "沃尔特开始了犯罪生涯。"
        ),
        encoding="utf-8",
    )

    def get_translations(tmdb_ids: TmdbIds) -> dict[str, TranslatedContent]:
        if tmdb_ids.episode == 1:
            return {
                "zh-CN": translated_content("试播集", "沃尔特开始了犯罪生涯。", "zh-CN")
            }
        return {"zh-CN": translated_content("袋中猫", "两人处理善后。", "zh-CN")}

    mock_translator.get_translations.side_effect = get_translations
    mock_translator.find_tmdb_id_by_external_id.return_value = None

    result = processor.process_file(nfo_path)

    assert_process_result(
        result,
        expected_success=True,
        expected_tmdb_id=1396,
        expected_season=1,
        expected_episode=1,
        expected_file_modified=True,
        expected_message_contains="1 already matched",
    )


def test_write_translated_metadata_with_tree_requires_xml_tree(
    processor: MetadataProcessor,
    test_data_dir: Path,
) -> None:
    """Test single-document writer rejects missing XML trees."""
    with pytest.raises(ValueError, match="XML tree cannot be None"):
        processor._write_translated_metadata_with_tree(
            None,
            test_data_dir / "out.nfo",
            TranslatedContent(
                title=TranslatedString(content="Title", language="en"),
                description=TranslatedString(content="Plot", language="en"),
            ),
        )


def test_write_translated_episode_entries_requires_xml_tree(
    processor: MetadataProcessor,
    test_data_dir: Path,
) -> None:
    """Test multi-document writer rejects missing XML trees."""
    with pytest.raises(ValueError, match="Episode XML tree cannot be None"):
        processor._write_translated_episode_entries(
            [EpisodeMetadataInfo()],
            test_data_dir / "out.nfo",
            {},
        )
