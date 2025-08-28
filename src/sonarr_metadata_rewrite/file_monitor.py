"""Real-time file system monitoring for .nfo files."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import (
    FileCreatedEvent,
    FileModifiedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

if TYPE_CHECKING:
    from watchdog.observers.api import BaseObserver

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.nfo_utils import is_nfo_file

logger = logging.getLogger(__name__)


class NFOFileHandler(FileSystemEventHandler):
    """File system event handler for .nfo files."""

    def __init__(self, callback: Callable[[Path], None]):
        self.callback = callback

    def _handle_nfo_event(self, event: FileSystemEvent) -> None:
        """Handle .nfo file events (creation or modification)."""
        if not event.is_directory:
            file_path = Path(str(event.src_path))
            if is_nfo_file(file_path):
                try:
                    self.callback(file_path)
                except Exception as e:
                    logger.error(
                        f"❌ Error in file monitor callback for {file_path}: {e}"
                    )

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        self._handle_nfo_event(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        self._handle_nfo_event(event)


class FileMonitor:
    """Real-time directory monitoring for .nfo file changes."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.observer: BaseObserver | None = None
        self.handler: NFOFileHandler | None = None

    def start(self, callback: Callable[[Path], None]) -> None:
        """Start monitoring directory for .nfo file changes.

        Args:
            callback: Function to call when .nfo file is created/modified
        """
        if self.observer is not None:
            self.stop()

        self.handler = NFOFileHandler(callback)
        self.observer = Observer()

        # Watch the root directory recursively, filtering for create/modify events only
        self.observer.schedule(
            self.handler,
            str(self.settings.rewrite_root_dir),
            recursive=True,
            event_filter=[FileCreatedEvent, FileModifiedEvent],
        )

        self.observer.start()

    def stop(self) -> None:
        """Stop monitoring and cleanup resources."""
        if self.observer is not None:
            self.observer.stop()
            self.observer.join()
            self.observer = None

        self.handler = None

    def is_running(self) -> bool:
        """Check if monitor is currently running."""
        return self.observer is not None and self.observer.is_alive()
