"""Unit tests for data models."""

from pathlib import Path

from sonarr_metadata_rewrite.models import (
    MetadataProcessResult,
    TmdbIds,
    TranslatedContent,
    TranslatedString,
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
        title=TranslatedString(content="示例剧集", language="zh-CN"),
        description=TranslatedString(content="这是一个示例描述", language="zh-CN"),
    )
    assert content.title.content == "示例剧集"
    assert content.description.content == "这是一个示例描述"
    assert content.title.language == "zh-CN"
    assert content.description.language == "zh-CN"


def test_process_result() -> None:
    """Test MetadataProcessResult creation."""
    translated_content = TranslatedContent(
        title=TranslatedString(content="测试标题", language="zh-CN"),
        description=TranslatedString(content="测试描述", language="zh-CN"),
    )
    result = MetadataProcessResult(
        success=True,
        file_path=Path("/test/path.nfo"),
        message="Test message",
        tmdb_ids=TmdbIds(series_id=12345),
        backup_created=True,
        file_modified=True,
        translated_content=translated_content,
    )
    assert result.success is True
    assert result.file_path == Path("/test/path.nfo")
    assert result.message == "Test message"
    assert result.tmdb_ids is not None
    assert result.tmdb_ids.series_id == 12345
    assert result.backup_created is True
    assert result.file_modified is True
    assert result.translated_content is not None
    assert result.translated_content.title.content == "测试标题"


def test_process_result_no_translation() -> None:
    """Test MetadataProcessResult for cases with no preferred translation."""
    result = MetadataProcessResult(
        success=False,
        file_path=Path("/test/path.nfo"),
        message=(
            "File unchanged - no translation available in preferred languages [zh-CN]. "
            "Available: [en, ja-JP]"
        ),
        tmdb_ids=TmdbIds(series_id=12345),
        file_modified=False,
        translated_content=None,
    )
    assert result.success is False
    assert result.file_path == Path("/test/path.nfo")
    assert "File unchanged" in result.message
    assert "preferred languages" in result.message
    assert result.tmdb_ids is not None
    assert result.file_modified is False
    assert result.translated_content is None
