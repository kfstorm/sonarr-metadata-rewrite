"""Unit tests for file scanner."""

import shutil
from pathlib import Path
from unittest.mock import Mock

import pytest

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.file_scanner import FileScanner


@pytest.fixture
def file_scanner(test_settings: Settings) -> FileScanner:
    """Create file scanner instance."""
    return FileScanner(test_settings)


def test_file_scanner_initialization(file_scanner: FileScanner) -> None:
    """Test file scanner initialization."""
    assert file_scanner.settings is not None
    assert file_scanner.scan_thread is None
    assert file_scanner.stop_event is None
    assert file_scanner.callback is None
    assert not file_scanner.is_running()


def test_scanner_start_stop(file_scanner: FileScanner) -> None:
    """Test scanner start/stop functionality."""
    callback = Mock()

    # Start scanning
    file_scanner.start(callback)
    assert file_scanner.scan_thread is not None
    assert file_scanner.stop_event is not None
    assert file_scanner.callback == callback
    assert file_scanner.is_running()

    # Stop scanning
    file_scanner.stop()
    assert file_scanner.scan_thread is None
    assert file_scanner.stop_event is None
    assert file_scanner.callback is None
    assert not file_scanner.is_running()


def test_scanner_finds_nfo_files_through_start(
    file_scanner: FileScanner, callback_tracker: Mock
) -> None:
    """Test that scanner finds .nfo files recursively through public interface."""
    # Use a dedicated test subdirectory
    test_dir = file_scanner.settings.rewrite_root_dir / "test_scan"
    original_root = file_scanner.settings.rewrite_root_dir
    file_scanner.settings.rewrite_root_dir = test_dir

    try:
        test_files = [
            test_dir / "tvshow.nfo",
            test_dir / "subdir" / "episode.nfo",
            test_dir / "other.txt",  # Should be ignored
        ]

        # Create directories and files
        for test_file in test_files:
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.touch()

        # Start scanner with callback
        file_scanner.start(callback_tracker)

        # Give scanner time to run initial scan
        import time

        time.sleep(0.1)

        # Stop scanner
        file_scanner.stop()

        # Check that callback was called for .nfo files only
        assert callback_tracker.call_count == 2
        called_paths = {call[0][0] for call in callback_tracker.call_args_list}
        assert test_dir / "tvshow.nfo" in called_paths
        assert test_dir / "subdir" / "episode.nfo" in called_paths
    finally:
        # Clean up test files and restore original root
        if test_dir.exists():
            shutil.rmtree(test_dir)
        file_scanner.settings.rewrite_root_dir = original_root


def test_scanner_case_insensitive_detection(
    file_scanner: FileScanner, callback_tracker: Mock
) -> None:
    """Test that scanner detects both .nfo and .NFO files through public interface."""
    # Use a dedicated test subdirectory
    test_dir = file_scanner.settings.rewrite_root_dir / "test_case_scan"
    original_root = file_scanner.settings.rewrite_root_dir
    file_scanner.settings.rewrite_root_dir = test_dir

    try:
        test_files = [
            test_dir / "tvshow.nfo",  # lowercase
            test_dir / "series.NFO",  # uppercase
            test_dir / "subdir" / "episode.nfo",  # lowercase in subdir
            test_dir / "subdir" / "special.NFO",  # uppercase in subdir
            test_dir / "other.txt",  # Should be ignored
        ]

        # Create directories and files
        for test_file in test_files:
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.touch()

        # Start scanner with callback
        file_scanner.start(callback_tracker)

        # Give scanner time to run initial scan
        import time

        time.sleep(0.1)

        # Stop scanner
        file_scanner.stop()

        # Check that callback was called for all .nfo/.NFO files
        assert callback_tracker.call_count == 4
        called_paths = {call[0][0] for call in callback_tracker.call_args_list}
        assert test_dir / "tvshow.nfo" in called_paths
        assert test_dir / "series.NFO" in called_paths
        assert test_dir / "subdir" / "episode.nfo" in called_paths
        assert test_dir / "subdir" / "special.NFO" in called_paths
    finally:
        # Clean up test files and restore original root
        if test_dir.exists():
            shutil.rmtree(test_dir)
        file_scanner.settings.rewrite_root_dir = original_root


def test_scanner_missing_directory_handling(
    file_scanner: FileScanner, callback_tracker: Mock
) -> None:
    """Test scanning when root directory doesn't exist through public interface."""
    original_root = file_scanner.settings.rewrite_root_dir

    try:
        # Set non-existent directory
        file_scanner.settings.rewrite_root_dir = Path("/nonexistent/directory")

        # Start scanner - should not raise exception
        file_scanner.start(callback_tracker)

        # Give scanner time to try scanning
        import time

        time.sleep(0.1)

        # Stop scanner
        file_scanner.stop()

        # Should not have called callback for non-existent directory
        callback_tracker.assert_not_called()
    finally:
        file_scanner.settings.rewrite_root_dir = original_root
