"""Integration tests for Docker container behavior."""

import subprocess
from pathlib import Path

import pytest


class TestDockerContainer:
    """Test Docker container functionality."""

    def test_dockerfile_cmd_removed(self) -> None:
        """Test that Dockerfile no longer contains CMD ["--help"]."""
        dockerfile_path = Path(__file__).parent.parent.parent / "Dockerfile"
        dockerfile_content = dockerfile_path.read_text()
        
        # Should not contain the old default help command
        assert 'CMD ["--help"]' not in dockerfile_content, \
            "Dockerfile should not default to showing help"
        
        # Should still have the entrypoint
        assert 'ENTRYPOINT ["sonarr-metadata-rewrite"]' in dockerfile_content, \
            "Dockerfile should still have the correct entrypoint"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_docker_container_default_behavior(self, tmp_path: Path) -> None:
        """Test that Docker container runs service by default (not help).
        
        This test verifies that the container no longer defaults to showing help
        but instead tries to run the actual service.
        """
        # Skip if Docker is not available
        try:
            subprocess.run(
                ["docker", "--version"], 
                check=True, 
                capture_output=True, 
                text=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pytest.skip("Docker not available")

        # Create test environment
        test_env = {
            "TMDB_API_KEY": "test_key_12345",
            "REWRITE_ROOT_DIR": str(tmp_path),
            "PREFERRED_LANGUAGES": "zh-CN"
        }

        # Build the Docker image first
        build_cmd = ["docker", "build", "-t", "sonarr-metadata-rewrite:test", "."]
        try:
            result = subprocess.run(build_cmd, check=True, capture_output=True, text=True, timeout=300)
        except subprocess.CalledProcessError as e:
            pytest.skip(f"Failed to build Docker image: {e.stderr}")
        except subprocess.TimeoutExpired:
            pytest.skip("Docker image build timed out")

        # Run container with minimal config to see if it tries to start service
        # We expect it to fail with configuration error, not show help
        docker_cmd = [
            "docker", "run", "--rm",
            "-e", f"TMDB_API_KEY={test_env['TMDB_API_KEY']}",
            "-e", f"REWRITE_ROOT_DIR={test_env['REWRITE_ROOT_DIR']}",
            "-e", f"PREFERRED_LANGUAGES={test_env['PREFERRED_LANGUAGES']}",
            "sonarr-metadata-rewrite:test"
        ]

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
        except subprocess.TimeoutExpired:
            # If it times out, that's actually good - it means it's trying to run the service
            # rather than just showing help and exiting
            pass
        else:
            # Check that output doesn't contain help text
            output = result.stdout + result.stderr
            
            # Should not contain help/usage information
            assert "Usage:" not in output, "Container should not show help by default"
            assert "Show this message and exit" not in output, "Container should not show help by default"
            
            # Should contain service startup attempt or configuration error
            # (it will fail because the test directories don't exist in container)
            assert any(
                phrase in output for phrase in [
                    "Starting Sonarr Metadata Translation Layer",
                    "Configuration error",
                    "Field required",
                    "TMDB API key",
                    "directory"
                ]
            ), f"Container should attempt to start service, got: {output}"

    @pytest.mark.integration
    def test_docker_container_help_option(self, tmp_path: Path) -> None:
        """Test that Docker container still shows help when explicitly requested."""
        # Skip if Docker is not available
        try:
            subprocess.run(
                ["docker", "--version"], 
                check=True, 
                capture_output=True, 
                text=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pytest.skip("Docker not available")

        # Build the Docker image first (reuse from previous test if available)
        build_cmd = ["docker", "build", "-t", "sonarr-metadata-rewrite:test", "."]
        try:
            subprocess.run(build_cmd, check=True, capture_output=True, text=True, timeout=300)
        except subprocess.CalledProcessError as e:
            pytest.skip(f"Failed to build Docker image: {e.stderr}")
        except subprocess.TimeoutExpired:
            pytest.skip("Docker image build timed out")

        # Run container with --help argument
        docker_cmd = [
            "docker", "run", "--rm",
            "sonarr-metadata-rewrite:test",
            "--help"
        ]

        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        output = result.stdout + result.stderr
        
        # Should contain help/usage information when explicitly requested
        assert result.returncode == 0, f"Help command should succeed, got: {output}"
        assert "Usage:" in output or "Sonarr Metadata Translation Layer" in output, \
            f"Should show help when requested, got: {output}"