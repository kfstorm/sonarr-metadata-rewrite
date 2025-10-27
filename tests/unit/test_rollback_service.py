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

    assert "No backup files found" in caplog.text
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


# Image-specific rollback tests


def test_restore_image_with_extension_change(test_data_dir: Path) -> None:
    """Test rollback handles extension changes (backup.png, current.jpg)."""
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_dir.mkdir(exist_ok=True)

    # Create backup with .png extension
    backup_show_dir = backup_dir / "Show1"
    backup_show_dir.mkdir(exist_ok=True)
    backup_file = backup_show_dir / "poster.png"
    backup_file.write_bytes(b"PNG image data")

    # Create current directory with .jpg version
    original_show_dir = original_dir / "Show1"
    original_show_dir.mkdir(exist_ok=True)
    current_file = original_show_dir / "poster.jpg"
    current_file.write_bytes(b"JPEG image data")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dir=original_dir,
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    service.execute_rollback()

    # poster.jpg should be removed, poster.png should be restored
    assert not current_file.exists()
    restored_file = original_show_dir / "poster.png"
    assert restored_file.exists()
    assert restored_file.read_bytes() == b"PNG image data"


def test_restore_removes_all_extension_variants(test_data_dir: Path) -> None:
    """Test rollback removes all image extension variants."""
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_dir.mkdir(exist_ok=True)

    # Create backup with .png extension
    backup_show_dir = backup_dir / "Show1"
    backup_show_dir.mkdir(exist_ok=True)
    backup_file = backup_show_dir / "logo.png"
    backup_file.write_bytes(b"Original PNG logo")

    # Create current directory with multiple extension variants
    original_show_dir = original_dir / "Show1"
    original_show_dir.mkdir(exist_ok=True)
    jpg_file = original_show_dir / "logo.jpg"
    jpeg_file = original_show_dir / "logo.jpeg"
    jpg_file.write_bytes(b"JPEG logo 1")
    jpeg_file.write_bytes(b"JPEG logo 2")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dir=original_dir,
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    service.execute_rollback()

    # Both .jpg and .jpeg should be removed
    assert not jpg_file.exists()
    assert not jpeg_file.exists()
    # Original .png should be restored
    restored_file = original_show_dir / "logo.png"
    assert restored_file.exists()
    assert restored_file.read_bytes() == b"Original PNG logo"


def test_restore_both_nfo_and_images(test_data_dir: Path) -> None:
    """Test rollback restores both NFO files and image files."""
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_dir.mkdir(exist_ok=True)

    # Create backups for NFO and images
    backup_show_dir = backup_dir / "Show1"
    backup_show_dir.mkdir(exist_ok=True)
    backup_nfo = backup_show_dir / "tvshow.nfo"
    backup_nfo.write_text("Original NFO")
    backup_poster = backup_show_dir / "poster.jpg"
    backup_poster.write_bytes(b"Original poster")

    # Create current directory with modified files
    original_show_dir = original_dir / "Show1"
    original_show_dir.mkdir(exist_ok=True)
    current_nfo = original_show_dir / "tvshow.nfo"
    current_nfo.write_text("Translated NFO")
    current_poster = original_show_dir / "poster.png"  # Extension changed
    current_poster.write_bytes(b"Translated poster")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dir=original_dir,
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    service.execute_rollback()

    # NFO should be restored
    assert current_nfo.exists()
    assert current_nfo.read_text() == "Original NFO"

    # Image with wrong extension should be removed, correct one restored
    assert not current_poster.exists()
    restored_poster = original_show_dir / "poster.jpg"
    assert restored_poster.exists()
    assert restored_poster.read_bytes() == b"Original poster"


def test_restore_mixed_backup_directory(
    test_data_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test rollback handles mixed NFO and image files."""
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_dir.mkdir(exist_ok=True)

    # Create diverse backup structure
    show1_backup = backup_dir / "Show1"
    show1_backup.mkdir(exist_ok=True)
    (show1_backup / "tvshow.nfo").write_text("NFO 1")
    (show1_backup / "poster.jpg").write_bytes(b"Poster 1")
    (show1_backup / "logo.png").write_bytes(b"Logo 1")

    show2_backup = backup_dir / "Show2"
    show2_backup.mkdir(exist_ok=True)
    (show2_backup / "tvshow.nfo").write_text("NFO 2")

    # Create corresponding original directories
    show1_orig = original_dir / "Show1"
    show1_orig.mkdir(exist_ok=True)
    show2_orig = original_dir / "Show2"
    show2_orig.mkdir(exist_ok=True)

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dir=original_dir,
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    with caplog.at_level(logging.INFO):
        service.execute_rollback()

    # All files should be restored
    assert (show1_orig / "tvshow.nfo").exists()
    assert (show1_orig / "poster.jpg").exists()
    assert (show1_orig / "logo.png").exists()
    assert (show2_orig / "tvshow.nfo").exists()

    # Check log contains count
    assert "4 files restored" in caplog.text


def test_restore_case_insensitive_extensions(test_data_dir: Path) -> None:
    """Test rollback handles case-insensitive extension matching."""
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_dir.mkdir(exist_ok=True)

    # Create backup with lowercase extension
    backup_show_dir = backup_dir / "Show1"
    backup_show_dir.mkdir(exist_ok=True)
    backup_file = backup_show_dir / "poster.png"
    backup_file.write_bytes(b"Original PNG")

    # Create current file with uppercase extension
    original_show_dir = original_dir / "Show1"
    original_show_dir.mkdir(exist_ok=True)
    current_file = original_show_dir / "poster.JPG"  # Uppercase
    current_file.write_bytes(b"Modified JPEG")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dir=original_dir,
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    service.execute_rollback()

    # Uppercase variant should be removed
    assert not current_file.exists()
    # Original should be restored
    restored_file = original_show_dir / "poster.png"
    assert restored_file.exists()
    assert restored_file.read_bytes() == b"Original PNG"
