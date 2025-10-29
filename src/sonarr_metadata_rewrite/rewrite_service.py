"""Main orchestrator service for metadata rewriting."""

import logging
from pathlib import Path

from diskcache import Cache  # type: ignore[import-untyped]

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.file_monitor import FileMonitor
from sonarr_metadata_rewrite.file_scanner import FileScanner
from sonarr_metadata_rewrite.image_processor import ImageProcessor
from sonarr_metadata_rewrite.metadata_processor import MetadataProcessor
from sonarr_metadata_rewrite.models import ProcessResult
from sonarr_metadata_rewrite.nfo_utils import is_nfo_file, is_rewritable_image
from sonarr_metadata_rewrite.translator import Translator

logger = logging.getLogger(__name__)


class RewriteService:
    """Main orchestrator coordinating all metadata rewriting components."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache = Cache(str(settings.cache_dir))
        self.translator = Translator(settings, self.cache)
        self.metadata_processor = MetadataProcessor(settings, self.translator)
        self.image_processor = ImageProcessor(settings, self.translator)
        self.file_monitor = FileMonitor(settings)
        self.file_scanner = FileScanner(settings)

    def start(self) -> None:
        """Start file monitoring and scanning services."""
        logger.info("Starting Sonarr Metadata Rewrite Service")
        logger.info(f"Monitoring directory: {self.settings.rewrite_root_dir}")
        logger.info(f"Preferred languages: {self.settings.preferred_languages}")

        # Start real-time file monitoring if enabled
        if self.settings.enable_file_monitor:
            self.file_monitor.start(self._process_file_callback)
            logger.info("File monitor started")
        else:
            logger.info("File monitor disabled")

        # Start periodic scanning if enabled
        if self.settings.enable_file_scanner:
            self.file_scanner.start(self._process_file_callback)
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

    def _process_file(self, file_path: Path) -> ProcessResult:
        """Process a single file (NFO or image)."""
        if is_nfo_file(file_path):
            return self.metadata_processor.process_file(file_path)
        else:
            # Gate image rewriting by configuration
            if not self.settings.enable_image_rewrite and is_rewritable_image(
                file_path
            ):
                return ProcessResult(
                    success=True,
                    file_path=file_path,
                    message="Image rewrite disabled; skipped",
                    file_modified=False,
                )

            return self.image_processor.process(file_path)

    def _process_file_callback(self, file_path: Path) -> None:
        """Callback wrapper for file monitor and scanner.

        Args:
            file_path: Path to file to process
        """
        try:
            logger.info(f"📄 Processing file: {file_path}")

            # Process the file through the appropriate processor
            result = self._process_file(file_path)

            # Log result based on success/failure
            if result.success:
                logger.info(f"✅ {result.message} - {file_path}")
            else:
                logger.warning(f"⚠️ {result.message} - {file_path}")

                # If there's an exception embedded in the result, log it with details
                if result.exception is not None:
                    logger.error(
                        f"❌ Processing error: {result.message}",
                        exc_info=result.exception,
                    )

        except Exception as e:
            logger.exception(f"❌ Failed to process {file_path}: {e}")
