"""Main orchestrator service for metadata rewriting."""

import logging
import sqlite3
from pathlib import Path

from diskcache import Cache  # type: ignore[import-untyped]

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.file_monitor import FileMonitor
from sonarr_metadata_rewrite.file_scanner import FileScanner
from sonarr_metadata_rewrite.metadata_processor import MetadataProcessor
from sonarr_metadata_rewrite.translator import Translator

logger = logging.getLogger(__name__)


class RewriteService:
    """Main orchestrator coordinating all metadata rewriting components."""

    def __init__(self, settings: Settings):
        self.settings = settings
        try:
            self.cache = Cache(str(settings.cache_dir))
        except sqlite3.OperationalError as e:
            raise RuntimeError(
                f"Failed to initialize cache at '{settings.cache_dir}'. "
                f"The directory may not be accessible or writable. "
                f"Error: {e}"
            ) from e
        self.translator = Translator(settings, self.cache)
        self.metadata_processor = MetadataProcessor(settings, self.translator)
        self.file_monitor = FileMonitor(settings)
        self.file_scanner = FileScanner(settings)

    def start(self) -> None:
        """Start the complete metadata rewriting service."""
        logger.info("Starting Sonarr Metadata Rewrite Service")
        logger.info(f"Monitoring directory: {self.settings.rewrite_root_dir}")
        logger.info(f"Preferred languages: {self.settings.preferred_languages}")

        # Start real-time file monitoring if enabled
        if self.settings.enable_file_monitor:
            self.file_monitor.start(self._process_file)
            logger.info("File monitor started")
        else:
            logger.info("File monitor disabled")

        # Start periodic scanning if enabled
        if self.settings.enable_file_scanner:
            self.file_scanner.start(self._process_file)
            interval = self.settings.periodic_scan_interval_seconds
            logger.info(f"Periodic scanner started (interval: {interval}s)")
        else:
            logger.info("Periodic scanner disabled")

    def stop(self) -> None:
        """Stop the service and cleanup all resources."""
        logger.info("Stopping Sonarr Metadata Rewrite Service")

        # Stop monitoring and scanning (only if they were started)
        if self.settings.enable_file_monitor:
            self.file_monitor.stop()
        if self.settings.enable_file_scanner:
            self.file_scanner.stop()

        # Close translator HTTP client and cache
        self.translator.close()
        self.cache.close()

        logger.info("Service stopped")

    def is_running(self) -> bool:
        """Check if service is currently running."""
        monitor_running = (
            self.settings.enable_file_monitor and self.file_monitor.is_running()
        )
        scanner_running = (
            self.settings.enable_file_scanner and self.file_scanner.is_running()
        )
        return monitor_running or scanner_running

    def _process_file(self, nfo_path: Path) -> None:
        """Process a single .nfo file (private callback method).

        Args:
            nfo_path: Path to .nfo file to process
        """
        try:
            logger.info(f"📄 Processing file: {nfo_path}")

            # Process the file through MetadataProcessor
            result = self.metadata_processor.process_file(nfo_path)

            if result.success:
                logger.info(f"✅ {result.message} - {nfo_path}")
            else:
                if result.exception:
                    # Actual error occurred - log as error with stack trace
                    logger.error(
                        f"❌ {result.message} - {nfo_path}", exc_info=result.exception
                    )
                else:
                    # Business logic failure (no translation available, etc.)
                    logger.warning(f"⚠️ {result.message} - {nfo_path}")

        except Exception:
            logger.exception(f"❌ Failed to process {nfo_path}")
