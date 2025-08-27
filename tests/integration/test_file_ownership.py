"""Integration tests for file ownership preservation functionality."""

import os
import stat
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.metadata_processor import MetadataProcessor
from sonarr_metadata_rewrite.models import TranslatedContent


def create_test_nfo(path: Path, title: str = "Test Title", plot: str = "Test plot") -> None:
    """Create a test .nfo file."""
    content = f"""<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>{title}</title>
  <plot>{plot}</plot>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
</tvshow>
"""
    path.write_text(content)


@pytest.mark.skipif(os.getuid() == 0, reason="Cannot test ownership preservation as root")
def test_file_ownership_preservation_in_restricted_environment() -> None:
    """Test that ownership preservation fails gracefully in restricted environments."""
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir)
        nfo_path = test_dir / "tvshow.nfo"
        
        # Create test file
        create_test_nfo(nfo_path)
        
        # Get original permissions
        original_stat = nfo_path.stat()
        
        # Create processor
        settings = Settings(
            tmdb_api_key="test_key",
            rewrite_root_dir=test_dir,
            preferred_languages="zh-CN",
            cache_dir=test_dir / "cache",
        )
        
        mock_translator = Mock()
        mock_translator.get_translations.return_value = {
            "zh-CN": TranslatedContent(
                title="中文标题", description="中文剧情描述", language="zh-CN"
            )
        }
        
        processor = MetadataProcessor(settings, mock_translator)
        
        # Process file - should succeed even if ownership preservation fails
        result = processor.process_file(nfo_path)
        
        # Should succeed (ownership preservation is best-effort)
        assert result.success
        assert result.file_modified
        assert result.selected_language == "zh-CN"
        
        # File should still have correct content
        content = nfo_path.read_text()
        assert "中文标题" in content
        assert "中文剧情描述" in content


def test_file_permissions_preservation() -> None:
    """Test that file permissions are preserved during metadata rewrite."""
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir)
        nfo_path = test_dir / "tvshow.nfo"
        
        # Create test file
        create_test_nfo(nfo_path)
        
        # Set specific permissions (readable and writable by owner only)
        nfo_path.chmod(0o600)
        original_mode = nfo_path.stat().st_mode
        
        # Create processor
        settings = Settings(
            tmdb_api_key="test_key",
            rewrite_root_dir=test_dir,
            preferred_languages="zh-CN",
            cache_dir=test_dir / "cache",
        )
        
        mock_translator = Mock()
        mock_translator.get_translations.return_value = {
            "zh-CN": TranslatedContent(
                title="中文标题", description="中文剧情描述", language="zh-CN"
            )
        }
        
        processor = MetadataProcessor(settings, mock_translator)
        
        # Process file
        result = processor.process_file(nfo_path)
        
        # Should succeed
        assert result.success
        assert result.file_modified
        assert result.selected_language == "zh-CN"
        
        # Permissions should be preserved
        final_mode = nfo_path.stat().st_mode
        assert final_mode == original_mode
        
        # Verify specific permission bits
        assert stat.filemode(final_mode) == "-rw-------"


@pytest.mark.skipif(os.getuid() == 0, reason="Cannot test different users as root")
def test_ownership_preservation_same_user() -> None:
    """Test ownership preservation when running as the same user."""
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir)
        nfo_path = test_dir / "tvshow.nfo"
        
        # Create test file
        create_test_nfo(nfo_path)
        
        # Get original ownership
        original_stat = nfo_path.stat()
        current_uid = os.getuid()
        current_gid = os.getgid()
        
        # Verify we own the file
        assert original_stat.st_uid == current_uid
        assert original_stat.st_gid == current_gid
        
        # Create processor
        settings = Settings(
            tmdb_api_key="test_key",
            rewrite_root_dir=test_dir,
            preferred_languages="zh-CN",
            cache_dir=test_dir / "cache",
        )
        
        mock_translator = Mock()
        mock_translator.get_translations.return_value = {
            "zh-CN": TranslatedContent(
                title="中文标题", description="中文剧情描述", language="zh-CN"
            )
        }
        
        processor = MetadataProcessor(settings, mock_translator)
        
        # Process file
        result = processor.process_file(nfo_path)
        
        # Should succeed
        assert result.success
        assert result.file_modified
        assert result.selected_language == "zh-CN"
        
        # Ownership should be preserved
        final_stat = nfo_path.stat()
        assert final_stat.st_uid == original_stat.st_uid
        assert final_stat.st_gid == original_stat.st_gid


def test_complex_permissions_preservation() -> None:
    """Test preservation of complex file permissions (multiple permission bits)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir)
        nfo_path = test_dir / "tvshow.nfo"
        
        # Create test file
        create_test_nfo(nfo_path)
        
        # Set complex permissions: read/write for owner, read for group, no access for others
        nfo_path.chmod(0o640)
        original_mode = nfo_path.stat().st_mode
        
        # Create processor
        settings = Settings(
            tmdb_api_key="test_key",
            rewrite_root_dir=test_dir,
            preferred_languages="zh-CN",
            cache_dir=test_dir / "cache",
        )
        
        mock_translator = Mock()
        mock_translator.get_translations.return_value = {
            "zh-CN": TranslatedContent(
                title="中文标题", description="中文剧情描述", language="zh-CN"
            )
        }
        
        processor = MetadataProcessor(settings, mock_translator)
        
        # Process file
        result = processor.process_file(nfo_path)
        
        # Should succeed
        assert result.success
        assert result.file_modified
        assert result.selected_language == "zh-CN"
        
        # Complex permissions should be preserved exactly
        final_mode = nfo_path.stat().st_mode
        assert final_mode == original_mode
        
        # Verify specific permission bits
        assert stat.filemode(final_mode) == "-rw-r-----"
        
        # Verify octal permissions
        assert oct(stat.S_IMODE(final_mode)) == "0o640"