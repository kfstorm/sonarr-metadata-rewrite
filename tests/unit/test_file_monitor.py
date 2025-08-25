"""Unit tests for file monitor."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.file_monitor import FileMonitor, NFOFileHandler


@pytest.fixture
def file_monitor(test_settings: Settings) -> FileMonitor:
    """Create file monitor instance."""
    return FileMonitor(test_settings)


def test_file_monitor_initialization(file_monitor: FileMonitor) -> None:
    """Test file monitor initialization."""
    assert file_monitor.settings is not None
    assert file_monitor.observer is None
    assert file_monitor.handler is None
    assert not file_monitor.is_running()


def test_nfo_file_handler() -> None:
    """Test NFO file event handler."""
    callback = Mock()
    handler = NFOFileHandler(callback)

    # Create mock file system event for .nfo file
    mock_event = Mock()
    mock_event.is_directory = False
    mock_event.src_path = "/test/path/tvshow.nfo"

    handler.on_created(mock_event)
    callback.assert_called_once_with(Path("/test/path/tvshow.nfo"))

    callback.reset_mock()
    handler.on_modified(mock_event)
    callback.assert_called_once_with(Path("/test/path/tvshow.nfo"))


def test_nfo_file_handler_case_insensitive() -> None:
    """Test that handler detects both .nfo and .NFO files."""
    callback = Mock()
    handler = NFOFileHandler(callback)

    # Test lowercase .nfo file
    mock_event_lower = Mock()
    mock_event_lower.is_directory = False
    mock_event_lower.src_path = "/test/path/tvshow.nfo"

    handler.on_created(mock_event_lower)
    callback.assert_called_with(Path("/test/path/tvshow.nfo"))

    # Test uppercase .NFO file
    callback.reset_mock()
    mock_event_upper = Mock()
    mock_event_upper.is_directory = False
    mock_event_upper.src_path = "/test/path/episode.NFO"

    handler.on_created(mock_event_upper)
    callback.assert_called_with(Path("/test/path/episode.NFO"))


def test_nfo_file_handler_ignores_non_nfo() -> None:
    """Test that handler ignores non-.nfo files."""
    callback = Mock()
    handler = NFOFileHandler(callback)

    mock_event = Mock()
    mock_event.is_directory = False
    mock_event.src_path = "/test/path/regular.txt"

    handler.on_created(mock_event)
    callback.assert_not_called()


def test_monitor_start_stop(file_monitor: FileMonitor) -> None:
    """Test monitor start/stop functionality."""
    callback = Mock()

    # Create the directory first since watchdog needs it to exist
    file_monitor.settings.rewrite_root_dir.mkdir(parents=True, exist_ok=True)

    # Start monitoring
    file_monitor.start(callback)
    assert file_monitor.observer is not None
    assert file_monitor.handler is not None
    assert file_monitor.is_running()

    # Stop monitoring
    file_monitor.stop()
    assert file_monitor.observer is None
    assert file_monitor.handler is None
    assert not file_monitor.is_running()
