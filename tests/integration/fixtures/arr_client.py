"""Shared HTTP client support for Arr integration fixtures."""

import time
from pathlib import Path
from typing import Any

import httpx

from sonarr_metadata_rewrite.retry_utils import retry


class ArrClient:
    """Authenticated HTTP client shared by Sonarr and Radarr test fixtures."""

    service_name: str

    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.Client(timeout=30.0)

    def _make_request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> httpx.Response:
        """Make a request with the configured API key."""
        if self.api_key:
            params = kwargs.setdefault("params", {})
            params["apikey"] = self.api_key
        return self.client.request(method, f"{self.base_url}{endpoint}", **kwargs)

    def wait_for_ready(self, max_attempts: int = 30, delay: float = 1.0) -> bool:
        """Wait for Arr API readiness."""
        timeout_sec = max_attempts * delay
        print(
            f"Waiting for {self.service_name} at {self.base_url} "
            f"(max {timeout_sec:.1f}s timeout)"
        )

        @retry(
            timeout=timeout_sec,
            interval=delay,
            log_interval=5.0,
            exceptions=(httpx.RequestError, httpx.HTTPStatusError),
        )
        def check_status() -> bool:
            response = self._make_request("GET", "/api/v3/system/status", timeout=5.0)
            response.raise_for_status()
            return True

        try:
            result = check_status()
            print(f"{self.service_name} is ready")
            return result
        except Exception as exc:
            print(f"{self.service_name} failed to become ready: {exc}")
            return False

    def _wait_for_directory_removal(
        self, directory: Path, resource_name: str, timeout: float
    ) -> bool:
        """Wait for Arr to remove a resource directory."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not directory.exists():
                return True
            time.sleep(1)
            elapsed = time.time() - start_time
            if elapsed % 5 == 0:
                print(
                    f"Still waiting for {resource_name.lower()} directory removal... "
                    f"({elapsed:.1f}s elapsed)"
                )

        if directory.exists():
            remaining_files = list(directory.rglob("*"))
            raise RuntimeError(
                f"{resource_name} directory {directory} still exists after {timeout}s. "
                f"Remaining files: {remaining_files}"
            )
        return True

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
