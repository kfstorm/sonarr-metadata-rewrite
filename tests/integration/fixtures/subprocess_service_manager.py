"""Subprocess service manager for integration tests."""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from tests.integration.fixtures.base_process_manager import BaseProcessManager


class SubprocessServiceManager(BaseProcessManager):
    """Manages the metadata rewrite service as a subprocess for integration testing."""

    def __init__(
        self,
        env_overrides: dict[str, str],
    ):
        """Initialize subprocess service manager.

        Args:
            env_overrides: Environment variables. Must include REWRITE_ROOT_DIR.
        """
        super().__init__()

        if "REWRITE_ROOT_DIR" not in env_overrides:
            raise ValueError("REWRITE_ROOT_DIR must be specified in env_overrides")

        self.env_overrides = env_overrides
        self.media_root = Path(env_overrides["REWRITE_ROOT_DIR"])
        self.temp_dirs: list[Path] = []

    def start(self) -> None:
        """Start the service subprocess."""
        service_name = "sonarr-metadata-rewrite"

        if service_name in self.processes:
            raise RuntimeError("Service is already running")

        # Check if user specified custom directories
        cache_dir_str = self.env_overrides.get("CACHE_DIR")
        if cache_dir_str:
            cache_dir = Path(cache_dir_str)
        else:
            cache_dir = Path(tempfile.mkdtemp(prefix="service_cache_"))
            self.temp_dirs.append(cache_dir)

        backup_dir_str = self.env_overrides.get("ORIGINAL_FILES_BACKUP_DIR")
        if backup_dir_str:
            backup_dir = Path(backup_dir_str)
        else:
            backup_dir = Path(tempfile.mkdtemp(prefix="service_backups_"))
            self.temp_dirs.append(backup_dir)

        # Prepare environment variables
        env = os.environ.copy()

        # Set defaults only for directories we created
        default_env = {}
        if "CACHE_DIR" not in self.env_overrides:
            default_env["CACHE_DIR"] = str(cache_dir)
        if "ORIGINAL_FILES_BACKUP_DIR" not in self.env_overrides:
            default_env["ORIGINAL_FILES_BACKUP_DIR"] = str(backup_dir)

        env.update(default_env)

        # Apply user-provided overrides (includes REWRITE_ROOT_DIR)
        env.update(self.env_overrides)

        # Start the service subprocess using base class
        cmd = ["uv", "run", "sonarr-metadata-rewrite"]
        print(f"Environment overrides: {self.env_overrides}")

        # Enable output streaming by default to show service logs
        self.enable_output_streaming()

        try:
            self._start_process(service_name, cmd, env)
        except Exception as e:
            self._cleanup()
            raise RuntimeError(f"Failed to start service subprocess: {e}") from e

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the service subprocess gracefully.

        Args:
            timeout: Maximum time to wait for graceful shutdown
        """
        service_name = "sonarr-metadata-rewrite"

        if service_name not in self.processes:
            return

        # Stop the service process using base class method
        self._stop_process(service_name, timeout)
        self._cleanup()

    def _cleanup(self) -> None:
        """Clean up temporary directories and resources."""
        for temp_dir in self.temp_dirs:
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Warning: Failed to cleanup {temp_dir}: {e}")

        self.temp_dirs.clear()

    def __enter__(self) -> "SubprocessServiceManager":
        return self

    def __exit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        self.stop()
