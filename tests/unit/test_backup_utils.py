"""Tests for backup utility functions."""

import errno
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from sonarr_metadata_rewrite.backup_utils import (
    create_backup,
    get_backup_path,
    restore_from_backup,
)


@pytest.mark.parametrize("content", [b"<tvshow>original</tvshow>", bytes(range(256))])
def test_backup_needs_only_content_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: bytes
) -> None:
    """Unreadable source xattrs must not prevent a complete content backup."""
    source = tmp_path / "poster.png"
    source.write_bytes(content)
    source.chmod(0o751)
    os.setxattr(source, "user.example", b"source metadata")
    os.utime(source, (1, 1))

    def fail_listxattr(*args: object, **kwargs: object) -> list[str]:
        raise OSError(errno.EIO, "xattrs unavailable")

    monkeypatch.setattr(os, "listxattr", fail_listxattr)
    backup_dir = tmp_path / "backups"
    assert create_backup(source, backup_dir)
    backup = get_backup_path(source, backup_dir)
    assert backup is not None
    assert backup.read_bytes() == content
    assert backup.stat().st_mode & 0o777 != 0o751
    assert backup.stat().st_mtime > 1
    with pytest.raises(OSError) as missing_attribute:
        os.getxattr(backup, "user.example")
    assert missing_attribute.value.errno == errno.ENODATA


@pytest.mark.parametrize("failure", ["copy", "publish", "vanished_winner"])
def test_failed_backup_is_never_discoverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """Partial writes and failed publication leave no valid backup or temp file."""
    source = tmp_path / "metadata.nfo"
    source.write_bytes(b"complete original")
    backups = tmp_path / "backups"

    def fail_copy(src: Path, dst: Path) -> None:
        dst.write_bytes(b"partial")
        raise OSError(errno.EIO, "copy failed")

    def fail_publish(src: Path, dst: Path) -> None:
        if failure == "vanished_winner":
            raise FileExistsError(errno.EEXIST, "racing backup has disappeared")
        raise OSError(errno.EPERM, "publication failed")

    if failure == "copy":
        monkeypatch.setattr(shutil, "copyfile", fail_copy)
    else:
        monkeypatch.setattr(os, "link", fail_publish)
    with pytest.raises(OSError):
        create_backup(source, backups)
    assert source.read_bytes() == b"complete original"
    assert get_backup_path(source, backups) is None
    assert not list(backups.rglob(".backup_*"))


def test_concurrent_backup_creation_publishes_only_one_complete_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two creators cannot overwrite the winner or expose partial bytes."""
    source = tmp_path / "poster.png"
    source.write_bytes(bytes(range(256)) * 1024)
    backups = tmp_path / "backups"
    barrier = Barrier(2)
    copyfile = shutil.copyfile

    def concurrent_copy(src: Path, dst: Path) -> None:
        copyfile(src, dst)
        barrier.wait(timeout=10)

    monkeypatch.setattr(shutil, "copyfile", concurrent_copy)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create_backup(source, backups), range(2)))
    assert results == [True, True]
    backup = get_backup_path(source, backups)
    assert backup is not None
    assert backup.read_bytes() == source.read_bytes()
    assert list(backup.parent.iterdir()) == [backup]


def test_racing_backup_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An already published winner survives even when it has different bytes."""
    source = tmp_path / "metadata.nfo"
    source.write_bytes(b"newer contents")
    backups = tmp_path / "backups"
    link = os.link

    def race_publish(src: Path, dst: Path) -> None:
        dst.write_bytes(b"first original")
        link(src, dst)

    monkeypatch.setattr(os, "link", race_publish)
    assert create_backup(source, backups)
    backup = get_backup_path(source, backups)
    assert backup is not None
    assert backup.read_bytes() == b"first original"
    assert list(backup.parent.iterdir()) == [backup]


def create_legacy_backup(backup_dir: Path, filename: str, content: str) -> Path:
    """Create a legacy-format backup for a file below root_dir."""
    backup_path = backup_dir / filename
    backup_path.parent.mkdir(parents=True)
    backup_path.write_text(content)
    return backup_path


def create_root_file(root_dir: Path, filename: str, content: str) -> Path:
    """Create a file below a media root."""
    file_path = root_dir / filename
    file_path.parent.mkdir(parents=True)
    file_path.write_text(content)
    return file_path


def test_backup_with_none_backup_dir() -> None:
    """Test backup functions with None backup_dir."""
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "test.nfo"
        file_path.write_text("<tvshow></tvshow>")

        assert create_backup(file_path, None) is False
        assert get_backup_path(file_path, None) is None


def test_backup_nonexistent_file() -> None:
    """An enabled backup cannot silently proceed after the source disappears."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "backup"
        file_path = temp_path / "nonexistent.nfo"

        with pytest.raises(FileNotFoundError):
            create_backup(file_path, backup_dir)


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
        same_stem_file = temp_path / "test.bak"
        same_stem_file.write_bytes(b"existing same-stem file")

        # Create backup using the full absolute path structure
        backup_path = backup_dir / file_path.relative_to("/")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text("backup content")

        result = restore_from_backup(file_path, backup_dir)
        assert result is True
        assert file_path.read_text() == "backup content"
        assert not same_stem_file.exists()


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
        restored = temp_path / "poster.png"
        assert not file_path_jpg.exists()
        assert restored.read_bytes() == b"PNG backup"

        # Only one poster file should remain
        poster_files = list(temp_path.glob("poster.*"))
        assert len(poster_files) == 1
        assert poster_files[0] == restored


def test_restore_deletes_files_with_same_stem() -> None:
    """Restore retains the existing same-stem cleanup scope across extensions."""
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
        assert not file_path_jpg.exists()
        assert (temp_path / "poster.png").read_bytes() == b"PNG backup"


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
        file_path = create_root_file(root_dir, "Show A/tvshow.nfo", "original")

        # Legacy backup: relative to root_dir
        legacy_backup = create_legacy_backup(
            backup_dir, "Show A/tvshow.nfo", "original"
        )

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

        file_path = create_root_file(
            root_dir, "Show A/tvshow.nfo", "translated content"
        )

        # Create legacy backup
        legacy_backup = create_legacy_backup(
            backup_dir, "Show A/tvshow.nfo", "original content"
        )

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

        file_path = create_root_file(
            root_dir, "Show A/tvshow.nfo", "translated content"
        )

        # Legacy backup only
        create_legacy_backup(backup_dir, "Show A/tvshow.nfo", "original content")

        result = restore_from_backup(file_path, backup_dir, [root_dir])
        assert result is True
        assert file_path.read_text() == "original content"


def test_legacy_fallback_stem_matching() -> None:
    """Legacy fallback also applies stem-matching for image extension changes."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        root_dir = temp_path / "tv"
        backup_dir = temp_path / "backup"

        file_path_jpg = create_root_file(
            root_dir, "Show A/poster.jpg", "JPEG translated"
        )

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

        file_path = create_root_file(root_dir, "Show A/tvshow.nfo", "content")

        # Only a legacy backup exists
        create_legacy_backup(backup_dir, "Show A/tvshow.nfo", "legacy backup")

        # No root_dirs → only new-format path is checked → not found
        assert get_backup_path(file_path, backup_dir) is None
        assert get_backup_path(file_path, backup_dir, []) is None


def test_get_backup_path_legacy_ignores_root_not_containing_file() -> None:
    """Legacy fallback skips root dirs that don't contain the file (lines 50-51, 96)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        root_dir_a = temp_path / "tv"
        root_dir_b = temp_path / "anime"
        backup_dir = temp_path / "backup"

        # File lives under root_dir_b, NOT root_dir_a
        file_path = create_root_file(root_dir_b, "Show B/tvshow.nfo", "original")

        # Legacy backup only under root_dir_b
        legacy_backup = create_legacy_backup(
            backup_dir, "Show B/tvshow.nfo", "original"
        )

        # root_dir_a does not contain the file → _legacy_backup_path returns None
        # and the loop continues to root_dir_b which does match
        result = get_backup_path(file_path, backup_dir, [root_dir_a, root_dir_b])
        assert result == legacy_backup


def test_create_backup_legacy_skips_root_not_containing_file() -> None:
    """create_backup legacy loop skips root dirs that don't contain the file.

    Exercises the `continue` at line 152 when _legacy_backup_path returns None.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        root_dir_a = temp_path / "tv"
        root_dir_b = temp_path / "anime"
        backup_dir = temp_path / "backup"

        # File lives under root_dir_b, NOT root_dir_a
        file_path = create_root_file(root_dir_b, "Show B/tvshow.nfo", "content")

        # Legacy backup exists under root_dir_b
        legacy_backup = create_legacy_backup(
            backup_dir, "Show B/tvshow.nfo", "original"
        )

        # root_dir_a is passed first (no match) then root_dir_b (legacy found)
        result = create_backup(file_path, backup_dir, [root_dir_a, root_dir_b])
        assert result is True
        # Legacy backup preserved; no new-format backup written
        new_backup = backup_dir / file_path.relative_to("/")
        assert not new_backup.exists()
        assert legacy_backup.read_text() == "original"


def test_create_backup_legacy_stem_match_skips_creation() -> None:
    """create_backup detects a legacy stem-matched backup and skips creating a new one.

    Exercises the stem-matching loop in the legacy fallback (lines 156-159).
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        root_dir = temp_path / "tv"
        backup_dir = temp_path / "backup"

        show_dir = root_dir / "Show A"
        show_dir.mkdir(parents=True)
        # Current file is .jpg
        file_path_jpg = show_dir / "poster.jpg"
        file_path_jpg.write_bytes(b"JPEG translated")

        # Legacy backup exists as .png (same stem, different extension)
        legacy_png = create_legacy_backup(
            backup_dir, "Show A/poster.png", "PNG original"
        )

        result = create_backup(file_path_jpg, backup_dir, [root_dir])
        assert result is True
        # Legacy .png backup preserved
        assert legacy_png.read_bytes() == b"PNG original"
        # No new-format backup created
        new_backup = backup_dir / file_path_jpg.relative_to("/")
        assert not new_backup.exists()


def test_restore_from_backup_file_parent_does_not_exist() -> None:
    """A missing destination directory fails without publishing a restored file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "backup"

        # Backup exists at the new-format path
        file_path = temp_path / "show" / "tvshow.nfo"
        backup_path = backup_dir / file_path.relative_to("/")
        backup_path.parent.mkdir(parents=True)
        backup_path.write_text("original content")

        # Parent of file_path does NOT exist (show dir was never created)
        assert not file_path.parent.exists()

        # Preparing a temporary file requires an existing destination directory.
        with pytest.raises(FileNotFoundError):
            restore_from_backup(file_path, backup_dir)
