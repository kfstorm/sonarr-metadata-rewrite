"""Tests for backup utility functions."""

import tempfile
from pathlib import Path

from sonarr_metadata_rewrite.backup_utils import (
    create_backup,
    get_backup_path,
    restore_from_backup,
)


def test_backup_with_none_backup_dir() -> None:
    """Test backup functions with None backup_dir."""
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "test.nfo"
        file_path.write_text("<tvshow></tvshow>")

        assert create_backup(file_path, None) is False
        assert get_backup_path(file_path, None) is None


def test_backup_nonexistent_file() -> None:
    """Test that create_backup returns False for nonexistent file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "backup"
        file_path = temp_path / "nonexistent.nfo"

        assert create_backup(file_path, backup_dir) is False


def test_backup_and_retrieval_workflow() -> None:
    """Test complete workflow: create backup and retrieve it."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "backup"
        file_path = temp_path / "test.nfo"
        content = "<tvshow></tvshow>"
        file_path.write_text(content)

        # Before backup, get_backup_path returns None
        assert get_backup_path(file_path, backup_dir) is None

        # Create backup
        assert create_backup(file_path, backup_dir) is True

        # After backup, get_backup_path returns the backup path
        backup_path = get_backup_path(file_path, backup_dir)
        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.read_text() == content


def test_backup_uses_full_absolute_path_structure() -> None:
    """Test backup mirrors the full absolute file path under backup_dir.

    e.g. /media/sonarr/Show/tvshow.nfo is backed up as:
         <backup_dir>/media/sonarr/Show/tvshow.nfo
    This prevents collisions when files from different root dirs share the
    same relative path.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "backup"
        subdir = temp_path / "shows" / "series1"
        subdir.mkdir(parents=True)
        file_path = subdir / "tvshow.nfo"
        content = "<tvshow></tvshow>"
        file_path.write_text(content)

        assert create_backup(file_path, backup_dir) is True

        # Verify the backup mirrors the full absolute path structure
        expected_backup = backup_dir / file_path.relative_to("/")
        assert expected_backup.exists()
        assert expected_backup.read_text() == content

        assert get_backup_path(file_path, backup_dir) == expected_backup


def test_backup_no_collision_across_root_dirs() -> None:
    """Files from different root dirs with identical relative paths don't collide."""
    with tempfile.TemporaryDirectory() as base_dir:
        base = Path(base_dir)
        backup_dir = base / "backup"

        # Two root dirs each containing "Show A/tvshow.nfo"
        dir1 = base / "sonarr" / "Show A"
        dir2 = base / "anime" / "Show A"
        dir1.mkdir(parents=True)
        dir2.mkdir(parents=True)

        file1 = dir1 / "tvshow.nfo"
        file2 = dir2 / "tvshow.nfo"
        file1.write_text("content from sonarr")
        file2.write_text("content from anime")

        assert create_backup(file1, backup_dir) is True
        assert create_backup(file2, backup_dir) is True

        # Both backups exist at different locations
        backup1 = get_backup_path(file1, backup_dir)
        backup2 = get_backup_path(file2, backup_dir)
        assert backup1 is not None
        assert backup2 is not None
        assert backup1 != backup2
        assert backup1.read_text() == "content from sonarr"
        assert backup2.read_text() == "content from anime"


def test_backup_does_not_overwrite_existing() -> None:
    """Test that backup doesn't overwrite existing backup."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "backup"
        file_path = temp_path / "test.nfo"
        file_path.write_text("<tvshow>new</tvshow>")

        # Create existing backup with different content
        expected_backup = backup_dir / file_path.relative_to("/")
        expected_backup.parent.mkdir(parents=True, exist_ok=True)
        original_content = "<tvshow>original</tvshow>"
        expected_backup.write_text(original_content)

        # Try to backup new content - should not overwrite
        assert create_backup(file_path, backup_dir) is True
        assert expected_backup.read_text() == original_content

        retrieved = get_backup_path(file_path, backup_dir)
        assert retrieved == expected_backup
        assert retrieved is not None
        assert retrieved.read_text() == original_content


def test_backup_stem_matching_for_different_extensions() -> None:
    """Test both functions handle same stem with different extensions."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "backup"

        # Create original poster.png in backup using the full-path structure
        file_path_jpg = temp_path / "poster.jpg"
        file_path_jpg.write_bytes(b"JPG new")
        expected_dir = (backup_dir / file_path_jpg.relative_to("/")).parent
        expected_dir.mkdir(parents=True, exist_ok=True)
        backup_path_png = expected_dir / "poster.png"
        backup_path_png.write_bytes(b"PNG original")

        # create_backup should recognize existing stem and not create new backup
        assert create_backup(file_path_jpg, backup_dir) is True
        assert backup_path_png.exists()
        assert backup_path_png.read_bytes() == b"PNG original"
        assert not (expected_dir / "poster.jpg").exists()

        # get_backup_path should find the .png backup when looking for .jpg
        retrieved = get_backup_path(file_path_jpg, backup_dir)
        assert retrieved == backup_path_png
        assert retrieved is not None
        assert retrieved.read_bytes() == b"PNG original"


def test_restore_same_extension() -> None:
    """Test restoring file with same extension."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "backup"

        file_path = temp_path / "test.nfo"
        file_path.write_text("modified content")

        # Create backup using the full absolute path structure
        backup_path = backup_dir / file_path.relative_to("/")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text("backup content")

        result = restore_from_backup(file_path, backup_dir)
        assert result is True
        assert file_path.read_text() == "backup content"


def test_restore_different_extension() -> None:
    """Test restoring when backup has different extension (stem matching)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "backup"

        file_path_jpg = temp_path / "poster.jpg"
        file_path_jpg.write_bytes(b"JPG modified")

        # Backup stored as .png (same stem, different extension)
        backup_dir_for_file = (backup_dir / file_path_jpg.relative_to("/")).parent
        backup_dir_for_file.mkdir(parents=True, exist_ok=True)
        (backup_dir_for_file / "poster.png").write_bytes(b"PNG backup")

        result = restore_from_backup(file_path_jpg, backup_dir)
        assert result is True
        assert file_path_jpg.exists()
        assert file_path_jpg.read_bytes() == b"PNG backup"

        # Only one poster file should remain
        poster_files = list(temp_path.glob("poster.*"))
        assert len(poster_files) == 1
        assert poster_files[0] == file_path_jpg


def test_restore_deletes_files_with_same_stem() -> None:
    """Test restore deletes all files with same stem but diff extensions."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "backup"

        # Backup stored as .png
        file_path_png = temp_path / "poster.png"
        backup_entry_dir = (backup_dir / file_path_png.relative_to("/")).parent
        backup_entry_dir.mkdir(parents=True, exist_ok=True)
        (backup_entry_dir / "poster.png").write_bytes(b"PNG backup")

        # Multiple files with same stem exist
        jpg_file = temp_path / "poster.jpg"
        jpeg_file = temp_path / "poster.jpeg"
        webp_file = temp_path / "poster.webp"
        jpg_file.write_bytes(b"JPG")
        jpeg_file.write_bytes(b"JPEG")
        webp_file.write_bytes(b"WEBP")

        result = restore_from_backup(file_path_png, backup_dir)
        assert result is True
        assert file_path_png.exists()
        assert file_path_png.read_bytes() == b"PNG backup"
        assert not jpg_file.exists()
        assert not jpeg_file.exists()
        assert not webp_file.exists()


def test_restore_with_no_backup() -> None:
    """Test restore when no backup exists."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "backup"
        backup_dir.mkdir()

        file_path = temp_path / "test.nfo"
        file_path.write_text("no backup")

        assert restore_from_backup(file_path, backup_dir) is False
        assert file_path.read_text() == "no backup"


def test_restore_with_none_backup_dir() -> None:
    """Test restore with None backup_dir."""
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "test.nfo"
        file_path.write_text("content")

        assert restore_from_backup(file_path, None) is False
        assert file_path.read_text() == "content"


def test_restore_creates_target_in_backup_extension() -> None:
    """Test that restore creates file with backup extension, not requested."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "backup"

        # Backup exists as .png
        file_path_jpg = temp_path / "poster.jpg"
        backup_entry_dir = (backup_dir / file_path_jpg.relative_to("/")).parent
        backup_entry_dir.mkdir(parents=True, exist_ok=True)
        (backup_entry_dir / "poster.png").write_bytes(b"PNG backup")

        # Restore requesting the .jpg path (which does not exist yet)
        result = restore_from_backup(file_path_jpg, backup_dir)
        assert result is True
        assert file_path_jpg.exists()
        assert file_path_jpg.read_bytes() == b"PNG backup"


# ---------------------------------------------------------------------------
# Backward-compatibility (legacy format) tests
# ---------------------------------------------------------------------------


def test_get_backup_path_finds_legacy_format() -> None:
    """get_backup_path falls back to legacy path when root_dirs supplied."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        root_dir = temp_path / "tv"
        backup_dir = temp_path / "backup"

        # Original file
        show_dir = root_dir / "Show A"
        show_dir.mkdir(parents=True)
        file_path = show_dir / "tvshow.nfo"
        file_path.write_text("original")

        # Legacy backup: relative to root_dir
        legacy_backup = backup_dir / "Show A" / "tvshow.nfo"
        legacy_backup.parent.mkdir(parents=True)
        legacy_backup.write_text("original")

        # New-format path does NOT exist, but legacy does
        new_backup = backup_dir / file_path.relative_to("/")
        assert not new_backup.exists()

        result = get_backup_path(file_path, backup_dir, [root_dir])
        assert result == legacy_backup


def test_create_backup_skips_when_legacy_backup_exists() -> None:
    """create_backup does not overwrite a legacy-format backup."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        root_dir = temp_path / "tv"
        backup_dir = temp_path / "backup"

        show_dir = root_dir / "Show A"
        show_dir.mkdir(parents=True)
        file_path = show_dir / "tvshow.nfo"
        file_path.write_text("translated content")

        # Create legacy backup
        legacy_backup = backup_dir / "Show A" / "tvshow.nfo"
        legacy_backup.parent.mkdir(parents=True)
        legacy_backup.write_text("original content")

        result = create_backup(file_path, backup_dir, [root_dir])
        assert result is True

        # Legacy backup untouched
        assert legacy_backup.read_text() == "original content"
        # New-format backup NOT created (legacy already covers it)
        new_backup = backup_dir / file_path.relative_to("/")
        assert not new_backup.exists()


def test_restore_from_backup_uses_legacy_format() -> None:
    """restore_from_backup restores content from a legacy-format backup."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        root_dir = temp_path / "tv"
        backup_dir = temp_path / "backup"

        show_dir = root_dir / "Show A"
        show_dir.mkdir(parents=True)
        file_path = show_dir / "tvshow.nfo"
        file_path.write_text("translated content")

        # Legacy backup only
        legacy_backup = backup_dir / "Show A" / "tvshow.nfo"
        legacy_backup.parent.mkdir(parents=True)
        legacy_backup.write_text("original content")

        result = restore_from_backup(file_path, backup_dir, [root_dir])
        assert result is True
        assert file_path.read_text() == "original content"


def test_legacy_fallback_stem_matching() -> None:
    """Legacy fallback also applies stem-matching for image extension changes."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        root_dir = temp_path / "tv"
        backup_dir = temp_path / "backup"

        show_dir = root_dir / "Show A"
        show_dir.mkdir(parents=True)
        # Current file is .jpg
        file_path_jpg = show_dir / "poster.jpg"
        file_path_jpg.write_bytes(b"JPEG translated")

        # Legacy backup is .png (stem matches)
        legacy_backup_png = backup_dir / "Show A" / "poster.png"
        legacy_backup_png.parent.mkdir(parents=True)
        legacy_backup_png.write_bytes(b"PNG original")

        result = get_backup_path(file_path_jpg, backup_dir, [root_dir])
        assert result == legacy_backup_png


def test_legacy_fallback_not_used_without_root_dirs() -> None:
    """Legacy format is NOT consulted when root_dirs is not provided."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        root_dir = temp_path / "tv"
        backup_dir = temp_path / "backup"

        show_dir = root_dir / "Show A"
        show_dir.mkdir(parents=True)
        file_path = show_dir / "tvshow.nfo"
        file_path.write_text("content")

        # Only a legacy backup exists
        legacy_backup = backup_dir / "Show A" / "tvshow.nfo"
        legacy_backup.parent.mkdir(parents=True)
        legacy_backup.write_text("legacy backup")

        # No root_dirs → only new-format path is checked → not found
        assert get_backup_path(file_path, backup_dir) is None
        assert get_backup_path(file_path, backup_dir, []) is None
