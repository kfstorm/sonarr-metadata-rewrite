"""Docker service manager for integration tests."""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


class DockerServiceManager:
    """Manages the metadata rewrite service as a Docker container for integration testing."""

    def __init__(
        self,
        env_overrides: dict[str, str],
        image_tag: str = "sonarr-metadata-rewrite:test",
    ):
        """Initialize Docker service manager.

        Args:
            env_overrides: Environment variables. Must include REWRITE_ROOT_DIR.
            image_tag: Docker image tag to use
        """
        if "REWRITE_ROOT_DIR" not in env_overrides:
            raise ValueError("REWRITE_ROOT_DIR must be specified in env_overrides")

        self.env_overrides = env_overrides
        self.media_root = Path(env_overrides["REWRITE_ROOT_DIR"])
        self.image_tag = image_tag

        self.container_id: str | None = None
        self.temp_dirs: list[Path] = []

    def start(self, timeout: float = 10.0) -> None:
        """Start the service Docker container.

        Args:
            timeout: Maximum time to wait for service startup
        """
        # Check if Docker tests should be skipped
        if os.environ.get("SKIP_DOCKER_TESTS"):
            raise RuntimeError("Docker tests are disabled due to build failure")
            
        if self.container_id is not None:
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

        # Prepare environment variables for container
        env_vars = {}

        # Set defaults only for directories we created
        if "CACHE_DIR" not in self.env_overrides:
            env_vars["CACHE_DIR"] = "/app/cache"
        if "ORIGINAL_FILES_BACKUP_DIR" not in self.env_overrides:
            env_vars["ORIGINAL_FILES_BACKUP_DIR"] = "/app/backups"

        # Apply user-provided overrides (but map REWRITE_ROOT_DIR to container path)
        for key, value in self.env_overrides.items():
            if key == "REWRITE_ROOT_DIR":
                env_vars[key] = "/app/data"
            else:
                env_vars[key] = value

        # Build Docker run command
        cmd = [
            "docker", "run", 
            "--rm", 
            "-d",  # Run in detached mode
            "--name", f"test-service-{int(time.time())}",
        ]

        # Add environment variables
        for key, value in env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Add volume mounts
        cmd.extend(["-v", f"{self.media_root}:/app/data:rw"])
        
        if "CACHE_DIR" not in self.env_overrides:
            cmd.extend(["-v", f"{cache_dir}:/app/cache:rw"])
        if "ORIGINAL_FILES_BACKUP_DIR" not in self.env_overrides:
            cmd.extend(["-v", f"{backup_dir}:/app/backups:rw"])

        # Add image tag
        cmd.append(self.image_tag)

        print(f"Starting service Docker container: {' '.join(cmd)}")
        print(f"Environment overrides: {self.env_overrides}")

        try:
            # Start the container
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            
            self.container_id = result.stdout.strip()
            print(f"Container started with ID: {self.container_id}")

            # Wait for service to start successfully
            self._wait_for_startup(timeout)
            print("Service Docker container started successfully")

        except subprocess.CalledProcessError as e:
            self._cleanup()
            raise RuntimeError(f"Failed to start service Docker container: {e.stderr}") from e
        except Exception as e:
            self._cleanup()
            raise RuntimeError(f"Failed to start service Docker container: {e}") from e

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the service Docker container gracefully.

        Args:
            timeout: Maximum time to wait for graceful shutdown
        """
        if self.container_id is None:
            return

        print("Stopping service Docker container...")

        try:
            # Stop the container gracefully
            subprocess.run(
                ["docker", "stop", self.container_id],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
            print("Service Docker container stopped gracefully")

        except subprocess.TimeoutExpired:
            print("Graceful shutdown timeout, forcing kill...")
            try:
                subprocess.run(
                    ["docker", "kill", self.container_id],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                print("Service Docker container killed")
            except subprocess.CalledProcessError as e:
                print(f"Error killing container: {e}")

        except subprocess.CalledProcessError as e:
            print(f"Error stopping container: {e}")

        finally:
            self.container_id = None
            self._cleanup()

    def is_running(self) -> bool:
        """Check if the service Docker container is still running."""
        if self.container_id is None:
            return False

        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "--filter", f"id={self.container_id}"],
                capture_output=True,
                text=True,
                check=True,
            )
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False

    def _wait_for_startup(self, timeout: float) -> None:
        """Wait for service to start up successfully.

        Args:
            timeout: Maximum time to wait for startup
        """
        start_time = time.time()
        startup_success = False

        while time.time() - start_time < timeout:
            if self.container_id is None:
                break

            # Check if container is still running
            if not self.is_running():
                # Container has exited, get logs
                try:
                    result = subprocess.run(
                        ["docker", "logs", self.container_id],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    error_output = result.stdout + result.stderr
                except subprocess.CalledProcessError:
                    error_output = "Failed to get container logs"
                
                raise RuntimeError(
                    f"Service Docker container exited during startup: {error_output}"
                )

            # Check for startup success indicators in container logs
            try:
                result = subprocess.run(
                    ["docker", "logs", "--tail", "10", self.container_id],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                logs = result.stdout + result.stderr
                
                if logs:
                    for line in logs.splitlines():
                        print(f"[container] {line}")
                        if "Service started successfully" in line:
                            startup_success = True
                            break
                
                if startup_success:
                    break
                    
            except subprocess.CalledProcessError:
                pass

            time.sleep(0.1)

        if not startup_success:
            raise RuntimeError("Service Docker container failed to start within timeout")

    def _cleanup(self) -> None:
        """Clean up temporary directories and resources."""
        for temp_dir in self.temp_dirs:
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Warning: Failed to cleanup {temp_dir}: {e}")

        self.temp_dirs.clear()

    def __enter__(self) -> "DockerServiceManager":
        return self

    def __exit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        self.stop()