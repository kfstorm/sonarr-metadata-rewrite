"""Unit tests for metadata formats."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from sonarr_metadata_rewrite.metadata_formats import (
    METADATA_FORMATS,
    EmbyMetadataFormat,
    KodiMetadataFormat,
    detect_metadata_format,
    get_metadata_format,
)
from sonarr_metadata_rewrite.models import TranslatedContent

# Test data for different formats
KODI_TVSHOW_NFO = (
    """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Breaking Bad</title>
  <plot>A high school chemistry teacher diagnosed with inoperable """
    """lung cancer turns to manufacturing and selling """
    """methamphetamine to secure his family's future.</plot>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <uniqueid type="imdb">tt0903747</uniqueid>
</tvshow>
"""
)

KODI_EPISODE_NFO = """<?xml version="1.0" encoding="utf-8"?>
<episodedetails>
  <title>Pilot</title>
  <plot>Walter White, a struggling high school chemistry teacher.</plot>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <season>1</season>
  <episode>1</episode>
</episodedetails>
"""

EMBY_TVSHOW_NFO = (
    """<?xml version="1.0" encoding="utf-8"?>
<series>
  <title>Breaking Bad</title>
  <overview>A high school chemistry teacher diagnosed with inoperable """
    """lung cancer turns to manufacturing and selling """
    """methamphetamine to secure his family's future.</overview>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <uniqueid type="imdb">tt0903747</uniqueid>
</series>
"""
)

EMBY_EPISODE_NFO = """<?xml version="1.0" encoding="utf-8"?>
<episode>
  <title>Pilot</title>
  <overview>Walter White, a struggling high school chemistry teacher.</overview>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <season>1</season>
  <episode>1</episode>
</episode>
"""

EMBY_MIXED_NFO = """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Mixed Format</title>
  <overview>This has overview instead of plot</overview>
  <uniqueid type="tmdb" default="true">999</uniqueid>
</tvshow>
"""


@pytest.fixture
def temp_nfo_file() -> Generator[Path, None, None]:
    """Create a temporary .nfo file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".nfo", delete=False) as f:
        temp_path = Path(f.name)
    yield temp_path
    if temp_path.exists():
        temp_path.unlink()


def test_kodi_format_extract_tmdb_ids_tvshow(temp_nfo_file: Path) -> None:
    """Test TMDB ID extraction from Kodi tvshow format."""
    temp_nfo_file.write_text(KODI_TVSHOW_NFO)

    format_handler = KodiMetadataFormat()
    tmdb_ids = format_handler.extract_tmdb_ids(temp_nfo_file)

    assert tmdb_ids is not None
    assert tmdb_ids.series_id == 1396
    assert tmdb_ids.season is None
    assert tmdb_ids.episode is None


def test_kodi_format_extract_tmdb_ids_episode(temp_nfo_file: Path) -> None:
    """Test TMDB ID extraction from Kodi episode format."""
    temp_nfo_file.write_text(KODI_EPISODE_NFO)

    format_handler = KodiMetadataFormat()
    tmdb_ids = format_handler.extract_tmdb_ids(temp_nfo_file)

    assert tmdb_ids is not None
    assert tmdb_ids.series_id == 1396
    assert tmdb_ids.season == 1
    assert tmdb_ids.episode == 1


def test_kodi_format_extract_content(temp_nfo_file: Path) -> None:
    """Test content extraction from Kodi format."""
    temp_nfo_file.write_text(KODI_TVSHOW_NFO)

    format_handler = KodiMetadataFormat()
    title, description = format_handler.extract_content(temp_nfo_file)

    assert title == "Breaking Bad"
    assert "high school chemistry teacher" in description


def test_kodi_format_write_translated_metadata(temp_nfo_file: Path) -> None:
    """Test writing translated metadata to Kodi format."""
    temp_nfo_file.write_text(KODI_TVSHOW_NFO)

    format_handler = KodiMetadataFormat()
    translation = TranslatedContent(
        title="测试标题", description="测试描述", language="zh-CN"
    )

    format_handler.write_translated_metadata(temp_nfo_file, translation)

    # Verify the content was updated
    title, description = format_handler.extract_content(temp_nfo_file)
    assert title == "测试标题"
    assert description == "测试描述"


def test_kodi_format_supports_file(temp_nfo_file: Path) -> None:
    """Test Kodi format detection."""
    format_handler = KodiMetadataFormat()

    # Test tvshow format
    temp_nfo_file.write_text(KODI_TVSHOW_NFO)
    assert format_handler.supports_file(temp_nfo_file) is True

    # Test episode format
    temp_nfo_file.write_text(KODI_EPISODE_NFO)
    assert format_handler.supports_file(temp_nfo_file) is True

    # Test unsupported format
    temp_nfo_file.write_text("<movie><title>Test</title></movie>")
    assert format_handler.supports_file(temp_nfo_file) is False


def test_emby_format_extract_tmdb_ids_series(temp_nfo_file: Path) -> None:
    """Test TMDB ID extraction from Emby series format."""
    temp_nfo_file.write_text(EMBY_TVSHOW_NFO)

    format_handler = EmbyMetadataFormat()
    tmdb_ids = format_handler.extract_tmdb_ids(temp_nfo_file)

    assert tmdb_ids is not None
    assert tmdb_ids.series_id == 1396
    assert tmdb_ids.season is None
    assert tmdb_ids.episode is None


def test_emby_format_extract_tmdb_ids_episode(temp_nfo_file: Path) -> None:
    """Test TMDB ID extraction from Emby episode format."""
    temp_nfo_file.write_text(EMBY_EPISODE_NFO)

    format_handler = EmbyMetadataFormat()
    tmdb_ids = format_handler.extract_tmdb_ids(temp_nfo_file)

    assert tmdb_ids is not None
    assert tmdb_ids.series_id == 1396
    assert tmdb_ids.season == 1
    assert tmdb_ids.episode == 1


def test_emby_format_extract_content_overview(temp_nfo_file: Path) -> None:
    """Test content extraction from Emby format with overview."""
    temp_nfo_file.write_text(EMBY_TVSHOW_NFO)

    format_handler = EmbyMetadataFormat()
    title, description = format_handler.extract_content(temp_nfo_file)

    assert title == "Breaking Bad"
    assert "high school chemistry teacher" in description


def test_emby_format_extract_content_mixed(temp_nfo_file: Path) -> None:
    """Test content extraction from mixed format (tvshow + overview)."""
    temp_nfo_file.write_text(EMBY_MIXED_NFO)

    format_handler = EmbyMetadataFormat()
    title, description = format_handler.extract_content(temp_nfo_file)

    assert title == "Mixed Format"
    assert description == "This has overview instead of plot"


def test_emby_format_write_translated_metadata_overview(temp_nfo_file: Path) -> None:
    """Test writing translated metadata to Emby format with overview."""
    temp_nfo_file.write_text(EMBY_TVSHOW_NFO)

    format_handler = EmbyMetadataFormat()
    translation = TranslatedContent(
        title="测试标题", description="测试描述", language="zh-CN"
    )

    format_handler.write_translated_metadata(temp_nfo_file, translation)

    # Verify the content was updated
    title, description = format_handler.extract_content(temp_nfo_file)
    assert title == "测试标题"
    assert description == "测试描述"


def test_emby_format_write_translated_metadata_plot_fallback(
    temp_nfo_file: Path,
) -> None:
    """Test writing translated metadata to Emby format with plot fallback."""
    # Create an Emby-style file with plot instead of overview
    nfo_content = """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Test Show</title>
  <plot>Original plot</plot>
  <uniqueid type="tmdb" default="true">999</uniqueid>
</tvshow>
"""
    temp_nfo_file.write_text(nfo_content)

    format_handler = EmbyMetadataFormat()
    translation = TranslatedContent(
        title="测试标题", description="测试描述", language="zh-CN"
    )

    format_handler.write_translated_metadata(temp_nfo_file, translation)

    # Verify the content was updated via plot element
    title, description = format_handler.extract_content(temp_nfo_file)
    assert title == "测试标题"
    assert description == "测试描述"


def test_emby_format_supports_file(temp_nfo_file: Path) -> None:
    """Test Emby format detection."""
    format_handler = EmbyMetadataFormat()

    # Test series format
    temp_nfo_file.write_text(EMBY_TVSHOW_NFO)
    assert format_handler.supports_file(temp_nfo_file) is True

    # Test episode format
    temp_nfo_file.write_text(EMBY_EPISODE_NFO)
    assert format_handler.supports_file(temp_nfo_file) is True


def test_get_metadata_format() -> None:
    """Test metadata format retrieval by name."""
    kodi_format = get_metadata_format("kodi")
    assert isinstance(kodi_format, KodiMetadataFormat)

    emby_format = get_metadata_format("emby")
    assert isinstance(emby_format, EmbyMetadataFormat)

    with pytest.raises(ValueError, match="Unsupported format 'invalid'"):
        get_metadata_format("invalid")


def test_detect_metadata_format(temp_nfo_file: Path) -> None:
    """Test automatic metadata format detection."""
    # Test Kodi format detection
    temp_nfo_file.write_text(KODI_TVSHOW_NFO)
    format_handler = detect_metadata_format(temp_nfo_file)
    assert isinstance(format_handler, KodiMetadataFormat)

    # Test Emby series format detection
    temp_nfo_file.write_text(EMBY_TVSHOW_NFO)
    format_handler = detect_metadata_format(temp_nfo_file)
    # Note: Both Kodi and Emby handlers support this, so either is valid
    assert format_handler is not None

    # Test unsupported format
    temp_nfo_file.write_text("<movie><title>Test</title></movie>")
    format_handler = detect_metadata_format(temp_nfo_file)
    assert format_handler is None


def test_metadata_formats_registry() -> None:
    """Test the metadata formats registry."""
    assert "kodi" in METADATA_FORMATS
    assert "emby" in METADATA_FORMATS
    assert METADATA_FORMATS["kodi"] == KodiMetadataFormat
    assert METADATA_FORMATS["emby"] == EmbyMetadataFormat
