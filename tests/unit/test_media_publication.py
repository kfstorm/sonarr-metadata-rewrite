"""Media publication on filesystems with limited hard-link/rename support."""

import ctypes
import errno
import os
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sonarr_metadata_rewrite.backup_utils import (
    create_backup,
    get_backup_path,
    restore_from_backup,
)
from sonarr_metadata_rewrite.file_utils import atomic_write_bytes, replace_file_bytes


@pytest.fixture(
    params=["native", "ENOSYS", "EOPNOTSUPP", "EINVAL", "missing", "nonlinux"]
)
def linkless_filesystem(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    disable_hard_links: Callable[[], None],
) -> str:
    """Exercise native no-clobber rename and checked-rename fallbacks."""
    disable_hard_links()
    support = str(request.param)
    if support == "nonlinux":
        monkeypatch.setattr(sys, "platform", "unsupported-platform")
    elif support != "native":

        def unavailable_rename(*args: object) -> int:
            ctypes.set_errno(getattr(errno, support))
            return -1

        library = (
            SimpleNamespace()
            if support == "missing"
            else SimpleNamespace(renameat2=Mock(side_effect=unavailable_rename))
        )
        monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: library)
    return support


@pytest.mark.parametrize("link_error", [None, errno.ENOSYS, errno.EOPNOTSUPP])
def test_publish_complete_new_media_without_requiring_hard_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link_error: int | None
) -> None:
    """New media paths accept complete prepared bytes, even without hard links."""
    target = tmp_path / "metadata.nfo"
    if link_error is not None:

        def unsupported_link(src: Path, dst: Path) -> None:
            assert src.read_bytes() == b"complete restored contents"
            assert not dst.exists()
            raise OSError(link_error, "hard links unavailable")

        monkeypatch.setattr(os, "link", unsupported_link)
    atomic_write_bytes(target, b"complete restored contents", mode_from=None)
    assert target.read_bytes() == b"complete restored contents"
    assert not list(tmp_path.glob(".tmp_*"))


def test_linkless_extension_rewrite_preserves_complete_contents_and_access(
    tmp_path: Path,
    linkless_filesystem: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Extension changes require neither hard links nor partial final media files."""
    source = tmp_path / "poster.jpg"
    source.write_bytes(b"old image")
    source.chmod(0o640)
    target = source.with_suffix(".png")
    replace_file_bytes(source, target, b"complete new image")
    assert not source.exists()
    assert target.read_bytes() == b"complete new image"
    assert target.stat().st_mode & 0o777 == 0o640
    assert not list(tmp_path.glob(".tmp_*"))
    assert ("Concurrent creation" in caplog.text) == (linkless_filesystem != "native")


def test_racing_destination_is_not_clobbered_after_unsupported_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, linkless_filesystem: str
) -> None:
    """A file created after preparation survives both no-clobber and checked rename."""
    source = tmp_path / "poster.jpg"
    source.write_bytes(b"current image")
    target = source.with_suffix(".png")

    def racing_link(src: Path, dst: Path) -> None:
        dst.write_bytes(b"concurrent image")
        raise OSError(errno.EOPNOTSUPP, "links unsupported")

    monkeypatch.setattr(os, "link", racing_link)
    with pytest.raises(OSError):
        replace_file_bytes(source, target, b"restored image")
    assert source.read_bytes() == b"current image"
    assert target.read_bytes() == b"concurrent image"
    assert not list(tmp_path.glob(".tmp_*"))


@pytest.mark.parametrize("error_number", [errno.EIO, errno.EPERM, errno.ENOSPC])
def test_unrelated_link_errors_never_trigger_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_number: int
) -> None:
    """Only unsupported-operation errors may select a different publication method."""
    target = tmp_path / "new.nfo"

    def fail_link(src: Path, dst: Path) -> None:
        raise OSError(error_number, "link failed")

    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(OSError, match="link failed") as failure:
        atomic_write_bytes(target, b"prepared bytes", mode_from=None)
    assert failure.value.errno == error_number
    assert not target.exists()
    assert not list(tmp_path.glob(".tmp_*"))


@pytest.mark.parametrize("error_number", [errno.EIO, errno.EPERM])
def test_native_noclobber_rename_failure_does_not_fall_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disable_hard_links: Callable[[], None],
    error_number: int,
) -> None:
    """A real rename failure leaves the source intact without trying plain rename."""
    disable_hard_links()
    source = tmp_path / "poster.jpg"
    source.write_bytes(b"unchanged")
    target = source.with_suffix(".png")

    def fail_rename(*args: object) -> int:
        ctypes.set_errno(error_number)
        return -1

    library = SimpleNamespace(renameat2=Mock(side_effect=fail_rename))
    monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: library)
    with pytest.raises(OSError) as failure:
        replace_file_bytes(source, target, b"replacement")
    assert failure.value.errno == error_number
    assert source.read_bytes() == b"unchanged"
    assert not target.exists()
    assert not list(tmp_path.glob(".tmp_*"))


@pytest.mark.parametrize(
    "linkless_filesystem",
    ["ENOSYS", "EOPNOTSUPP", "EINVAL", "missing", "nonlinux"],
    indirect=True,
)
def test_checked_rename_failure_retains_current_media(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, linkless_filesystem: str
) -> None:
    """Failure of the final guarded rename cannot remove current image bytes."""
    source = tmp_path / "poster.jpg"
    source.write_bytes(b"current contents")
    target = source.with_suffix(".png")

    def fail_rename(src: Path, dst: Path) -> None:
        assert src.read_bytes() == b"complete replacement"
        raise OSError(errno.EIO, "checked rename failed")

    monkeypatch.setattr(Path, "rename", fail_rename)
    with pytest.raises(OSError, match="checked rename failed"):
        replace_file_bytes(source, target, b"complete replacement")
    assert source.read_bytes() == b"current contents"
    assert not target.exists()
    assert not list(tmp_path.glob(".tmp_*"))


def test_backup_publication_remains_strict_when_media_links_are_unavailable(
    tmp_path: Path, disable_hard_links: Callable[[], None]
) -> None:
    """Media compatibility must not weaken first-backup-wins guarantees."""
    source = tmp_path / "movie.nfo"
    source.write_bytes(b"original")
    backups = tmp_path / "backups"
    assert create_backup(source, backups)
    source.write_bytes(b"modified")
    disable_hard_links()
    assert create_backup(source, backups)
    backup = get_backup_path(source, backups)
    assert backup is not None
    assert backup.read_bytes() == b"original"
    other = tmp_path / "episode.nfo"
    other.write_bytes(b"another original")
    with pytest.raises(OSError) as failure:
        create_backup(other, backups)
    assert failure.value.errno == errno.EOPNOTSUPP
    assert get_backup_path(other, backups) is None
    assert other.read_bytes() == b"another original"
    assert not list(backups.rglob(".backup_*"))


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("current_image", [False, True])
def test_linkless_rollback_publishes_backup_extension_with_or_without_current_file(
    tmp_path: Path, linkless_filesystem: str, legacy: bool, current_image: bool
) -> None:
    """Both backup layouts restore through linkless publication with current access."""
    media = tmp_path / "media"
    media.mkdir()
    requested = media / "poster.jpg"
    restored = media / "poster.png"
    backups = tmp_path / "backups"
    relative = restored.relative_to(tmp_path if legacy else "/")
    backup = backups / relative
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b"complete original PNG")
    backup.chmod(0o700)
    peer = media / "ordinary-file"
    peer.touch()
    if current_image:
        requested.write_bytes(b"current JPEG")
        requested.chmod(0o640)
    assert restore_from_backup(requested, backups, [tmp_path])
    assert restored.read_bytes() == b"complete original PNG"
    expected_mode = 0o640 if current_image else peer.stat().st_mode & 0o777
    assert restored.stat().st_mode & 0o777 == expected_mode
    assert not requested.exists()
    assert backup.read_bytes() == b"complete original PNG"
    assert not list(media.glob(".tmp_*"))


def test_checked_publication_rechecks_destination_after_noclobber_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disable_hard_links: Callable[[], None],
) -> None:
    """A creator racing the unsupported primitive is caught by the final guard."""
    disable_hard_links()
    target = tmp_path / "new.nfo"

    def racing_library(*args: object, **kwargs: object) -> SimpleNamespace:
        target.write_bytes(b"concurrently created contents")
        return SimpleNamespace()

    monkeypatch.setattr(ctypes, "CDLL", racing_library)
    with pytest.raises(OSError, match="changed during preparation"):
        atomic_write_bytes(target, b"prepared replacement", mode_from=None)
    assert target.read_bytes() == b"concurrently created contents"
    assert not list(tmp_path.glob(".tmp_*"))
