"""Periodic directory scanning for .nfo files."""

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.nfo_utils import find_nfo_files

logger = logging.getLogger(__name__)


class FileScanner:
    """Periodic scanner for .nfo files in directory tree."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.scan_thread: threading.Thread | None = None
        self.stop_event: threading.Event | None = None
        self.callback: Callable[[Path], None] | None = None

    def start(self, callback: Callable[[Path], None]) -> None:
        """Start periodic scanning for .nfo files.

        Args:
            callback: Function to call for each .nfo file found
        """
        if self.scan_thread is not None:
            self.stop()

        self.callback = callback
        self.stop_event = threading.Event()
        self.scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.scan_thread.start()

    def stop(self) -> None:
        """Stop scanning and cleanup resources."""
        if self.stop_event is not None:
            self.stop_event.set()

        if self.scan_thread is not None:
            self.scan_thread.join(timeout=5.0)
            self.scan_thread = None

        self.stop_event = None
        self.callback = None

    def is_running(self) -> bool:
        """Check if scanner is currently running."""
        return self.scan_thread is not None and self.scan_thread.is_alive()

    def _scan_loop(self) -> None:
        """Main scanning loop running in background thread."""
        while self.stop_event is not None and not self.stop_event.is_set():
            try:
                self._perform_scan()
            except Exception:
                logger.exception("Unexpected error during directory scan")

            # Wait for next scan interval or stop signal
            if self.stop_event is not None:
                self.stop_event.wait(
                    timeout=self.settings.periodic_scan_interval_seconds
                )

    def _perform_scan(self) -> None:
        """Perform one complete scan of the directory tree."""
        root_dir = self.settings.rewrite_root_dir
        if not root_dir.exists():
            logger.warning(f"Root directory does not exist: {root_dir}")
            return

        logger.debug(f"Starting scan of directory: {root_dir}")

        try:
            # Scan for .nfo/.NFO files recursively (case-insensitive)
            nfo_files = find_nfo_files(root_dir)
            for nfo_path in nfo_files:
                if self.stop_event is not None and self.stop_event.is_set():
                    break

                try:
                    if self.callback:
                        logger.debug(f"Processing file: {nfo_path}")
                        self.callback(nfo_path)
                except Exception:
                    logger.exception(f"Unexpected error processing file {nfo_path}")
                    continue

        except (OSError, PermissionError):
            logger.exception(f"File system error during scan of {root_dir}")
