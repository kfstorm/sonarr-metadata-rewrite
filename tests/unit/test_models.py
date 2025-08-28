"""Unit tests for data models."""

from pathlib import Path

from sonarr_metadata_rewrite.models import (
    ExternalIds,
    ProcessResult,
    TmdbIds,
    TranslatedContent,
)


def test_tmdb_ids_series() -> None:
    """Test TmdbIds for series files."""
    tmdb_ids = TmdbIds(series_id=12345)
    assert tmdb_ids.series_id == 12345
    assert tmdb_ids.season is None
    assert tmdb_ids.episode is None


def test_tmdb_ids_episode() -> None:
    """Test TmdbIds for episode files."""
    tmdb_ids = TmdbIds(series_id=12345, season=1, episode=1)
    assert tmdb_ids.series_id == 12345
    assert tmdb_ids.season == 1
    assert tmdb_ids.episode == 1


def test_translated_content() -> None:
    """Test TranslatedContent creation."""
    content = TranslatedContent(
        title="示例剧集", description="这是一个示例描述", language="zh-CN"
    )
    assert content.title == "示例剧集"
    assert content.description == "这是一个示例描述"
    assert content.language == "zh-CN"


def test_external_ids() -> None:
    """Test ExternalIds creation."""
    # Test with both IDs
    external_ids = ExternalIds(tvdb_id=123456, imdb_id="tt1234567")
    assert external_ids.tvdb_id == 123456
    assert external_ids.imdb_id == "tt1234567"

    # Test with only TVDB ID
    tvdb_only = ExternalIds(tvdb_id=789012)
    assert tvdb_only.tvdb_id == 789012
    assert tvdb_only.imdb_id is None

    # Test with only IMDB ID
    imdb_only = ExternalIds(imdb_id="tt7890123")
    assert imdb_only.tvdb_id is None
    assert imdb_only.imdb_id == "tt7890123"

    # Test with no IDs (defaults)
    empty = ExternalIds()
    assert empty.tvdb_id is None
    assert empty.imdb_id is None


def test_process_result() -> None:
    """Test ProcessResult creation."""
    result = ProcessResult(
        success=True,
        file_path=Path("/test/path.nfo"),
        message="Test message",
        tmdb_ids=TmdbIds(series_id=12345),
        translations_found=True,
        backup_created=True,
        file_modified=True,
        selected_language="zh-CN",
    )
    assert result.success is True
    assert result.file_path == Path("/test/path.nfo")
    assert result.message == "Test message"
    assert result.tmdb_ids is not None
    assert result.tmdb_ids.series_id == 12345
    assert result.translations_found is True
    assert result.backup_created is True
    assert result.file_modified is True
    assert result.selected_language == "zh-CN"


def test_process_result_no_translation() -> None:
    """Test ProcessResult for cases with no preferred translation."""
    result = ProcessResult(
        success=False,
        file_path=Path("/test/path.nfo"),
        message=(
            "File unchanged - no translation available in preferred languages [zh-CN]. "
            "Available: [en, ja-JP]"
        ),
        tmdb_ids=TmdbIds(series_id=12345),
        translations_found=True,
        file_modified=False,
        selected_language=None,
    )
    assert result.success is False
    assert result.file_path == Path("/test/path.nfo")
    assert "File unchanged" in result.message
    assert "preferred languages" in result.message
    assert result.tmdb_ids is not None
    assert (
        result.translations_found is True
    )  # Translations were found, just not preferred
    assert result.file_modified is False
    assert result.selected_language is None
