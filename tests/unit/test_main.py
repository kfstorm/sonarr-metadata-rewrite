"""Unit tests for main CLI module."""

import os
from unittest.mock import patch

from click.testing import CliRunner

from sonarr_metadata_rewrite.main import cli


class TestCli:
    """Test CLI functionality."""

    def test_cli_with_valid_api_key(self) -> None:
        """Test CLI with valid TMDB API key."""
        test_key = "test_api_key_1234567890abcdef"
        runner = CliRunner()

        with runner.isolated_filesystem():
            env_vars = {"TMDB_API_KEY": test_key, "REWRITE_ROOT_DIR": "/tmp/test"}
            with patch.dict(os.environ, env_vars):
                # Mock the service to avoid actually starting it
                with patch(
                    "sonarr_metadata_rewrite.main.RewriteService"
                ) as mock_service:
                    mock_service.return_value.is_running.return_value = False
                    result = runner.invoke(cli)

            # Check the initial output
            assert "🚀 Starting Sonarr Metadata Translation Layer..." in result.output
            assert (
                f"✅ TMDB API key loaded (ending in ...{test_key[-4:]})"
                in result.output
            )

    def test_cli_missing_api_key(self) -> None:
        """Test CLI with missing TMDB API key."""
        runner = CliRunner()

        with patch.dict(os.environ, {}, clear=True):
            result = runner.invoke(cli)

        assert result.exit_code == 1
        # Check for the actual pydantic validation error message
        assert "❌ Configuration error:" in result.output
        assert "Field required" in result.output

    def test_cli_version(self) -> None:
        """Test CLI version option."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])

        assert result.exit_code == 0
        assert "version 0.1.0" in result.output

    def test_cli_help(self) -> None:
        """Test CLI help option."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "Sonarr Metadata Translation Layer" in result.output
        assert (
            "A long-running service that monitors Sonarr-generated .nfo files"
            in result.output
        )
