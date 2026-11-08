"""Rollback content and access semantics under filesystem failures."""

import errno
import os
import stat
from pathlib import Path

import pytest

from sonarr_metadata_rewrite.backup_utils import create_backup, restore_from_backup


def prepare_restore(
    tmp_path: Path, name: str = "metadata.nfo"
) -> tuple[Path, Path, Path]:
    """Create original bytes in backup and different current contents."""
    target = tmp_path / name
    backups = tmp_path / "backups"
    target.write_bytes(b"original bytes")
    create_backup(target, backups)
    backup = backups / target.relative_to("/")
    target.write_bytes(b"current bytes")
    target.chmod(0o640)
    backup.chmod(0o700)
    os.utime(backup, (1, 1))
    os.utime(target, (2, 2))
    return target, backup, backups


@pytest.mark.parametrize("different_extension", [False, True])
def test_restore_inherits_current_access_not_backup(
    tmp_path: Path, different_extension: bool
) -> None:
    """Restore bytes and backup extension while retaining current access metadata."""
    target, backup, backups = prepare_restore(tmp_path, "poster.png")
    if different_extension:
        target = target.rename(target.with_suffix(".jpg"))
    os.setxattr(target, "user.example", b"current attribute")
    os.setxattr(backup, "user.example", b"backup attribute")
    before = target.stat()

    assert restore_from_backup(target, backups)

    restored = target.with_suffix(".png")
    assert restored.read_bytes() == b"original bytes"
    after = restored.stat()
    assert (after.st_uid, after.st_gid) == (before.st_uid, before.st_gid)
    assert stat.S_IMODE(after.st_mode) == 0o640
    assert os.getxattr(restored, "user.example") == b"current attribute"
    assert after.st_mtime > 2
    assert backup.read_bytes() == b"original bytes"
    if different_extension:
        assert not target.exists()


@pytest.mark.parametrize("failure", ["read", "metadata", "publish"])
@pytest.mark.parametrize("different_extension", [False, True])
def test_failed_preparation_or_publication_leaves_current_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    different_extension: bool,
) -> None:
    """No current file is removed before complete contents and metadata are ready."""
    target, backup, backups = prepare_restore(tmp_path, "poster.png")
    if different_extension:
        target = target.rename(target.with_suffix(".jpg"))
    same_stem_file = target.with_suffix(".webp")
    same_stem_file.write_bytes(b"existing variant")
    read_bytes = Path.read_bytes

    def fail_read(path: Path) -> bytes:
        if path == backup:
            raise OSError(errno.EIO, "content read failed")
        return read_bytes(path)

    def fail_metadata(fd: int, mode: int) -> None:
        raise PermissionError(errno.EPERM, "metadata failed")

    def fail_publish(*args: object, **kwargs: object) -> None:
        raise OSError(errno.EIO, "publication failed")

    if failure == "read":
        monkeypatch.setattr(Path, "read_bytes", fail_read)
    elif failure == "metadata":
        monkeypatch.setattr(os, "fchmod", fail_metadata)
    elif different_extension:
        monkeypatch.setattr(os, "link", fail_publish)
    else:
        monkeypatch.setattr(Path, "replace", fail_publish)
    with pytest.raises(OSError):
        restore_from_backup(target, backups)
    assert target.read_bytes() == b"current bytes"
    assert same_stem_file.read_bytes() == b"existing variant"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    if different_extension:
        assert not target.with_suffix(".png").exists()
    assert list(tmp_path.glob(".tmp_*")) == []


def test_missing_current_file_uses_normal_creation_permissions(tmp_path: Path) -> None:
    """Historical backup permissions and timestamps are not resurrected."""
    target, backup, backups = prepare_restore(tmp_path)
    target.unlink()
    peer = tmp_path / "new-file.nfo"
    peer.write_bytes(b"normal creation")

    assert restore_from_backup(target, backups)

    assert target.read_bytes() == b"original bytes"
    assert stat.S_IMODE(target.stat().st_mode) == stat.S_IMODE(peer.stat().st_mode)
    assert target.stat().st_mtime > backup.stat().st_mtime


def test_cleanup_failure_reports_partial_restore_and_retains_both_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Published restored bytes survive a failure to remove the obsolete image."""
    target, _, backups = prepare_restore(tmp_path, "poster.png")
    target = target.rename(target.with_suffix(".jpg"))
    unlink = Path.unlink

    def fail_cleanup(path: Path, missing_ok: bool = False) -> None:
        if path == target:
            raise PermissionError(errno.EPERM, "cleanup denied")
        unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(OSError, match=r"Restored .*obsolete variant"):
        restore_from_backup(target, backups)
    assert target.read_bytes() == b"current bytes"
    assert target.with_suffix(".png").read_bytes() == b"original bytes"


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo"])
def test_unusual_current_variant_is_not_destroyed(tmp_path: Path, kind: str) -> None:
    """Symlinks and special files are rejected rather than followed or removed."""
    target, _, backups = prepare_restore(tmp_path, "poster.png")
    other = target.with_suffix(".jpg")
    if kind == "symlink":
        other.symlink_to(target)
    elif kind == "directory":
        other.mkdir()
    else:
        os.mkfifo(other)
    with pytest.raises(OSError, match="non-regular"):
        restore_from_backup(target, backups)
    assert target.read_bytes() == b"current bytes"
    assert other.lstat()


def test_unsupported_backup_extension_does_not_destroy_current_image(
    tmp_path: Path,
) -> None:
    """A stem-matched unsupported backup cannot be published under a false format."""
    target, backup, backups = prepare_restore(tmp_path, "poster.png")
    backup = backup.rename(backup.with_suffix(".webp"))
    with pytest.raises(ValueError, match="Unsupported backup image extension"):
        restore_from_backup(target, backups)
    assert target.read_bytes() == b"current bytes"
    assert backup.read_bytes() == b"original bytes"
    assert not list(tmp_path.glob(".tmp_*"))
