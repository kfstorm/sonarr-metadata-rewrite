"""Simple container orchestrator agnostic container management."""

import subprocess
import threading
from typing import Any


class ContainerManager:
    """Simple container manager that works with podman, docker, or any OCI runtime."""

    def __init__(self) -> None:
        self.runtime = self._detect_runtime()
        self.containers: list[str] = []
        self.processes: dict[str, subprocess.Popen[str]] = {}

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

        # Log the complete command before execution
        cmd_str = " ".join(cmd)
        print(f"Running container command: {cmd_str}")

        # Run container in foreground mode with output streaming
        try:
            print(f"Starting container: {name}")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
            self.processes[name] = process
            self.containers.append(name)

            # Start thread to stream output
            def stream_output() -> None:
                if process.stdout:
                    for line in iter(process.stdout.readline, ""):
                        if line:
                            print(f"[{name}] {line.rstrip()}")
                    process.stdout.close()

            thread = threading.Thread(target=stream_output, daemon=True)
            thread.start()

        except Exception as e:
            error_msg = f"Container run failed:\nCommand: {cmd_str}\nError: {e}"
            raise RuntimeError(error_msg) from e

    def cleanup(self) -> None:
        """Stop and remove all managed containers."""
        # Terminate all processes
        for _name, process in self.processes.items():
            try:
                process.terminate()
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        # Force remove any remaining containers
        for name in self.containers:
            try:
                subprocess.run(
                    [self.runtime, "rm", "-f", name], capture_output=True, timeout=10
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass

        self.containers.clear()
        self.processes.clear()

    def __enter__(self) -> "ContainerManager":
        return self

    def __exit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        self.cleanup()
