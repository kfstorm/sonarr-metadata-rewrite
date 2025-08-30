"""Unit tests for main CLI module."""

import os
import re
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
            env_vars = {
                "TMDB_API_KEY": test_key,
                "REWRITE_ROOT_DIR": "/tmp/test",
                "PREFERRED_LANGUAGES": "zh-CN",
            }
            with patch.dict(os.environ, env_vars):
                # Mock the service to avoid actually starting it
                with patch(
                    "sonarr_metadata_rewrite.main.RewriteService"
                ) as mock_service:
                    mock_service.return_value.is_running.return_value = False
                    result = runner.invoke(cli)

            # Check the initial output
            assert "🚀 Starting Sonarr Metadata Rewrite..." in result.output
            assert (
                f"✅ TMDB API key loaded (ending in ...{test_key[-4:]})"
                in result.output
            )
            assert "🔧 Service mode: rewrite" in result.output

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
        assert "version" in result.output
        # Version format should be semantic version or dev version

        # Check for either semantic version (x.y.z) or development version
        version_patterns = [
            r"version \d+\.\d+\.\d+",  # Semantic version like "version 1.0.2"
            r"dev",  # Development version
            r"\+g[0-9a-f]+",  # Git commit hash in version
        ]
        assert any(
            re.search(pattern, result.output) for pattern in version_patterns
        ), f"Version output '{result.output.strip()}' doesn't match expected patterns"

    def test_cli_help(self) -> None:
        """Test CLI help option."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "Sonarr Metadata Rewrite" in result.output
        assert (
            "A long-running service that monitors Sonarr-generated .nfo files"
            in result.output
        )
        assert "In rollback mode, restores original files" in result.output

    def test_cli_rollback_mode_success(self) -> None:
        """Test CLI in rollback mode with successful execution."""
        test_key = "test_api_key_1234567890abcdef"
        runner = CliRunner()

        with runner.isolated_filesystem():
            env_vars = {
                "TMDB_API_KEY": test_key,
                "REWRITE_ROOT_DIR": "/tmp/test",
                "PREFERRED_LANGUAGES": "zh-CN",
                "SERVICE_MODE": "rollback",
            }
            with patch.dict(os.environ, env_vars):
                # Mock the rollback service
                with patch(
                    "sonarr_metadata_rewrite.main.RollbackService"
                ) as mock_rollback_service:
                    mock_instance = mock_rollback_service.return_value
                    mock_instance.execute_rollback.return_value = None
                    mock_instance.hang_after_completion.side_effect = (
                        KeyboardInterrupt()
                    )

                    result = runner.invoke(cli)

            # Check the output
            assert "🚀 Starting Sonarr Metadata Rewrite..." in result.output
            assert "🔧 Service mode: rollback" in result.output
            assert "🔄 Executing rollback operation..." in result.output
            assert "✅ Rollback completed successfully" in result.output
            assert result.exit_code == 0

    def test_cli_rollback_mode_failure(self) -> None:
        """Test CLI in rollback mode with execution failure."""
        test_key = "test_api_key_1234567890abcdef"
        runner = CliRunner()

        with runner.isolated_filesystem():
            env_vars = {
                "TMDB_API_KEY": test_key,
                "REWRITE_ROOT_DIR": "/tmp/test",
                "PREFERRED_LANGUAGES": "zh-CN",
                "SERVICE_MODE": "rollback",
            }
            with patch.dict(os.environ, env_vars):
                # Mock the rollback service to fail
                with patch(
                    "sonarr_metadata_rewrite.main.RollbackService"
                ) as mock_rollback_service:
                    mock_instance = mock_rollback_service.return_value
                    mock_instance.execute_rollback.side_effect = ValueError(
                        "Backup directory not configured"
                    )

                    result = runner.invoke(cli)

            # Check the output
            assert "🚀 Starting Sonarr Metadata Rewrite..." in result.output
            assert "🔧 Service mode: rollback" in result.output
            assert "🔄 Executing rollback operation..." in result.output
            assert (
                "❌ Rollback failed: Backup directory not configured" in result.output
            )
            assert result.exit_code == 1
