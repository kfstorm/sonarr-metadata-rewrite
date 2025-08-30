"""Base process manager with shared functionality for process lifecycle."""

import subprocess
import threading
from typing import Any


class BaseProcessManager:
    """Base class for managing a single subprocess with output streaming capability."""

    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.should_stream_output = False
        self._output_thread: threading.Thread | None = None
        self._startup_event: threading.Event | None = None

    def _start_process(
        self,
        cmd: list[str],
        env: dict[str, str] | None = None,
        startup_log_pattern: str | None = None,
        startup_timeout: float = 10.0,
    ) -> subprocess.Popen[str]:
        """Start a subprocess with output capture.

        Args:
            cmd: Command and arguments to execute
            env: Environment variables for the process
            startup_log_pattern: Optional log pattern to wait for before returning
            startup_timeout: Maximum time to wait for startup pattern

        Returns:
            Started subprocess instance

        Raises:
            RuntimeError: If process fails to start or startup pattern not detected
        """
        if self.process is not None:
            raise RuntimeError("A process is already running")

        cmd_str = " ".join(cmd)
        print(f"Starting process: {cmd_str}")

        # Setup startup event if pattern provided
        if startup_log_pattern:
            self._startup_event = threading.Event()

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                bufsize=1,
                universal_newlines=True,
            )
            self._start_output_streaming(self.process, startup_log_pattern)

            # Wait for startup pattern if specified
            if self._startup_event and startup_log_pattern:
                print(f"Waiting for startup pattern: '{startup_log_pattern}'...")
                if not self._startup_event.wait(startup_timeout):
                    # Cleanup process on timeout
                    self._terminate_process(self.process)
                    self.process = None
                    self._startup_event = None
                    raise RuntimeError(
                        f"Startup timeout: Pattern '{startup_log_pattern}' not found "
                        f"in {startup_timeout}s"
                    )
                print("Startup pattern detected!")

            return self.process

        except Exception as e:
            error_msg = f"Process start failed:\nCommand: {cmd_str}\nError: {e}"
            raise RuntimeError(error_msg) from e

    def _start_output_streaming(
        self, process: subprocess.Popen[str], startup_log_pattern: str | None = None
    ) -> None:
        """Start output streaming thread for the process.

        Args:
            process: Process instance to stream from
            startup_log_pattern: Optional pattern to detect for startup completion
        """

        def stream_output() -> None:
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    if line:
                        line_stripped = line.rstrip()
                        if self.should_stream_output:
                            print(f"[process] {line_stripped}")

                        # Check for startup pattern
                        if (
                            startup_log_pattern
                            and self._startup_event
                            and not self._startup_event.is_set()
                        ):
                            if startup_log_pattern in line_stripped:
                                self._startup_event.set()

                process.stdout.close()

        self._output_thread = threading.Thread(target=stream_output, daemon=True)
        self._output_thread.start()

    def enable_output_streaming(self) -> None:
        """Enable output streaming for all managed processes."""
        self.should_stream_output = True

    def _terminate_process(
        self, process: subprocess.Popen[str], timeout: float = 5.0
    ) -> None:
        """Terminate a process gracefully, then forcefully if needed.

        Args:
            process: Process to terminate
            timeout: Time to wait for graceful termination before killing
        """
        try:
            process.terminate()
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        except Exception:
            process.kill()
            process.wait()

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the process gracefully.

        Args:
            timeout: Maximum time to wait for graceful shutdown
        """
        if not self.process:
            return

        print("Stopping process...")

        # Send SIGTERM for graceful shutdown
        self._terminate_process(self.process, timeout)
        print("Process stopped")

        # Clean up references
        self.process = None
        self._output_thread = None
        self._startup_event = None

    def _cleanup(self) -> None:
        """Clean up the process and resources."""
        self.stop()
        self.process = None
        self._output_thread = None
        self._startup_event = None

    def __enter__(self) -> "BaseProcessManager":
        return self

    def __exit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        self._cleanup()
