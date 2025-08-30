"""Base process manager with shared functionality for process lifecycle."""

import subprocess
import threading
from typing import Any


class BaseProcessManager:
    """Base class for managing subprocesses with output streaming capability."""

    def __init__(self) -> None:
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.should_stream_output = False
        self._output_threads: dict[str, threading.Thread] = {}

    def _start_process(
        self,
        name: str,
        cmd: list[str],
        env: dict[str, str] | None = None,
    ) -> subprocess.Popen[str]:
        """Start a subprocess with output capture.

        Args:
            name: Unique name for the process
            cmd: Command and arguments to execute
            env: Environment variables for the process

        Returns:
            Started subprocess instance

        Raises:
            RuntimeError: If process fails to start
        """
        if name in self.processes:
            raise RuntimeError(f"Process '{name}' is already running")

        cmd_str = " ".join(cmd)
        print(f"Starting process '{name}': {cmd_str}")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                bufsize=1,
                universal_newlines=True,
            )
            self.processes[name] = process
            self._start_output_streaming(name, process)
            return process

        except Exception as e:
            error_msg = f"Process start failed:\nCommand: {cmd_str}\nError: {e}"
            raise RuntimeError(error_msg) from e

    def _start_output_streaming(
        self, name: str, process: subprocess.Popen[str]
    ) -> None:
        """Start output streaming thread for a process.

        Args:
            name: Process name for logging
            process: Process instance to stream from
        """

        def stream_output() -> None:
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    if line and self.should_stream_output:
                        print(f"[{name}] {line.rstrip()}")
                process.stdout.close()

        thread = threading.Thread(target=stream_output, daemon=True)
        thread.start()
        self._output_threads[name] = thread

    def enable_output_streaming(self) -> None:
        """Enable output streaming for all managed processes."""
        self.should_stream_output = True

    def _stop_process(self, name: str, timeout: float = 10.0) -> None:
        """Stop a specific process gracefully.

        Args:
            name: Name of process to stop
            timeout: Maximum time to wait for graceful shutdown
        """
        process = self.processes.get(name)
        if not process:
            return

        print(f"Stopping process '{name}'...")

        try:
            # Send SIGTERM for graceful shutdown
            process.terminate()

            # Wait for graceful shutdown
            try:
                process.wait(timeout=timeout)
                print(f"Process '{name}' stopped gracefully")
            except subprocess.TimeoutExpired:
                print(f"Graceful shutdown timeout for '{name}', forcing kill...")
                process.kill()
                process.wait()
                print(f"Process '{name}' killed")

        except Exception as e:
            print(f"Error stopping process '{name}': {e}")
            try:
                process.kill()
                process.wait()
            except Exception:
                pass

        # Clean up references
        self.processes.pop(name, None)
        self._output_threads.pop(name, None)

    def _stop_all_processes(self, timeout: float = 10.0) -> None:
        """Stop all managed processes.

        Args:
            timeout: Maximum time to wait for each process shutdown
        """
        process_names = list(self.processes.keys())
        for name in process_names:
            self._stop_process(name, timeout)

    def _cleanup(self) -> None:
        """Clean up all processes and resources."""
        self._stop_all_processes()
        self.processes.clear()
        self._output_threads.clear()

    def __enter__(self) -> "BaseProcessManager":
        return self

    def __exit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        self._cleanup()
