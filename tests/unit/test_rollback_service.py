"""Unit tests for rollback service."""

import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from sonarr_metadata_rewrite.backup_utils import create_backup
from sonarr_metadata_rewrite.rollback_service import RollbackService
from tests.conftest import create_test_settings


def _make_backup(original_file: Path, backup_dir: Path) -> None:
    """Helper: create a backup using the correct absolute-path structure.

    Assumes original_file exists. Creates necessary backup directory structure
    automatically.
    """
    create_backup(original_file, backup_dir)


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
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_show_dir = original_dir / "Show1"
    original_show_dir.mkdir(parents=True, exist_ok=True)
    original_file = original_show_dir / "tvshow.nfo"
    original_file.write_text("Original content")

    # Create backup at the correct absolute-path structure
    _make_backup(original_file, backup_dir)

    # Simulate translation (overwrite original)
    original_file.write_text("Translated content")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dirs=[original_dir],
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    with caplog.at_level(logging.INFO):
        service.execute_rollback()

    # Verify file was restored
    assert original_file.read_text() == "Original content"
    assert "Found 1 backup files to restore" in caplog.text
    assert "Rollback completed: 1 files restored, 0 failed" in caplog.text
    assert "✅ Restored:" in caplog.text
    assert "tvshow.nfo" in caplog.text


def test_execute_rollback_missing_original_directory(
    test_data_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test rollback handles missing original directories gracefully."""
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    deleted_show_dir = original_dir / "DeletedShow"
    deleted_show_dir.mkdir(parents=True, exist_ok=True)
    original_file = deleted_show_dir / "tvshow.nfo"
    original_file.write_text("Original content")

    # Create backup before the directory is deleted
    _make_backup(original_file, backup_dir)

    # Simulate the show being deleted
    original_file.unlink()
    deleted_show_dir.rmdir()

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dirs=[original_dir],
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    with caplog.at_level(logging.INFO):
        service.execute_rollback()

    assert "Original directory no longer exists, skipping" in caplog.text
    assert "Rollback completed: 0 files restored, 1 failed" in caplog.text


def test_restore_single_file_success(test_data_dir: Path) -> None:
    """Test successful restoration of a single file."""
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_show_dir = original_dir / "Show1"
    original_show_dir.mkdir(parents=True, exist_ok=True)
    original_file = original_show_dir / "tvshow.nfo"
    original_file.write_text("Original content")

    _make_backup(original_file, backup_dir)

    # Simulate translation
    original_file.write_text("Translated content")

    # Derive the backup file path the same way create_backup would
    backup_file = backup_dir / original_file.relative_to("/")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dirs=[original_dir],
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    result = service._restore_single_file(backup_file)

    assert result is True
    assert original_file.read_text() == "Original content"


def test_restore_single_file_missing_directory(test_data_dir: Path) -> None:
    """Test restoration fails gracefully when original directory is missing."""
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    deleted_show_dir = original_dir / "DeletedShow"
    deleted_show_dir.mkdir(parents=True, exist_ok=True)
    original_file = deleted_show_dir / "tvshow.nfo"
    original_file.write_text("Original content")

    _make_backup(original_file, backup_dir)
    backup_file = backup_dir / original_file.relative_to("/")

    # Delete the show directory (simulate deletion)
    original_file.unlink()
    deleted_show_dir.rmdir()

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dirs=[original_dir],
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
    original_show_dir = original_dir / "Show1"
    original_show_dir.mkdir(parents=True, exist_ok=True)

    # Original poster was .png; create and back it up
    original_poster = original_show_dir / "poster.png"
    original_poster.write_bytes(b"PNG image data")
    _make_backup(original_poster, backup_dir)

    # Simulate rewrite: original is replaced with .jpg variant
    original_poster.unlink()
    current_file = original_show_dir / "poster.jpg"
    current_file.write_bytes(b"JPEG image data")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dirs=[original_dir],
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    service.execute_rollback()

    # .jpg should be removed, .png should be restored
    assert not current_file.exists()
    restored_file = original_show_dir / "poster.png"
    assert restored_file.exists()
    assert restored_file.read_bytes() == b"PNG image data"


def test_restore_removes_all_extension_variants(test_data_dir: Path) -> None:
    """Test rollback removes all image extension variants."""
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_show_dir = original_dir / "Show1"
    original_show_dir.mkdir(parents=True, exist_ok=True)

    # Original clearlogo was .png; create and back it up
    original_logo = original_show_dir / "clearlogo.png"
    original_logo.write_bytes(b"Original PNG logo")
    _make_backup(original_logo, backup_dir)
    original_logo.unlink()

    # Current directory contains multiple extension variants
    (original_show_dir / "clearlogo.jpg").write_bytes(b"JPEG logo 1")
    (original_show_dir / "clearlogo.jpeg").write_bytes(b"JPEG logo 2")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dirs=[original_dir],
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    service.execute_rollback()

    assert not (original_show_dir / "clearlogo.jpg").exists()
    assert not (original_show_dir / "clearlogo.jpeg").exists()
    restored_file = original_show_dir / "clearlogo.png"
    assert restored_file.exists()
    assert restored_file.read_bytes() == b"Original PNG logo"


def test_restore_both_nfo_and_images(test_data_dir: Path) -> None:
    """Test rollback restores both NFO files and image files."""
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_show_dir = original_dir / "Show1"
    original_show_dir.mkdir(parents=True, exist_ok=True)

    # Create originals and back them up
    original_nfo = original_show_dir / "tvshow.nfo"
    original_nfo.write_text("Original NFO")
    _make_backup(original_nfo, backup_dir)

    original_poster = original_show_dir / "poster.jpg"
    original_poster.write_bytes(b"Original poster")
    _make_backup(original_poster, backup_dir)

    # Simulate translation (overwrite with translated versions and extension change)
    original_nfo.write_text("Translated NFO")
    original_poster.unlink()
    (original_show_dir / "poster.png").write_bytes(b"Translated poster")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dirs=[original_dir],
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    service.execute_rollback()

    assert original_nfo.read_text() == "Original NFO"
    assert not (original_show_dir / "poster.png").exists()
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

    show1_orig = original_dir / "Show1"
    show1_orig.mkdir(parents=True, exist_ok=True)
    show2_orig = original_dir / "Show2"
    show2_orig.mkdir(parents=True, exist_ok=True)

    # Create originals and back them up
    files_to_backup = [
        (show1_orig / "tvshow.nfo", "NFO 1"),
        (show2_orig / "tvshow.nfo", "NFO 2"),
    ]
    binary_files = [
        (show1_orig / "poster.jpg", b"Poster 1"),
        (show1_orig / "clearlogo.png", b"Logo 1"),
    ]
    for file_path, content in files_to_backup:
        file_path.write_text(content)
        _make_backup(file_path, backup_dir)
        file_path.write_text("translated")

    for file_path, content in binary_files:
        file_path.write_bytes(content)
        _make_backup(file_path, backup_dir)
        file_path.write_bytes(b"translated")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dirs=[original_dir],
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    with caplog.at_level(logging.INFO):
        service.execute_rollback()

    assert (show1_orig / "tvshow.nfo").read_text() == "NFO 1"
    assert (show1_orig / "poster.jpg").read_bytes() == b"Poster 1"
    assert (show1_orig / "clearlogo.png").read_bytes() == b"Logo 1"
    assert (show2_orig / "tvshow.nfo").read_text() == "NFO 2"

    assert "4 files restored" in caplog.text


def test_restore_case_insensitive_extensions(test_data_dir: Path) -> None:
    """Test rollback handles case-insensitive extension matching."""
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media"
    original_show_dir = original_dir / "Show1"
    original_show_dir.mkdir(parents=True, exist_ok=True)

    # Original was .png; back it up
    original_poster = original_show_dir / "poster.png"
    original_poster.write_bytes(b"Original PNG")
    _make_backup(original_poster, backup_dir)
    original_poster.unlink()

    # Simulate extension change to uppercase .JPG
    current_file = original_show_dir / "poster.JPG"
    current_file.write_bytes(b"Modified JPEG")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dirs=[original_dir],
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    service.execute_rollback()

    assert not current_file.exists()
    restored_file = original_show_dir / "poster.png"
    assert restored_file.exists()
    assert restored_file.read_bytes() == b"Original PNG"


def test_restore_single_file_when_backup_parent_not_exists(
    test_data_dir: Path,
) -> None:
    """Test restore when original parent directory doesn't exist."""
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir()

    original_dir = test_data_dir / "media"
    deleted_show_dir = original_dir / "show"
    deleted_show_dir.mkdir(parents=True, exist_ok=True)
    original_file = deleted_show_dir / "poster.jpg"
    original_file.write_bytes(b"Original")
    _make_backup(original_file, backup_dir)

    backup_file = backup_dir / original_file.relative_to("/")

    # Remove the original directory
    original_file.unlink()
    deleted_show_dir.rmdir()

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    # Don't create the parent directory in rewrite_root_dir
    result = service._restore_single_file(backup_file)

    assert result is False


def test_execute_rollback_with_no_backup_files(test_data_dir: Path) -> None:
    """Test rollback when backup directory exists but is empty."""
    backup_dir = test_data_dir / "empty_backups"
    backup_dir.mkdir()

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    # Should not raise
    service.execute_rollback()


def test_execute_rollback_restores_multi_episode_nfo(test_data_dir: Path) -> None:
    """Test rollback restores Sonarr-style multi-episode NFO content."""
    backup_dir = test_data_dir / "backups"
    original_dir = test_data_dir / "media"
    backup_dir.mkdir(parents=True, exist_ok=True)
    original_dir.mkdir(parents=True, exist_ok=True)

    episode_dir = original_dir / "Breaking Bad" / "Season 01"
    episode_dir.mkdir(parents=True, exist_ok=True)
    original_file = episode_dir / "episodes.nfo"
    original_content = """<?xml version="1.0" encoding="utf-8"?>
<episodedetails>
  <title>Pilot</title>
  <plot>Walter White begins a new life in crime.</plot>
  <season>1</season>
  <episode>1</episode>
</episodedetails>
<episodedetails>
  <title>Cat's in the Bag...</title>
  <plot>Walt and Jesse deal with the aftermath.</plot>
  <season>1</season>
  <episode>2</episode>
</episodedetails>
"""
    original_file.write_text(original_content, encoding="utf-8")
    _make_backup(original_file, backup_dir)

    # Simulate translation
    original_file.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<episodedetails>
  <title>试播集</title>
  <plot>沃尔特开始了犯罪生涯。</plot>
  <season>1</season>
  <episode>1</episode>
</episodedetails>
<episodedetails>
  <title>猫在袋中</title>
  <plot>沃尔特和杰西处理后果。</plot>
  <season>1</season>
  <episode>2</episode>
</episodedetails>
""",
        encoding="utf-8",
    )

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dirs=[original_dir],
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    service.execute_rollback()

    restored_content = original_file.read_text(encoding="utf-8")
    assert "Pilot" in restored_content
    assert "Cat's in the Bag..." in restored_content
    assert "试播集" not in restored_content


# ---------------------------------------------------------------------------
# Backward-compatibility (legacy backup format) rollback tests
# ---------------------------------------------------------------------------


def test_rollback_restores_legacy_format_backup(test_data_dir: Path) -> None:
    """Rollback correctly restores a file whose backup is in the legacy format.

    The legacy format stores the backup relative to the root dir, e.g.:
        <BACKUP_DIR>/Show A/tvshow.nfo   (root: <MEDIA>/tv)
    rather than the new absolute-path format:
        <BACKUP_DIR>/tv/Show A/tvshow.nfo
    """
    backup_dir = test_data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    original_dir = test_data_dir / "media" / "tv"
    show_dir = original_dir / "Show A"
    show_dir.mkdir(parents=True, exist_ok=True)
    original_file = show_dir / "tvshow.nfo"
    original_file.write_text("Translated content")

    # Place backup in the OLD (legacy) format: relative to root_dir
    legacy_backup = backup_dir / "Show A" / "tvshow.nfo"
    legacy_backup.parent.mkdir(parents=True, exist_ok=True)
    legacy_backup.write_text("Original content")

    settings = create_test_settings(
        test_data_dir,
        service_mode="rollback",
        rewrite_root_dirs=[original_dir],
        original_files_backup_dir=backup_dir,
    )
    service = RollbackService(settings)

    service.execute_rollback()

    assert original_file.read_text() == "Original content"
