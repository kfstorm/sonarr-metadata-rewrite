"""Unit tests for file monitor."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from watchdog.events import (
    EVENT_TYPE_CLOSED,
    FileClosedEvent,
    FileCreatedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.file_monitor import FileMonitor, MediaFileHandler


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


def test_media_file_handler() -> None:
    """Test media file event handler."""
    callback = Mock()
    handler = MediaFileHandler(callback)

    # Test closed event for .nfo file
    event = FileClosedEvent("/test/path/tvshow.nfo")
    handler.on_any_event(event)
    callback.assert_called_once_with(Path("/test/path/tvshow.nfo"))


def test_media_file_handler_case_insensitive() -> None:
    """Test that handler detects both .nfo and .NFO files."""
    callback = Mock()
    handler = MediaFileHandler(callback)

    # Test lowercase .nfo file
    event_lower = FileClosedEvent("/test/path/tvshow.nfo")
    handler.on_any_event(event_lower)
    callback.assert_called_with(Path("/test/path/tvshow.nfo"))

    # Test uppercase .NFO file
    callback.reset_mock()
    event_upper = FileClosedEvent("/test/path/episode.NFO")
    handler.on_any_event(event_upper)
    callback.assert_called_with(Path("/test/path/episode.NFO"))


def test_media_file_handler_handles_images() -> None:
    """Test that handler detects rewritable image files."""
    callback = Mock()
    handler = MediaFileHandler(callback)

    # Test poster.jpg
    event_poster = FileClosedEvent("/test/path/poster.jpg")
    handler.on_any_event(event_poster)
    callback.assert_called_with(Path("/test/path/poster.jpg"))

    # Test season01-poster.png
    callback.reset_mock()
    event_season = FileClosedEvent("/test/path/season01-poster.png")
    handler.on_any_event(event_season)
    callback.assert_called_with(Path("/test/path/season01-poster.png"))

    # Test clearlogo.jpeg
    callback.reset_mock()
    event_clearlogo = FileClosedEvent("/test/path/clearlogo.jpeg")
    handler.on_any_event(event_clearlogo)
    callback.assert_called_with(Path("/test/path/clearlogo.jpeg"))


def test_media_file_handler_ignores_non_media() -> None:
    """Test that handler ignores non-media files."""
    callback = Mock()
    handler = MediaFileHandler(callback)

    # Ignore .txt file
    event_txt = FileClosedEvent("/test/path/regular.txt")
    handler.on_any_event(event_txt)
    callback.assert_not_called()

    # Ignore banner.jpg (not poster/clearlogo pattern)
    event_banner = FileClosedEvent("/test/path/banner.jpg")
    handler.on_any_event(event_banner)
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


# Additional image-specific tests


def test_media_file_handler_detects_poster_closed() -> None:
    """Test handler detects poster.jpg closed events."""
    callback = Mock()
    handler = MediaFileHandler(callback)

    event = FileClosedEvent("/test/Series/Season 1/poster.jpg")
    handler.on_any_event(event)
    callback.assert_called_once_with(Path("/test/Series/Season 1/poster.jpg"))


def test_media_file_handler_detects_clearlogo_closed() -> None:
    """Test handler detects clearlogo.png closed events."""
    callback = Mock()
    handler = MediaFileHandler(callback)

    event = FileClosedEvent("/test/Series/clearlogo.png")
    handler.on_any_event(event)
    callback.assert_called_once_with(Path("/test/Series/clearlogo.png"))


def test_media_file_handler_ignores_banner() -> None:
    """Test handler ignores banner.jpg files."""
    callback = Mock()
    handler = MediaFileHandler(callback)

    event = FileClosedEvent("/test/Series/banner.jpg")
    handler.on_any_event(event)
    callback.assert_not_called()


def test_media_file_handler_ignores_created_events() -> None:
    """Test handler ignores created events (only handles closed/moved)."""
    callback = Mock()
    handler = MediaFileHandler(callback)

    event = FileCreatedEvent("/test/path/tvshow.nfo")
    handler.on_any_event(event)
    callback.assert_not_called()


def test_media_file_handler_ignores_modified_events() -> None:
    """Test handler ignores modified events (only handles closed/moved)."""
    callback = Mock()
    handler = MediaFileHandler(callback)

    event = FileModifiedEvent("/test/path/tvshow.nfo")
    handler.on_any_event(event)
    callback.assert_not_called()


def test_media_file_handler_handles_moved_events() -> None:
    """Test handler handles moved events using dest_path."""
    callback = Mock()
    handler = MediaFileHandler(callback)

    event = FileMovedEvent("/test/old/tvshow.nfo", "/test/new/tvshow.nfo")
    handler.on_any_event(event)
    callback.assert_called_once_with(Path("/test/new/tvshow.nfo"))


def test_media_file_handler_ignores_directories() -> None:
    """Test handler ignores directory events."""
    callback = Mock()
    handler = MediaFileHandler(callback)

    # Create a mock directory event
    mock_event = Mock()
    mock_event.is_directory = True
    mock_event.event_type = EVENT_TYPE_CLOSED
    mock_event.src_path = "/test/path/some_directory"

    handler.on_any_event(mock_event)
    callback.assert_not_called()


def test_media_file_handler_handles_callback_exceptions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test handler logs exceptions from callback."""

    def failing_callback(path: Path) -> None:
        raise ValueError("Test error")

    handler = MediaFileHandler(failing_callback)
    event = FileClosedEvent("/test/path/tvshow.nfo")

    handler.on_any_event(event)

    assert "Error in file monitor callback" in caplog.text
    assert "/test/path/tvshow.nfo" in caplog.text
