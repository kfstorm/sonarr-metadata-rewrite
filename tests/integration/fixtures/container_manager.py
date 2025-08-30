"""Simple container orchestrator agnostic container management."""

import subprocess
from typing import Any

from tests.integration.fixtures.base_process_manager import BaseProcessManager


class ContainerManager(BaseProcessManager):
    """Simple container manager that works with podman, docker, or any OCI runtime."""

    def __init__(self) -> None:
        super().__init__()
        self.runtime = self._detect_runtime()
        self.containers: list[str] = []

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
        self._start_process(name, cmd)
        self.containers.append(name)

    def start_streaming(self, name: str) -> None:
        """Start output streaming for a specific container."""
        if name not in self.processes:
            raise ValueError(f"Container {name} not found")

        self.enable_output_streaming()

    def cleanup(self) -> None:
        """Stop and remove all managed containers."""
        # Stop all processes using base class method
        self._stop_all_processes()

        # Force remove any remaining containers
        for name in self.containers:
            try:
                subprocess.run(
                    [self.runtime, "rm", "-f", name], capture_output=True, timeout=10
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass

        self.containers.clear()

    def __enter__(self) -> "ContainerManager":
        return self

    def __exit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        self.cleanup()
