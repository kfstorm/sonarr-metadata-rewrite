"""Unit tests for rollback service."""

import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from sonarr_metadata_rewrite.rollback_service import RollbackService
from tests.conftest import create_test_settings


def test_rollback_service_init(test_data_dir: Path) -> None:
    """Test RollbackService initialization."""
    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
    )
    service = RollbackService(settings)
    assert service.settings == settings


def test_execute_rollback_no_backup_dir_configured(test_data_dir: Path) -> None:
    """Test rollback fails when backup directory is not configured."""
    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        original_files_backup_dir=None,
    )
    service = RollbackService(settings)

    with pytest.raises(ValueError, match="Backup directory is not configured"):
        service.execute_rollback()


def test_execute_rollback_backup_dir_not_exists(
    test_data_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test rollback handles non-existent backup directory gracefully."""
    backup_dir = test_data_dir / "nonexistent_backups"
    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    with caplog.at_level(logging.INFO):
        service.execute_rollback()  # Should not raise exception

    assert "Backup directory does not exist" in caplog.text
    assert "rollback completed with no files to restore" in caplog.text


def test_execute_rollback_no_backup_files(
    test_data_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test rollback handles empty backup directory gracefully."""
    backup_dir = test_data_dir / "empty_backups"
    backup_dir.mkdir(exist_ok=True)

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    with caplog.at_level(logging.INFO):
        service.execute_rollback()

    assert "No .nfo/.NFO backup files found" in caplog.text
    assert "rollback completed with no files to restore" in caplog.text


def test_execute_rollback_successful(
    test_data_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test successful rollback of backup files."""
    # Setup directory structure
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_dir.mkdir(exist_ok=True)

    # Create backup file
    backup_show_dir = backup_dir / "Show1"
    backup_show_dir.mkdir(exist_ok=True)
    backup_file = backup_show_dir / "tvshow.nfo"
    backup_file.write_text("Original content")

    # Create corresponding original directory
    original_show_dir = original_dir / "Show1"
    original_show_dir.mkdir(exist_ok=True)
    original_file = original_show_dir / "tvshow.nfo"
    original_file.write_text("Translated content")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dir=original_dir,
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    with caplog.at_level(logging.INFO):
        service.execute_rollback()

    # Verify file was restored
    assert original_file.read_text() == "Original content"
    assert "Found 1 backup files to restore" in caplog.text
    assert "Rollback completed: 1 files restored, 0 failed" in caplog.text
    assert "✅ Restored: Show1/tvshow.nfo" in caplog.text


def test_execute_rollback_missing_original_directory(
    test_data_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test rollback handles missing original directories gracefully."""
    # Setup backup directory
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_dir.mkdir(exist_ok=True)

    # Create backup file for show that no longer exists
    backup_show_dir = backup_dir / "DeletedShow"
    backup_show_dir.mkdir(exist_ok=True)
    backup_file = backup_show_dir / "tvshow.nfo"
    backup_file.write_text("Original content")

    # Note: We don't create the original show directory to simulate deleted show

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dir=original_dir,
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    with caplog.at_level(logging.INFO):
        service.execute_rollback()

    assert "Original directory no longer exists, skipping" in caplog.text
    assert "Rollback completed: 0 files restored, 1 failed" in caplog.text


def test_restore_single_file_success(test_data_dir: Path) -> None:
    """Test successful restoration of a single file."""
    # Setup directory structure
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_dir.mkdir(exist_ok=True)

    # Create backup file
    backup_show_dir = backup_dir / "Show1"
    backup_show_dir.mkdir(exist_ok=True)
    backup_file = backup_show_dir / "tvshow.nfo"
    backup_file.write_text("Original content")

    # Create corresponding original directory
    original_show_dir = original_dir / "Show1"
    original_show_dir.mkdir(exist_ok=True)
    original_file = original_show_dir / "tvshow.nfo"
    original_file.write_text("Translated content")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dir=original_dir,
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    result = service._restore_single_file(backup_file)

    assert result is True
    assert original_file.read_text() == "Original content"


def test_restore_single_file_missing_directory(test_data_dir: Path) -> None:
    """Test restoration fails gracefully when original directory is missing."""
    # Setup backup directory
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_dir.mkdir(exist_ok=True)

    # Create backup file for show that no longer exists
    backup_show_dir = backup_dir / "DeletedShow"
    backup_show_dir.mkdir(exist_ok=True)
    backup_file = backup_show_dir / "tvshow.nfo"
    backup_file.write_text("Original content")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dir=original_dir,
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    result = service._restore_single_file(backup_file)

    assert result is False


@patch("time.sleep")
def test_hang_after_completion_keyboard_interrupt(mock_sleep: Mock) -> None:
    """Test hang_after_completion handles KeyboardInterrupt gracefully."""
    test_data_dir = Path("/tmp")
    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
    )
    service = RollbackService(settings)

    # Simulate KeyboardInterrupt after first sleep
    mock_sleep.side_effect = KeyboardInterrupt()

    # Should not raise exception
    service.hang_after_completion()

    mock_sleep.assert_called_once_with(60)


@patch("time.sleep")
def test_hang_after_completion_runs_indefinitely(mock_sleep: Mock) -> None:
    """Test hang_after_completion runs indefinitely without interruption."""
    test_data_dir = Path("/tmp")
    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
    )
    service = RollbackService(settings)

    # Simulate multiple sleep calls before raising interrupt to stop
    mock_sleep.side_effect = [None, None, KeyboardInterrupt()]

    service.hang_after_completion()

    assert mock_sleep.call_count == 3
