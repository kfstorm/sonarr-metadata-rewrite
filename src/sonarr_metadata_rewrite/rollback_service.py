"""Rollback service for restoring original files from backups."""

import logging
import shutil
import time
from pathlib import Path

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.nfo_utils import find_target_files

logger = logging.getLogger(__name__)


class RollbackService:
    """Service for rolling back all translated files to their original versions."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def execute_rollback(self) -> None:
        """Execute the rollback operation to restore all original files.

        Raises:
            ValueError: If backup directory is not configured or doesn't exist
        """
        if not self.settings.original_files_backup_dir:
            raise ValueError("Backup directory is not configured")

        if not self.settings.original_files_backup_dir.exists():
            logger.warning(
                f"Backup directory does not exist: "
                f"{self.settings.original_files_backup_dir}"
            )
            logger.info(
                "No backups found - rollback completed with no files to restore"
            )
            return

        logger.info(
            f"Starting rollback from backup directory: "
            f"{self.settings.original_files_backup_dir}"
        )

        # Find all .nfo and image files in backup directory
        backup_files = find_target_files(self.settings.original_files_backup_dir)

        if not backup_files:
            logger.info(
                "No backup files found - rollback completed with no files to restore"
            )
            return

        logger.info(f"Found {len(backup_files)} backup files to restore")

        restored_count = 0
        failed_count = 0

        for backup_file in backup_files:
            try:
                success = self._restore_single_file(backup_file)
                if success:
                    restored_count += 1
                else:
                    failed_count += 1
            except Exception:
                logger.exception(f"Failed to restore {backup_file}")
                failed_count += 1

        logger.info(
            f"Rollback completed: {restored_count} files restored, "
            f"{failed_count} failed"
        )

    def _restore_single_file(self, backup_file: Path) -> bool:
        """Restore a single file from backup to its original location.

        For image files, this handles cases where the extension may have changed
        (e.g., backup is poster.png but current file is poster.jpg).

        Args:
            backup_file: Path to the backup file

        Returns:
            True if file was restored successfully, False otherwise
        """
        try:
            # Calculate original file path
            # At this point, backup_dir is guaranteed to be not None due to check above
            backup_dir = self.settings.original_files_backup_dir
            assert backup_dir is not None
            relative_path = backup_file.relative_to(backup_dir)
            original_file = self.settings.rewrite_root_dir / relative_path

            # Check if original location still exists (parent directory)
            if not original_file.parent.exists():
                logger.warning(
                    f"Original directory no longer exists, skipping: "
                    f"{original_file.parent}"
                )
                return False

            # For image files, remove any file with same stem but different extension
            # This handles cases where extension changed during rewrite
            # (e.g., poster.png was replaced with poster.jpg)
            if backup_file.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                stem = original_file.stem
                parent = original_file.parent
                for ext in [".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"]:
                    candidate = parent / f"{stem}{ext}"
                    if candidate.exists() and candidate != original_file:
                        candidate.unlink()
                        logger.debug(
                            f"Removed file with different extension: {candidate.name}"
                        )

            # Copy backup file to original location
            shutil.copy2(backup_file, original_file)
            logger.info(f"✅ Restored: {relative_path}")
            return True

        except Exception:
            logger.exception(f"❌ Failed to restore {backup_file.name}")
            return False

    def hang_after_completion(self) -> None:
        """Keep the service running indefinitely after rollback completion.

        This prevents container restarts that would re-execute the rollback.
        """
        logger.info("Rollback completed. Service will now hang to prevent restart.")
        logger.info("To stop the service, use SIGTERM or SIGINT (Ctrl+C)")

        try:
            while True:
                time.sleep(60)  # Sleep for 1 minute at a time
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down gracefully")
