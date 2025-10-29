"""Unit tests for data models."""

from pathlib import Path

from sonarr_metadata_rewrite.models import (
    ImageCandidate,
    ImageProcessResult,
    MetadataProcessResult,
    ProcessResult,
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


# Image-specific model tests


def test_image_candidate_initialization() -> None:
    """Test ImageCandidate model initialization."""
    candidate = ImageCandidate(
        file_path="/test_poster.jpg", iso_639_1="en", iso_3166_1="US"
    )
    assert candidate.file_path == "/test_poster.jpg"
    assert candidate.iso_639_1 == "en"
    assert candidate.iso_3166_1 == "US"


def test_image_process_result_initialization() -> None:
    """Test ImageProcessResult model initialization."""
    result = ImageProcessResult(
        success=True,
        file_path=Path("/test/poster.jpg"),
        message="Poster rewritten successfully",
        kind="poster",
        backup_created=True,
        file_modified=True,
        selected_language="en-US",
        selected_file_path="/poster_en.jpg",
    )
    # Image-specific fields
    assert result.kind == "poster"
    assert result.selected_language == "en-US"
    assert result.selected_file_path == "/poster_en.jpg"

    # Inherited fields from ProcessResult
    assert result.success is True
    assert result.file_path == Path("/test/poster.jpg")
    assert result.message == "Poster rewritten successfully"
    assert result.backup_created is True
    assert result.file_modified is True


def test_process_result_base_class() -> None:
    """Test base ProcessResult class."""
    result = ProcessResult(
        success=True, file_path=Path("/test/file.txt"), message="Test message"
    )
    assert result.success is True
    assert result.file_path == Path("/test/file.txt")
    assert result.message == "Test message"
    assert result.backup_created is False  # Default value
    assert result.file_modified is False  # Default value
    assert result.exception is None  # Default value


def test_metadata_process_result_backward_compatibility() -> None:
    """Test MetadataProcessResult maintains compatibility."""
    translated_content = TranslatedContent(
        title=TranslatedString(content="中文标题", language="zh-CN"),
        description=TranslatedString(content="中文描述", language="zh-CN"),
    )
    result = MetadataProcessResult(
        success=True,
        file_path=Path("/test/tvshow.nfo"),
        message="NFO updated",
        tmdb_ids=TmdbIds(series_id=999, season=1, episode=1),
        backup_created=True,
        file_modified=True,
        translated_content=translated_content,
    )

    # Metadata-specific fields
    assert result.tmdb_ids is not None
    assert result.tmdb_ids.series_id == 999
    assert result.tmdb_ids.season == 1
    assert result.tmdb_ids.episode == 1
    assert result.translated_content is not None
    assert result.translated_content.title.content == "中文标题"

    # Inherited base fields
    assert result.success is True
    assert result.file_path == Path("/test/tvshow.nfo")
    assert result.backup_created is True
