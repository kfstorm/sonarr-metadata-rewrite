"""Subprocess service manager for integration tests."""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


class SubprocessServiceManager:
    """Manages the metadata rewrite service as a subprocess for integration testing."""

    def __init__(
        self,
        env_overrides: dict[str, str],
    ):
        """Initialize subprocess service manager.

        Args:
            env_overrides: Environment variables. Must include REWRITE_ROOT_DIR.
        """
        if "REWRITE_ROOT_DIR" not in env_overrides:
            raise ValueError("REWRITE_ROOT_DIR must be specified in env_overrides")

        self.env_overrides = env_overrides
        self.media_root = Path(env_overrides["REWRITE_ROOT_DIR"])

        self.process: subprocess.Popen[str] | None = None
        self.temp_dirs: list[Path] = []

    def start(self, timeout: float = 10.0) -> None:
        """Start the service subprocess.

        Args:
            timeout: Maximum time to wait for service startup
        """
        if self.process is not None:
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

        # Start the service subprocess
        cmd = ["uv", "run", "sonarr-metadata"]
        print(f"Starting service subprocess: {' '.join(cmd)}")
        print(f"Environment overrides: {self.env_overrides}")

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                cwd=Path.cwd(),
                bufsize=1,
                universal_newlines=True,
            )

            # Wait for service to start successfully
            self._wait_for_startup(timeout)
            print("Service subprocess started successfully")

        except Exception as e:
            self._cleanup()
            raise RuntimeError(f"Failed to start service subprocess: {e}") from e

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the service subprocess gracefully.

        Args:
            timeout: Maximum time to wait for graceful shutdown
        """
        if self.process is None:
            return

        print("Stopping service subprocess...")

        try:
            # Send SIGTERM for graceful shutdown
            self.process.terminate()

            # Wait for graceful shutdown
            try:
                self.process.wait(timeout=timeout)
                print("Service subprocess stopped gracefully")
            except subprocess.TimeoutExpired:
                print("Graceful shutdown timeout, forcing kill...")
                self.process.kill()
                self.process.wait()
                print("Service subprocess killed")

        except Exception as e:
            print(f"Error stopping subprocess: {e}")
            try:
                self.process.kill()
                self.process.wait()
            except Exception:
                pass

        finally:
            self.process = None
            self._cleanup()

    def is_running(self) -> bool:
        """Check if the service subprocess is still running."""
        return self.process is not None and self.process.poll() is None

    def _wait_for_startup(self, timeout: float) -> None:
        """Wait for service to start up successfully.

        Args:
            timeout: Maximum time to wait for startup
        """
        start_time = time.time()
        startup_success = False

        while time.time() - start_time < timeout:
            if self.process is None:
                break

            # Check if process is still running
            if self.process.poll() is not None:
                # Process has exited
                stdout, stderr = self.process.communicate()
                error_output = (
                    f"stdout: {stdout}\nstderr: {stderr}" if stderr else stdout
                )
                raise RuntimeError(
                    f"Service subprocess exited during startup: {error_output}"
                )

            # Check for startup success indicators in logs
            try:
                if self.process.stdout:
                    line = self.process.stdout.readline()
                    if line:
                        print(f"[service] {line.rstrip()}")
                        if "Service started successfully" in line:
                            startup_success = True
                            break
            except Exception:
                pass

            time.sleep(0.1)

        if not startup_success:
            raise RuntimeError("Service subprocess failed to start within timeout")

    def _cleanup(self) -> None:
        """Clean up temporary directories and resources."""
        import shutil

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
