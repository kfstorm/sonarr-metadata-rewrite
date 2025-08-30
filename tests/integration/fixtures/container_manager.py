"""Simple container orchestrator agnostic container management."""

import subprocess
from typing import Any

from tests.integration.fixtures.base_process_manager import BaseProcessManager


class ContainerManager(BaseProcessManager):
    """Simple container manager that works with podman, docker, or any OCI runtime."""

    def __init__(self) -> None:
        super().__init__()
        self.runtime = self._detect_runtime()
        self.container_name: str | None = None

    def _detect_runtime(self) -> str:
        """Detect available container runtime."""
        for runtime in ["podman", "docker"]:
            try:
                subprocess.run(
                    [runtime, "--version"], capture_output=True, check=True, timeout=5
                )
                return runtime
            except (
                subprocess.CalledProcessError,
                FileNotFoundError,
                subprocess.TimeoutExpired,
            ):
                continue
        raise RuntimeError("No container runtime found. Install podman or docker.")

    def run_container(
        self,
        image: str,
        name: str,
        ports: dict[int, int] | None = None,
        volumes: dict[str, str] | None = None,
        environment: dict[str, str] | None = None,
        extra_args: list[str] | None = None,
    ) -> None:
        """Run a container in foreground mode with output streaming.

        Args:
            image: Container image to run
            name: Container name
            ports: Port mapping {container_port: host_port}
            volumes: Volume mapping {host_path: container_path}
            environment: Environment variables
            extra_args: Additional arguments to pass to container run
        """
        if self.process is not None:
            raise RuntimeError("A container is already running")
        cmd = [self.runtime, "run", "--rm", "--name", name]

        # Add port mappings
        if ports:
            for container_port, host_port in ports.items():
                cmd.extend(["-p", f"{host_port}:{container_port}"])

        # Add volume mounts
        if volumes:
            for host_path, container_path in volumes.items():
                cmd.extend(["-v", f"{host_path}:{container_path}"])

        # Add environment variables
        if environment:
            for key, value in environment.items():
                cmd.extend(["-e", f"{key}={value}"])

        # Add extra arguments
        if extra_args:
            cmd.extend(extra_args)

        cmd.append(image)

        # Start the container process using base class
        self._start_process(cmd)
        self.container_name = name

    def start_streaming(self) -> None:
        """Start output streaming for the container."""
        if self.process is None:
            raise ValueError("No container is running")

        self.enable_output_streaming()

    def cleanup(self) -> None:
        """Stop and remove the managed container."""
        # Stop the process using base class method
        self.stop()

        # Force remove any remaining container
        if self.container_name:
            try:
                subprocess.run(
                    [self.runtime, "rm", "-f", self.container_name],
                    capture_output=True,
                    timeout=10,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass

        self.container_name = None

    def __enter__(self) -> "ContainerManager":
        return self

    def __exit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        self.cleanup()
