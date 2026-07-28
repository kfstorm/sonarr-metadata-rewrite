"""Tests for service-mode-dependent TMDB API key validation."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from sonarr_metadata_rewrite.config import Settings, get_settings
from sonarr_metadata_rewrite.main import cli


@pytest.mark.parametrize("api_key", ["", " ", "\t", "\n"])
def test_rewrite_mode_rejects_empty_tmdb_api_key(
    api_key: str,
    tmp_path: Path,
) -> None:
    """Rewrite mode requires a non-empty TMDB API key."""
    with pytest.raises(
        ValidationError,
        match="TMDB_API_KEY is required when SERVICE_MODE=rewrite",
    ):
        Settings(
            tmdb_api_key=api_key,
            rewrite_root_dirs=[tmp_path],
            preferred_languages=["zh-CN"],
            service_mode="rewrite",
        )


def test_rewrite_mode_rejects_missing_tmdb_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rewrite mode rejects an omitted TMDB API key."""
    monkeypatch.delenv("TMDB_API_KEY", raising=False)

    with pytest.raises(
        ValidationError,
        match="TMDB_API_KEY is required when SERVICE_MODE=rewrite",
    ):
        Settings(
            _env_file=None,
            rewrite_root_dirs=[tmp_path],
            preferred_languages=["zh-CN"],
            service_mode="rewrite",
        )


@pytest.mark.parametrize("api_key", ["", " ", "\t"])
def test_rollback_mode_allows_empty_tmdb_api_key(
    api_key: str,
    tmp_path: Path,
) -> None:
    """Rollback mode does not access TMDB and allows an empty API key."""
    settings = Settings(
        tmdb_api_key=api_key,
        rewrite_root_dirs=[tmp_path],
        preferred_languages=["zh-CN"],
        service_mode="rollback",
    )

    assert settings.tmdb_api_key == ""


def test_rollback_mode_allows_missing_tmdb_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollback mode allows the TMDB API key to be omitted."""
    monkeypatch.delenv("TMDB_API_KEY", raising=False)

    settings = Settings(
        _env_file=None,
        rewrite_root_dirs=[tmp_path],
        preferred_languages=["zh-CN"],
        service_mode="rollback",
    )

    assert settings.tmdb_api_key == ""


def test_get_settings_rejects_empty_tmdb_api_key_in_rewrite_mode(
    tmp_path: Path,
) -> None:
    """Environment loading reports a configuration error before HTTP setup."""
    env_vars = {
        "TMDB_API_KEY": " ",
        "REWRITE_ROOT_DIR": str(tmp_path),
        "PREFERRED_LANGUAGES": "zh-CN",
        "SERVICE_MODE": "rewrite",
    }

    with (
        patch.dict(os.environ, env_vars, clear=True),
        pytest.raises(
            ValueError,
            match="TMDB_API_KEY is required when SERVICE_MODE=rewrite",
        ),
    ):
        get_settings()


def test_cli_rollback_mode_runs_without_tmdb_api_key(tmp_path: Path) -> None:
    """Rollback CLI starts without logging or requiring a TMDB API key."""
    runner = CliRunner()
    env_vars = {
        "REWRITE_ROOT_DIR": str(tmp_path),
        "PREFERRED_LANGUAGES": "zh-CN",
        "SERVICE_MODE": "rollback",
    }

    with (
        runner.isolated_filesystem(),
        patch.dict(os.environ, env_vars, clear=True),
        patch("sonarr_metadata_rewrite.main.RollbackService") as rollback_service,
    ):
        rollback_service.return_value.execute_rollback.return_value = None
        rollback_service.return_value.hang_after_completion.side_effect = (
            KeyboardInterrupt()
        )
        result = runner.invoke(cli)

    assert result.exit_code == 0
    assert "🔧 Service mode: rollback" in result.output
    assert "🔄 Executing rollback operation..." in result.output
    assert "TMDB API key loaded" not in result.output
