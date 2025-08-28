"""Rollback service for restoring original files from backups."""

import logging
import shutil
from pathlib import Path

from sonarr_metadata_rewrite.config import Settings

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
            logger.warning(f"Backup directory does not exist: {self.settings.original_files_backup_dir}")
            logger.info("No backups found - rollback completed with no files to restore")
            return

        logger.info(f"Starting rollback from backup directory: {self.settings.original_files_backup_dir}")
        
        # Find all .nfo files in backup directory
        backup_files = list(self.settings.original_files_backup_dir.rglob("*.nfo"))
        
        if not backup_files:
            logger.info("No .nfo backup files found - rollback completed with no files to restore")
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
            except Exception as e:
                logger.error(f"Failed to restore {backup_file}: {e}")
                failed_count += 1
        
        logger.info(f"Rollback completed: {restored_count} files restored, {failed_count} failed")

    def _restore_single_file(self, backup_file: Path) -> bool:
        """Restore a single file from backup to its original location.
        
        Args:
            backup_file: Path to the backup file
            
        Returns:
            True if file was restored successfully, False otherwise
        """
        try:
            # Calculate original file path
            relative_path = backup_file.relative_to(self.settings.original_files_backup_dir)
            original_file = self.settings.rewrite_root_dir / relative_path
            
            # Check if original location still exists (parent directory)
            if not original_file.parent.exists():
                logger.warning(f"Original directory no longer exists, skipping: {original_file.parent}")
                return False
            
            # Copy backup file to original location
            shutil.copy2(backup_file, original_file)
            logger.info(f"✅ Restored: {relative_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to restore {backup_file.name}: {e}")
            return False

    def hang_after_completion(self) -> None:
        """Keep the service running indefinitely after rollback completion.
        
        This prevents container restarts that would re-execute the rollback.
        """
        logger.info("Rollback completed. Service will now hang to prevent restart.")
        logger.info("To stop the service, use SIGTERM or SIGINT (Ctrl+C)")
        
        try:
            while True:
                import time
                time.sleep(60)  # Sleep for 1 minute at a time
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down gracefully")