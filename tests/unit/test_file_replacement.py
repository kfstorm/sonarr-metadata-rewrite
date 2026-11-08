"""Filesystem-state regression tests for safe replacement and access metadata."""

import errno
import os
import stat
import struct
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO
from unittest.mock import Mock

import pytest

from sonarr_metadata_rewrite.file_utils import atomic_write_bytes


def add_access_acl(target: Path, named_user: int = 12345) -> bytes:
    """Install a synthetic Linux POSIX ACL with an additional read-only user."""
    entries = [
        (1, 6, 0xFFFFFFFF),
        (2, 4, named_user),
        (4, 4, 0xFFFFFFFF),
        (16, 4, 0xFFFFFFFF),
        (32, 0, 0xFFFFFFFF),
    ]
    value = struct.pack("<I", 2) + b"".join(
        struct.pack("<HHI", *entry) for entry in entries
    )
    os.setxattr(target, "system.posix_acl_access", value)
    return value


def test_preserves_readable_xattrs_and_fresh_mtime(tmp_path: Path) -> None:
    """Replacement inherits current access attributes without historical times."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"old")
    target.chmod(0o2640)
    os.setxattr(target, "user.example", b"retained")
    os.utime(target, (1, 1))
    before = target.stat()

    atomic_write_bytes(target, b"new", mode_from=target)

    after = target.stat()
    assert target.read_bytes() == b"new"
    assert (after.st_uid, after.st_gid) == (before.st_uid, before.st_gid)
    assert stat.S_IMODE(after.st_mode) == 0o2640
    assert os.getxattr(target, "user.example") == b"retained"
    assert after.st_mtime > before.st_mtime


@pytest.mark.parametrize("mode", [0o600, 0o640])
def test_failed_chmod_requires_matching_effective_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: int
) -> None:
    """A denied chmod is harmless only if permissions already match."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"old")
    target.chmod(mode)

    def deny_chmod(fd: int, _requested: int) -> None:
        raise PermissionError(errno.EPERM, "chmod denied")

    monkeypatch.setattr(os, "fchmod", deny_chmod)
    if mode == 0o600:
        atomic_write_bytes(target, b"new", mode_from=target)
        assert target.read_bytes() == b"new"
    else:
        with pytest.raises(OSError):
            atomic_write_bytes(target, b"new", mode_from=target)
        assert target.read_bytes() == b"old"
    assert stat.S_IMODE(target.stat().st_mode) == mode
    assert list(tmp_path.glob(".tmp_*")) == []


def test_matching_ownership_does_not_require_chown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-root rewrite with matching UID/GID never needs chown privileges."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"old")
    before = target.stat()

    def forbidden_chown(fd: int, uid: int, gid: int) -> None:
        pytest.fail("Unnecessary chown")

    monkeypatch.setattr(os, "fchown", forbidden_chown)
    atomic_write_bytes(target, b"new", mode_from=target)
    assert target.read_bytes() == b"new"
    assert (target.stat().st_uid, target.stat().st_gid) == (
        before.st_uid,
        before.st_gid,
    )


@pytest.mark.parametrize("matches_after_error", [False, True])
def test_failed_chown_requires_matching_effective_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, matches_after_error: bool
) -> None:
    """An ownership mismatch cannot silently publish a different-owner inode."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"old")
    before = target.stat()
    fstat = os.fstat
    attempted = False

    def different_owner(fd: int) -> os.stat_result:
        result = fstat(fd)
        if attempted and matches_after_error:
            return result
        fields = list(result)
        fields[4] = result.st_uid + 1
        return os.stat_result(fields)

    def deny_chown(fd: int, uid: int, gid: int) -> None:
        nonlocal attempted
        attempted = True
        raise PermissionError(errno.EPERM, "chown denied")

    monkeypatch.setattr(os, "fstat", different_owner)
    monkeypatch.setattr(os, "fchown", deny_chown)
    if matches_after_error:
        atomic_write_bytes(target, b"new", mode_from=target)
        assert target.read_bytes() == b"new"
    else:
        with pytest.raises(PermissionError, match="chown denied"):
            atomic_write_bytes(target, b"new", mode_from=target)
        assert target.read_bytes() == b"old"
    assert (target.stat().st_uid, target.stat().st_gid) == (
        before.st_uid,
        before.st_gid,
    )
    assert list(tmp_path.glob(".tmp_*")) == []


def test_group_only_chown_does_not_request_unchanged_uid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Group restoration is compatible with non-root Linux chown restrictions."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"old")
    target.chmod(0o2640)
    fstat = os.fstat
    fchown = os.fchown
    restored = False

    def different_group(fd: int) -> os.stat_result:
        result = fstat(fd)
        if restored:
            return result
        fields = list(result)
        fields[5] = result.st_gid + 1
        return os.stat_result(fields)

    def restore_group(fd: int, uid: int, gid: int) -> None:
        nonlocal restored
        assert uid == -1
        fchown(fd, uid, gid)
        restored = True

    monkeypatch.setattr(os, "fstat", different_group)
    monkeypatch.setattr(os, "fchown", restore_group)
    atomic_write_bytes(target, b"new", mode_from=target)
    assert restored
    assert target.read_bytes() == b"new"
    assert stat.S_IMODE(target.stat().st_mode) == 0o2640


@pytest.mark.parametrize(
    "error_number",
    [errno.EIO, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS, errno.EPERM],
)
def test_unavailable_xattr_listing_probes_access_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_number: int
) -> None:
    """A failed enumeration need not fail when access attributes remain readable."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"old")
    acl = add_access_acl(target)

    def fail_listing(*args: object, **kwargs: object) -> list[str]:
        raise OSError(error_number, "listing failed")

    monkeypatch.setattr(os, "listxattr", fail_listing)
    atomic_write_bytes(target, b"new", mode_from=target)
    assert target.read_bytes() == b"new"
    assert os.getxattr(target, "system.posix_acl_access") == acl
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


@pytest.mark.parametrize(
    "error_number",
    [errno.EIO, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS, errno.EPERM],
)
@pytest.mark.parametrize("attribute", ["user.example", "system.posix_acl_access"])
def test_optional_xattr_failure_and_strict_acl_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_number: int, attribute: str
) -> None:
    """Unsupported optional metadata is skipped; a lost effective ACL is fatal."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"old")
    is_acl = attribute == "system.posix_acl_access"
    value = add_access_acl(target) if is_acl else b"optional value"
    if not is_acl:
        os.setxattr(target, attribute, value)
    setxattr = os.setxattr

    def fail_attribute(fd: int, name: str, data: bytes) -> None:
        if name == attribute:
            raise OSError(error_number, "attribute write failed")
        setxattr(fd, name, data)

    monkeypatch.setattr(os, "setxattr", fail_attribute)
    if is_acl:
        with pytest.raises(OSError):
            atomic_write_bytes(target, b"new", mode_from=target)
        assert target.read_bytes() == b"old"
        assert os.getxattr(target, attribute) == value
    else:
        atomic_write_bytes(target, b"new", mode_from=target)
        assert target.read_bytes() == b"new"
    assert list(tmp_path.glob(".tmp_*")) == []


@pytest.mark.parametrize(
    "error_number", [errno.EIO, errno.EPERM, errno.ENOTSUP, errno.ENOSYS, errno.ENODATA]
)
def test_unreadable_access_attribute_fails_before_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_number: int
) -> None:
    """An unknown effective ACL must never be silently discarded."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"old")
    add_access_acl(target)
    getxattr = os.getxattr

    def unreadable_acl(
        path: Path | int, name: str, *, follow_symlinks: bool = True
    ) -> bytes:
        if name == "system.posix_acl_access":
            raise OSError(error_number, "ACL read failed")
        return (
            getxattr(path, name)
            if isinstance(path, int)
            else getxattr(path, name, follow_symlinks=follow_symlinks)
        )

    monkeypatch.setattr(os, "getxattr", unreadable_acl)
    with pytest.raises(OSError, match="ACL read failed"):
        atomic_write_bytes(target, b"new", mode_from=target)
    assert target.read_bytes() == b"old"
    assert list(tmp_path.glob(".tmp_*")) == []


def test_detectable_concurrent_modification_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file modified during preparation survives instead of being overwritten."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"old")
    fchmod = os.fchmod

    def concurrent_write(fd: int, mode: int) -> None:
        target.write_bytes(b"concurrent contents")
        fchmod(fd, mode)

    monkeypatch.setattr(os, "fchmod", concurrent_write)
    with pytest.raises(OSError, match="changed during preparation"):
        atomic_write_bytes(target, b"new", mode_from=target)
    assert target.read_bytes() == b"concurrent contents"
    assert list(tmp_path.glob(".tmp_*")) == []


@pytest.mark.parametrize("removal_succeeds", [False, True])
def test_inherited_acl_cannot_grant_additional_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, removal_succeeds: bool
) -> None:
    """Directory default ACLs must not add named-user access to a replacement."""
    source = tmp_path / "source.nfo"
    source.write_bytes(b"old")
    source.chmod(0o640)
    directory = tmp_path / "destination"
    directory.mkdir()
    acl_file = tmp_path / "acl-template"
    acl_file.touch()
    acl = add_access_acl(acl_file)
    os.setxattr(directory, "system.posix_acl_default", acl)
    destination = directory / "metadata.nfo"

    if not removal_succeeds:
        monkeypatch.setattr(os, "removexattr", lambda *args: None)
        with pytest.raises(OSError, match="Access attribute"):
            atomic_write_bytes(destination, b"new", mode_from=source)
        assert not destination.exists()
    else:
        atomic_write_bytes(destination, b"new", mode_from=source)
        assert destination.read_bytes() == b"new"
        assert "system.posix_acl_access" not in os.listxattr(destination)
        assert stat.S_IMODE(destination.stat().st_mode) == 0o640
    assert source.read_bytes() == b"old"
    assert not list(directory.glob(".tmp_*"))


@pytest.mark.parametrize("degraded", [False, True])
def test_partial_content_write_is_not_a_metadata_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, degraded: bool
) -> None:
    """Content EIO must retain the complete old file and discard partial bytes."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"complete old content")
    fdopen = os.fdopen

    @contextmanager
    def partial_writer(fd: int, mode: str) -> Iterator[BinaryIO]:
        with fdopen(fd, mode) as output:

            def partial_write(content: bytes) -> None:
                output.write(content[:3])
                raise OSError(errno.EIO, "content write failed")

            writer = Mock(wraps=output)
            writer.write.side_effect = partial_write
            yield writer

    monkeypatch.setattr(os, "fdopen", partial_writer)
    if degraded:

        def unavailable_xattrs(*args: object, **kwargs: object) -> None:
            raise OSError(errno.EIO, "metadata unavailable")

        monkeypatch.setattr(os, "listxattr", unavailable_xattrs)
        monkeypatch.setattr(os, "getxattr", unavailable_xattrs)
    with pytest.raises(OSError, match="content write failed"):
        atomic_write_bytes(target, b"complete new content", mode_from=target)
    assert target.read_bytes() == b"complete old content"
    assert not list(tmp_path.glob(".tmp_*"))


def test_unrelated_system_xattr_does_not_block_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A filesystem-specific system attribute need not be access-control data."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"old")
    getxattr = os.getxattr

    def read_attribute(
        path: Path | int, name: str, *, follow_symlinks: bool = True
    ) -> bytes:
        if name == "system.example":
            return b"optional filesystem metadata"
        return (
            getxattr(path, name)
            if isinstance(path, int)
            else getxattr(path, name, follow_symlinks=follow_symlinks)
        )

    def unsupported_write(fd: int, name: str, value: bytes) -> None:
        raise OSError(errno.EOPNOTSUPP, "unsupported attribute")

    monkeypatch.setattr(os, "listxattr", lambda *args, **kwargs: ["system.example"])
    monkeypatch.setattr(os, "getxattr", read_attribute)
    monkeypatch.setattr(os, "setxattr", unsupported_write)
    atomic_write_bytes(target, b"new", mode_from=target)
    assert target.read_bytes() == b"new"
    assert not list(tmp_path.glob(".tmp_*"))


def test_creation_without_metadata_source_cannot_replace_an_existing_file(
    tmp_path: Path,
) -> None:
    """A newly appeared target must not be overwritten using default permissions."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"concurrent contents")
    target.chmod(0o640)
    with pytest.raises(FileExistsError):
        atomic_write_bytes(target, b"restored contents", mode_from=None)
    assert target.read_bytes() == b"concurrent contents"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert not list(tmp_path.glob(".tmp_*"))


@pytest.mark.parametrize(
    "operation",
    ["list", "optional_read", "optional_write", "access_probe", "access_verify"],
)
@pytest.mark.parametrize(
    "error_number", [errno.EIO, errno.EPERM, errno.ENOTSUP, errno.ENOSPC]
)
def test_metadata_error_policy_depends_on_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str, error_number: int
) -> None:
    """Only expected optional-metadata failures may publish a replacement."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"original")
    target.chmod(0o640)
    os.setxattr(target, "user.example", b"optional metadata")
    acl = add_access_acl(target) if operation == "access_verify" else None
    listxattr, getxattr, setxattr = os.listxattr, os.getxattr, os.setxattr

    def list_attributes(path: Path, *, follow_symlinks: bool = True) -> list[str]:
        if operation == "list":
            raise OSError(error_number, "injected metadata error")
        return listxattr(path, follow_symlinks=follow_symlinks)

    def read_attribute(
        path: Path | int, name: str, *, follow_symlinks: bool = True
    ) -> bytes:
        optional_read = operation == "optional_read" and name == "user.example"
        access_read = (
            operation in {"access_probe", "access_verify"}
            and isinstance(path, int)
            and name == "system.posix_acl_access"
        )
        if optional_read or access_read:
            raise OSError(error_number, "injected metadata error")
        return (
            getxattr(path, name)
            if isinstance(path, int)
            else getxattr(path, name, follow_symlinks=follow_symlinks)
        )

    def write_attribute(fd: int, name: str, value: bytes) -> None:
        if operation == "optional_write" and name == "user.example":
            raise OSError(error_number, "injected metadata error")
        setxattr(fd, name, value)

    monkeypatch.setattr(os, "listxattr", list_attributes)
    monkeypatch.setattr(os, "getxattr", read_attribute)
    monkeypatch.setattr(os, "setxattr", write_attribute)
    allowed = (
        operation in {"list", "optional_read", "optional_write"}
        and error_number != errno.ENOSPC
    ) or (operation == "access_probe" and error_number != errno.ENOSPC)
    if allowed:
        atomic_write_bytes(target, b"replacement", mode_from=target)
        assert target.read_bytes() == b"replacement"
    else:
        with pytest.raises(OSError, match="injected metadata error") as failure:
            atomic_write_bytes(target, b"replacement", mode_from=target)
        assert failure.value.errno == error_number
        assert target.read_bytes() == b"original"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    if acl is not None:
        assert getxattr(target, "system.posix_acl_access") == acl
    assert not list(tmp_path.glob(".tmp_*"))


@pytest.mark.parametrize("matching_acl", [False, True])
def test_denied_acl_write_requires_matching_inherited_acl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, matching_acl: bool
) -> None:
    """A denied ACL write may proceed only when inherited effective access matches."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"original")
    expected_acl = add_access_acl(target)
    template = tmp_path / "acl-template"
    template.touch()
    inherited_acl = add_access_acl(
        template, named_user=12345 if matching_acl else 23456
    )
    os.setxattr(tmp_path, "system.posix_acl_default", inherited_acl)
    setxattr = os.setxattr

    def deny_acl_write(fd: int, name: str, value: bytes) -> None:
        if name == "system.posix_acl_access":
            raise PermissionError(errno.EPERM, "ACL write denied")
        setxattr(fd, name, value)

    monkeypatch.setattr(os, "setxattr", deny_acl_write)
    if matching_acl:
        atomic_write_bytes(target, b"replacement", mode_from=target)
        assert target.read_bytes() == b"replacement"
    else:
        with pytest.raises(PermissionError, match="ACL write denied"):
            atomic_write_bytes(target, b"replacement", mode_from=target)
        assert target.read_bytes() == b"original"
    assert os.getxattr(target, "system.posix_acl_access") == expected_acl
    assert not list(tmp_path.glob(".tmp_*"))


@pytest.mark.parametrize("missing_api", ["listxattr", "getxattr"])
def test_replacement_without_xattr_api_preserves_posix_attributes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing_api: str
) -> None:
    """Platforms without xattr APIs still preserve ownership and mode."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"original")
    target.chmod(0o640)
    before = target.stat()
    monkeypatch.delattr(os, missing_api)
    atomic_write_bytes(target, b"replacement", mode_from=target)
    assert target.read_bytes() == b"replacement"
    after = target.stat()
    assert (after.st_uid, after.st_gid, stat.S_IMODE(after.st_mode)) == (
        before.st_uid,
        before.st_gid,
        0o640,
    )


def test_silently_ignored_chmod_does_not_publish_incorrect_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful syscall is insufficient when final permission bits differ."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"original")
    target.chmod(0o640)
    monkeypatch.setattr(os, "fchmod", lambda *args: None)
    with pytest.raises(PermissionError, match="ownership or permission mode"):
        atomic_write_bytes(target, b"replacement", mode_from=target)
    assert target.read_bytes() == b"original"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert not list(tmp_path.glob(".tmp_*"))


def test_missing_metadata_source_leaves_existing_destination_intact(
    tmp_path: Path,
) -> None:
    """A disappeared metadata source cannot downgrade an existing target's access."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"original")
    with pytest.raises(FileNotFoundError):
        atomic_write_bytes(target, b"replacement", mode_from=tmp_path / "missing.nfo")
    assert target.read_bytes() == b"original"
    assert not list(tmp_path.glob(".tmp_*"))


def test_failed_temp_cleanup_keeps_primary_failure_and_reports_leftover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Cleanup errors must not hide a publication failure or destroy old contents."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"original")

    def fail_publication(*args: object) -> None:
        raise OSError(errno.EIO, "publication failed")

    def fail_cleanup(*args: object, **kwargs: object) -> None:
        raise PermissionError(errno.EPERM, "temporary cleanup denied")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail_publication)
        patch.setattr(Path, "unlink", fail_cleanup)
        with pytest.raises(OSError, match="publication failed") as failure:
            atomic_write_bytes(target, b"replacement", mode_from=target)
        assert failure.value.errno == errno.EIO
    assert target.read_bytes() == b"original"
    leftovers = list(tmp_path.glob(".tmp_*"))
    assert len(leftovers) == 1
    assert leftovers[0].read_bytes() == b"replacement"
    assert "Failed to clean up replacement temporary file" in caplog.text
    assert "temporary cleanup denied" in caplog.text
    leftovers[0].unlink()


@pytest.mark.parametrize("unavailable_on", ["source", "temporary", "both"])
@pytest.mark.parametrize(
    "error_number", [errno.EIO, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS]
)
def test_unavailable_xattr_interfaces_preserve_verified_posix_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    unavailable_on: str,
    error_number: int,
) -> None:
    """Unavailable metadata APIs cannot make ordinary FUSE writes unusable."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"original")
    target.chmod(0o2640)
    before = target.stat()
    listxattr, getxattr = os.listxattr, os.getxattr

    def unavailable(path: Path | int) -> bool:
        return unavailable_on == "both" or (
            isinstance(path, int) == (unavailable_on == "temporary")
        )

    def list_attributes(path: Path | int, *, follow_symlinks: bool = True) -> list[str]:
        if unavailable(path):
            raise OSError(error_number, "xattr API unavailable")
        return listxattr(path)

    def read_attribute(
        path: Path | int, name: str, *, follow_symlinks: bool = True
    ) -> bytes:
        if unavailable(path):
            raise OSError(error_number, "xattr API unavailable")
        return getxattr(path, name)

    monkeypatch.setattr(os, "listxattr", list_attributes)
    monkeypatch.setattr(os, "getxattr", read_attribute)
    atomic_write_bytes(target, b"replacement", mode_from=target)
    after = target.stat()
    assert target.read_bytes() == b"replacement"
    assert (after.st_uid, after.st_gid, stat.S_IMODE(after.st_mode)) == (
        before.st_uid,
        before.st_gid,
        0o2640,
    )
    assert "cannot verify" in caplog.text
    assert not list(tmp_path.glob(".tmp_*"))


@pytest.mark.parametrize("error_number", [errno.EIO, errno.ENOSYS, errno.ENOTSUP])
def test_identified_acl_requires_usable_temporary_xattr_interface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_number: int
) -> None:
    """Degraded temporary metadata cannot waive verification of a known source ACL."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"protected original")
    acl = add_access_acl(target)
    getxattr = os.getxattr

    def unavailable_on_fd(
        path: Path | int, name: str, *, follow_symlinks: bool = True
    ) -> bytes:
        if isinstance(path, int):
            raise OSError(error_number, "temporary xattrs unavailable")
        return getxattr(path, name, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "getxattr", unavailable_on_fd)
    with pytest.raises(OSError, match="temporary xattrs unavailable"):
        atomic_write_bytes(target, b"new", mode_from=target)
    assert target.read_bytes() == b"protected original"
    assert getxattr(target, "system.posix_acl_access") == acl
    assert not list(tmp_path.glob(".tmp_*"))


@pytest.mark.parametrize("location", ["source", "temporary"])
@pytest.mark.parametrize("operation", ["listxattr", "getxattr"])
def test_unexpected_metadata_error_stops_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, location: str, operation: str
) -> None:
    """Resource failures are not evidence that an xattr API is merely unsupported."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"unchanged contents")
    original = getattr(os, operation)

    def fail_metadata(path: Path | int, *args: object, **kwargs: object) -> object:
        if isinstance(path, int) == (location == "temporary"):
            raise OSError(errno.ENOSPC, "unexpected metadata failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, operation, fail_metadata)
    with pytest.raises(OSError, match="unexpected metadata failure"):
        atomic_write_bytes(target, b"replacement", mode_from=target)
    assert target.read_bytes() == b"unchanged contents"
    assert not list(tmp_path.glob(".tmp_*"))


@pytest.mark.parametrize("attribute", ["system.posix_acl_access", "security.example"])
def test_inherited_access_attribute_is_not_removed_when_source_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attribute: str
) -> None:
    """An unavailable source interface is not evidence an inherited grant is absent."""
    target = tmp_path / "metadata.nfo"
    target.write_bytes(b"protected contents")
    listxattr, getxattr = os.listxattr, os.getxattr

    def enumerate_attributes(
        path: Path | int, *, follow_symlinks: bool = True
    ) -> list[str]:
        if not isinstance(path, int):
            raise OSError(errno.EIO, "source enumeration unavailable")
        return [*listxattr(path), attribute]

    def read_attribute(
        path: Path | int, name: str, *, follow_symlinks: bool = True
    ) -> bytes:
        if name == attribute:
            if isinstance(path, int):
                return b"synthetic inherited access metadata"
            raise OSError(errno.EIO, "source access metadata unavailable")
        return getxattr(path, name)

    monkeypatch.setattr(os, "listxattr", enumerate_attributes)
    monkeypatch.setattr(os, "getxattr", read_attribute)
    with pytest.raises(OSError, match="Cannot establish original access attribute"):
        atomic_write_bytes(target, b"replacement", mode_from=target)
    assert target.read_bytes() == b"protected contents"
    assert not list(tmp_path.glob(".tmp_*"))
