"""Tests for backup utility functions."""

import tempfile
from pathlib import Path

from sonarr_metadata_rewrite.backup_utils import (
    create_backup,
    get_backup_path,
    restore_from_backup,
)


class TestBackupFunctions:
    """Test create_backup, get_backup_path, and restore_from_backup functions."""

    def test_backup_with_none_backup_dir(self) -> None:
        """Test backup functions with None backup_dir."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            file_path = temp_path / "test.nfo"
            file_path.write_text("<tvshow></tvshow>")

            # create_backup returns False
            result = create_backup(file_path, None, temp_path)
            assert result is False

            # get_backup_path returns None
            backup_path = get_backup_path(file_path, None, temp_path)
            assert backup_path is None

    def test_backup_nonexistent_file(self) -> None:
        """Test that create_backup returns False for nonexistent file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"
            file_path = temp_path / "nonexistent.nfo"

            result = create_backup(file_path, backup_dir, temp_path)
            assert result is False

    def test_backup_and_retrieval_workflow(self) -> None:
        """Test complete workflow: create backup and retrieve it."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"
            file_path = temp_path / "test.nfo"
            content = "<tvshow></tvshow>"
            file_path.write_text(content)

            # Before backup, get_backup_path returns None
            backup_path = get_backup_path(file_path, backup_dir, temp_path)
            assert backup_path is None

            # Create backup
            created = create_backup(file_path, backup_dir, temp_path)
            assert created is True

            # After backup, get_backup_path returns the backup path
            backup_path = get_backup_path(file_path, backup_dir, temp_path)
            assert backup_path is not None
            assert backup_path.exists()
            assert backup_path.read_text() == content

    def test_backup_preserves_directory_structure(self) -> None:
        """Test backup maintains directory structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"
            subdir = temp_path / "shows" / "series1"
            subdir.mkdir(parents=True)
            file_path = subdir / "tvshow.nfo"
            content = "<tvshow></tvshow>"
            file_path.write_text(content)

            # Create backup
            result = create_backup(file_path, backup_dir, temp_path)
            assert result is True

            # Verify structure is preserved
            expected_backup = backup_dir / "shows" / "series1" / "tvshow.nfo"
            assert expected_backup.exists()
            assert expected_backup.read_text() == content

            # get_backup_path should find it
            backup_path = get_backup_path(file_path, backup_dir, temp_path)
            assert backup_path == expected_backup

    def test_backup_does_not_overwrite_existing(self) -> None:
        """Test that backup doesn't overwrite existing backup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"
            file_path = temp_path / "test.nfo"
            file_path.write_text("<tvshow>new</tvshow>")

            # Create existing backup with different content
            backup_path = backup_dir / "test.nfo"
            backup_path.parent.mkdir(parents=True)
            original_content = "<tvshow>original</tvshow>"
            backup_path.write_text(original_content)

            # Try to backup new content
            result = create_backup(file_path, backup_dir, temp_path)
            assert result is True

            # Verify backup wasn't overwritten
            assert backup_path.read_text() == original_content

            # get_backup_path should return existing backup
            retrieved_path = get_backup_path(file_path, backup_dir, temp_path)
            assert retrieved_path == backup_path
            assert retrieved_path is not None
            assert retrieved_path.read_text() == original_content

    def test_backup_stem_matching_for_different_extensions(self) -> None:
        """Test both functions handle same stem with different extensions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"

            # Create original poster.png in backup
            backup_path_png = backup_dir / "poster.png"
            backup_path_png.parent.mkdir(parents=True)
            backup_path_png.write_bytes(b"PNG original")

            # Try to backup poster.jpg (same stem, different extension)
            file_path_jpg = temp_path / "poster.jpg"
            file_path_jpg.write_bytes(b"JPG new")

            # create_backup should recognize existing stem and not create new
            result = create_backup(file_path_jpg, backup_dir, temp_path)
            assert result is True

            # Verify original backup still exists and wasn't modified
            assert backup_path_png.exists()
            assert backup_path_png.read_bytes() == b"PNG original"

            # Verify new backup wasn't created
            backup_path_jpg = backup_dir / "poster.jpg"
            assert not backup_path_jpg.exists()

            # get_backup_path should find the .png backup when looking for .jpg
            retrieved_path = get_backup_path(file_path_jpg, backup_dir, temp_path)
            assert retrieved_path == backup_path_png
            assert retrieved_path is not None
            assert retrieved_path.read_bytes() == b"PNG original"

    def test_restore_same_extension(self) -> None:
        """Test restoring file with same extension."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"

            # Create backup
            backup_path = backup_dir / "test.nfo"
            backup_path.parent.mkdir(parents=True)
            backup_path.write_text("backup content")

            # Create current file
            file_path = temp_path / "test.nfo"
            file_path.write_text("modified content")

            # Restore from backup
            result = restore_from_backup(file_path, backup_dir, temp_path)
            assert result is True
            assert file_path.read_text() == "backup content"

    def test_restore_different_extension(self) -> None:
        """Test restoring when backup has different extension (stem matching)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"

            # Create backup as .png
            backup_path = backup_dir / "poster.png"
            backup_path.parent.mkdir(parents=True)
            backup_path.write_bytes(b"PNG backup")

            # Create current file as .jpg
            file_path = temp_path / "poster.jpg"
            file_path.write_bytes(b"JPG modified")

            # Restore from backup
            result = restore_from_backup(file_path, backup_dir, temp_path)
            assert result is True

            # Current file (poster.jpg) should now have backup content
            assert file_path.exists()
            assert file_path.read_bytes() == b"PNG backup"

            # No other files with same stem should exist
            # (In this case, there's only the .jpg file we restored to)
            poster_files = list(temp_path.glob("poster.*"))
            assert len(poster_files) == 1
            assert poster_files[0] == file_path

    def test_restore_deletes_files_with_same_stem(self) -> None:
        """Test restore deletes all files with same stem but diff extensions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"

            # Create backup
            backup_path = backup_dir / "poster.png"
            backup_path.parent.mkdir(parents=True)
            backup_path.write_bytes(b"PNG backup")

            # Create multiple files with same stem
            jpg_file = temp_path / "poster.jpg"
            jpeg_file = temp_path / "poster.jpeg"
            webp_file = temp_path / "poster.webp"
            jpg_file.write_bytes(b"JPG")
            jpeg_file.write_bytes(b"JPEG")
            webp_file.write_bytes(b"WEBP")

            # Restore from backup (requesting poster.png path)
            file_path = temp_path / "poster.png"
            result = restore_from_backup(file_path, backup_dir, temp_path)
            assert result is True

            # Only poster.png should exist with backup content
            assert file_path.exists()
            assert file_path.read_bytes() == b"PNG backup"

            # All other extensions should be deleted
            assert not jpg_file.exists()
            assert not jpeg_file.exists()
            assert not webp_file.exists()

    def test_restore_with_no_backup(self) -> None:
        """Test restore when no backup exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"
            backup_dir.mkdir()

            # Create current file but no backup
            file_path = temp_path / "test.nfo"
            file_path.write_text("no backup")

            # Restore should fail
            result = restore_from_backup(file_path, backup_dir, temp_path)
            assert result is False

            # File should be unchanged
            assert file_path.read_text() == "no backup"

    def test_restore_with_none_backup_dir(self) -> None:
        """Test restore with None backup_dir."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create current file
            file_path = temp_path / "test.nfo"
            file_path.write_text("content")

            # Restore should fail
            result = restore_from_backup(file_path, None, temp_path)
            assert result is False

            # File should be unchanged
            assert file_path.read_text() == "content"

    def test_restore_creates_target_in_backup_extension(self) -> None:
        """Test that restore creates file with backup extension, not requested."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"

            # Create backup as .png
            backup_path = backup_dir / "poster.png"
            backup_path.parent.mkdir(parents=True)
            backup_path.write_bytes(b"PNG backup")

            # Request restore to .jpg (which doesn't exist yet)
            file_path = temp_path / "poster.jpg"

            # Restore from backup
            result = restore_from_backup(file_path, backup_dir, temp_path)
            assert result is True

            # The .jpg file should now exist with backup content
            assert file_path.exists()
            assert file_path.read_bytes() == b"PNG backup"
