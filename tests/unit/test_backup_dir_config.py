"""Regression tests for backup directory configuration sources."""

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from sonarr_metadata_rewrite.backup_utils import create_backup
from sonarr_metadata_rewrite.config import Settings


@pytest.fixture
def settings_kwargs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[dict[str, Any]]:
    """Isolate settings from the host environment and dotenv files."""
    monkeypatch.chdir(tmp_path)
    with patch.dict(os.environ, {}, clear=True):
        yield {
            "tmdb_api_key": "test_key",
            "rewrite_root_dirs": [tmp_path],
            "preferred_languages": ["en-US"],
        }


@pytest.mark.parametrize("source", ["init", "env", "dotenv"])
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", None),
        (" \t ", None),
        ("custom/backups", Path("custom/backups")),
        (" backups with spaces ", Path(" backups with spaces ")),
    ],
)
def test_backup_dir_sources(
    source: str,
    value: str,
    expected: Path | None,
    settings_kwargs: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All sources disable blank paths and preserve nonblank paths verbatim."""
    if source == "init":
        settings_kwargs["original_files_backup_dir"] = value
    elif source == "env":
        monkeypatch.setenv("ORIGINAL_FILES_BACKUP_DIR", value)
    else:
        Path(".env").write_text(f'ORIGINAL_FILES_BACKUP_DIR="{value}"\n')

    settings = Settings(**settings_kwargs)

    assert settings.original_files_backup_dir == expected


def test_backup_dir_default(settings_kwargs: dict[str, Any]) -> None:
    """An omitted backup directory retains the existing default."""
    assert Settings(**settings_kwargs).original_files_backup_dir == Path("backups")


@pytest.mark.parametrize("value", [None, Path("custom/backups")])
def test_backup_dir_python_values(
    value: Path | None, settings_kwargs: dict[str, Any]
) -> None:
    """Explicit None disables backups and Path objects remain supported."""
    settings = Settings(original_files_backup_dir=value, **settings_kwargs)
    assert settings.original_files_backup_dir == value


@pytest.mark.parametrize(
    ("init", "env", "dotenv", "expected"),
    [
        ({}, "", "dotenv-backups", None),
        ({}, " \t ", "dotenv-backups", None),
        ({}, "env-backups", "", Path("env-backups")),
        ({}, None, "", None),
        ({"original_files_backup_dir": None}, "env-backups", "dotenv-backups", None),
        ({"original_files_backup_dir": ""}, "env-backups", "dotenv-backups", None),
        ({"original_files_backup_dir": " \t "}, "env-backups", "", None),
        ({"original_files_backup_dir": "init-backups"}, "", "", Path("init-backups")),
    ],
)
def test_backup_dir_source_precedence(
    init: dict[str, Any],
    env: str | None,
    dotenv: str,
    expected: Path | None,
    settings_kwargs: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Init overrides environment, which overrides dotenv, even for blank values."""
    Path(".env").write_text(f'ORIGINAL_FILES_BACKUP_DIR="{dotenv}"\n')
    if env is not None:
        monkeypatch.setenv("ORIGINAL_FILES_BACKUP_DIR", env)

    settings = Settings(**init, **settings_kwargs)

    assert settings.original_files_backup_dir == expected


@pytest.mark.parametrize("value", ["", " \t "])
def test_blank_backup_dir_creates_no_backup(
    value: str,
    settings_kwargs: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured blank paths prevent backup writes, including under cwd."""
    monkeypatch.setenv("ORIGINAL_FILES_BACKUP_DIR", value)
    settings = Settings(**settings_kwargs)
    source = Path("example.nfo").resolve()
    source.write_text("<tvshow />")

    assert create_backup(source, settings.original_files_backup_dir) is False
    assert list(Path.cwd().iterdir()) == [source]
    assert source.read_text() == "<tvshow />"


@pytest.mark.parametrize("value", [None, "", " \t "])
def test_rollback_rejects_disabled_backups(
    value: str | None, settings_kwargs: dict[str, Any]
) -> None:
    """Rollback requires a backup directory after blank values are normalized."""
    settings_kwargs.update(original_files_backup_dir=value, service_mode="rollback")
    with pytest.raises(
        ValidationError,
        match="ORIGINAL_FILES_BACKUP_DIR is required when SERVICE_MODE=rollback",
    ):
        Settings(**settings_kwargs)
