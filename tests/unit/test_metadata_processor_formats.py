"""Unit tests for metadata processor with different formats."""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.metadata_processor import MetadataProcessor
from sonarr_metadata_rewrite.models import TranslatedContent


# Test data for different formats
EMBY_SERIES_NFO = """<?xml version="1.0" encoding="utf-8"?>
<series>
  <title>Breaking Bad</title>
  <overview>A high school chemistry teacher diagnosed with inoperable lung cancer turns to manufacturing and selling methamphetamine in order to secure his family's future.</overview>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <uniqueid type="imdb">tt0903747</uniqueid>
</series>
"""

EMBY_EPISODE_NFO = """<?xml version="1.0" encoding="utf-8"?>
<episode>
  <title>Pilot</title>
  <overview>Walter White, a struggling high school chemistry teacher, is diagnosed with advanced lung cancer.</overview>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <season>1</season>
  <episode>1</episode>
</episode>
"""

UNSUPPORTED_NFO = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>Some Movie</title>
  <plot>This is a movie format, not supported</plot>
</movie>
"""


@pytest.fixture
def temp_nfo_file():
    """Create a temporary .nfo file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".nfo", delete=False) as f:
        temp_path = Path(f.name)
    yield temp_path
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_translator():
    """Mock translator that returns test translations."""
    translator = Mock()
    translator.get_translations.return_value = {
        "zh-CN": TranslatedContent("中文标题", "中文描述", "zh-CN"),
        "ja-JP": TranslatedContent("日本語タイトル", "日本語の説明", "ja-JP"),
    }
    return translator


def test_metadata_processor_auto_format_detection_kodi(temp_dir, mock_translator):
    """Test automatic format detection with Kodi format."""
    # Create settings with auto format detection
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=temp_dir,
        preferred_languages="zh-CN",
        metadata_format="auto",  # Auto-detect format
        cache_dir=temp_dir / "cache",
        original_files_backup_dir=temp_dir / "backups",
    )
    
    # Create Kodi format file inside the root directory
    nfo_file = temp_dir / "test_show" / "tvshow.nfo"
    nfo_file.parent.mkdir(parents=True, exist_ok=True)
    
    kodi_content = """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Breaking Bad</title>
  <plot>Original English description</plot>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
</tvshow>
"""
    nfo_file.write_text(kodi_content)
    
    # Test processing
    processor = MetadataProcessor(settings, mock_translator)
    result = processor.process_file(nfo_file)
    
    assert result.success is True
    assert result.selected_language == "zh-CN"
    assert "Successfully translated" in result.message
    
    # Verify the file was updated correctly
    updated_content = nfo_file.read_text()
    assert "中文标题" in updated_content
    assert "中文描述" in updated_content


def test_metadata_processor_auto_format_detection_emby(temp_dir, mock_translator):
    """Test automatic format detection with Emby format."""
    # Create settings with auto format detection
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=temp_dir,
        preferred_languages="zh-CN",
        metadata_format="auto",  # Auto-detect format
        cache_dir=temp_dir / "cache",
        original_files_backup_dir=temp_dir / "backups",
    )
    
    # Create Emby format file inside the root directory
    nfo_file = temp_dir / "test_show" / "tvshow.nfo"
    nfo_file.parent.mkdir(parents=True, exist_ok=True)
    
    nfo_file.write_text(EMBY_SERIES_NFO)
    
    # Test processing
    processor = MetadataProcessor(settings, mock_translator)
    result = processor.process_file(nfo_file)
    
    assert result.success is True
    assert result.selected_language == "zh-CN"
    assert "Successfully translated" in result.message
    
    # Verify the file was updated correctly
    updated_content = nfo_file.read_text()
    assert "中文标题" in updated_content
    assert "中文描述" in updated_content


def test_metadata_processor_explicit_kodi_format(temp_dir, mock_translator):
    """Test explicit Kodi format configuration."""
    # Create settings with explicit Kodi format
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=temp_dir,
        preferred_languages="ja-JP",
        metadata_format="kodi",  # Explicit Kodi format
        cache_dir=temp_dir / "cache",
        original_files_backup_dir=temp_dir / "backups",
    )
    
    # Create Kodi format file inside the root directory
    nfo_file = temp_dir / "test_show" / "tvshow.nfo"
    nfo_file.parent.mkdir(parents=True, exist_ok=True)
    
    kodi_content = """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Breaking Bad</title>
  <plot>Original English description</plot>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
</tvshow>
"""
    nfo_file.write_text(kodi_content)
    
    # Test processing
    processor = MetadataProcessor(settings, mock_translator)
    result = processor.process_file(nfo_file)
    
    assert result.success is True
    assert result.selected_language == "ja-JP"
    assert "Successfully translated" in result.message
    
    # Verify the file was updated correctly with Japanese translation
    updated_content = nfo_file.read_text()
    assert "日本語タイトル" in updated_content
    assert "日本語の説明" in updated_content


def test_metadata_processor_explicit_emby_format(temp_dir, mock_translator):
    """Test explicit Emby format configuration."""
    # Create settings with explicit Emby format
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=temp_dir,
        preferred_languages="ja-JP",
        metadata_format="emby",  # Explicit Emby format
        cache_dir=temp_dir / "cache", 
        original_files_backup_dir=temp_dir / "backups",
    )
    
    # Create Emby format file inside the root directory
    nfo_file = temp_dir / "test_show" / "tvshow.nfo"
    nfo_file.parent.mkdir(parents=True, exist_ok=True)
    
    nfo_file.write_text(EMBY_SERIES_NFO)
    
    # Test processing
    processor = MetadataProcessor(settings, mock_translator)
    result = processor.process_file(nfo_file)
    
    assert result.success is True
    assert result.selected_language == "ja-JP"
    assert "Successfully translated" in result.message
    
    # Verify the file was updated correctly with Japanese translation
    updated_content = nfo_file.read_text()
    assert "日本語タイトル" in updated_content
    assert "日本語の説明" in updated_content


def test_metadata_processor_unsupported_format(temp_dir, mock_translator):
    """Test handling of unsupported metadata format."""
    # Create settings with auto format detection
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=temp_dir,
        preferred_languages="zh-CN",
        metadata_format="auto",  # Auto-detect format
        cache_dir=temp_dir / "cache",
        original_files_backup_dir=temp_dir / "backups",
    )
    
    # Create unsupported format file inside the root directory
    nfo_file = temp_dir / "test_movie" / "movie.nfo"
    nfo_file.parent.mkdir(parents=True, exist_ok=True)
    
    nfo_file.write_text(UNSUPPORTED_NFO)
    
    # Test processing
    processor = MetadataProcessor(settings, mock_translator)
    result = processor.process_file(nfo_file)
    
    assert result.success is False
    assert "Unsupported metadata format" in result.message
    assert result.selected_language is None


def test_metadata_processor_invalid_format_config_fallback(temp_dir, mock_translator):
    """Test fallback to auto-detection when invalid format is configured."""
    # Create settings with invalid format
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=temp_dir,
        preferred_languages="zh-CN",
        metadata_format="invalid_format",  # Invalid format
        cache_dir=temp_dir / "cache",
        original_files_backup_dir=temp_dir / "backups",
    )
    
    # Create valid Kodi format file inside the root directory
    nfo_file = temp_dir / "test_show" / "tvshow.nfo"
    nfo_file.parent.mkdir(parents=True, exist_ok=True)
    
    kodi_content = """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Breaking Bad</title>
  <plot>Original English description</plot>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
</tvshow>
"""
    nfo_file.write_text(kodi_content)
    
    # Test processing - should fall back to auto-detection
    processor = MetadataProcessor(settings, mock_translator)
    result = processor.process_file(nfo_file)
    
    assert result.success is True
    assert result.selected_language == "zh-CN"
    assert "Successfully translated" in result.message


def test_metadata_processor_emby_episode_format(temp_dir, mock_translator):
    """Test processing Emby episode format."""
    # Create settings for Emby format
    settings = Settings(
        tmdb_api_key="test_key",
        rewrite_root_dir=temp_dir,
        preferred_languages="zh-CN",
        metadata_format="emby",
        cache_dir=temp_dir / "cache",
        original_files_backup_dir=temp_dir / "backups",
    )
    
    # Create Emby episode format file inside the root directory
    nfo_file = temp_dir / "test_show" / "Season 01" / "S01E01.nfo"
    nfo_file.parent.mkdir(parents=True, exist_ok=True)
    
    nfo_file.write_text(EMBY_EPISODE_NFO)
    
    # Test processing
    processor = MetadataProcessor(settings, mock_translator)
    result = processor.process_file(nfo_file)
    
    assert result.success is True
    assert result.selected_language == "zh-CN"
    assert "Successfully translated" in result.message
    assert result.tmdb_ids is not None
    assert result.tmdb_ids.series_id == 1396
    assert result.tmdb_ids.season == 1
    assert result.tmdb_ids.episode == 1
    
    # Verify the file was updated correctly
    updated_content = nfo_file.read_text()
    assert "中文标题" in updated_content
    assert "中文描述" in updated_content