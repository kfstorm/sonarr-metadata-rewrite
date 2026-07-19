"""Shared HTTP client support for Arr integration fixtures."""

import time
from pathlib import Path
from typing import Any, cast

import httpx

from sonarr_metadata_rewrite.retry_utils import retry


class ArrClient:
    """Authenticated HTTP client shared by Sonarr and Radarr test fixtures."""

    service_name: str

    def __init__(self, base_url: str, api_key: str | None = None):
        """Initialize authenticated Arr API client."""
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
            return cast(bool, result)
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

    def _wait_for_queued_command(
        self,
        command_name: str,
        resource_id_field: str,
        resource_id: int,
        timeout: float = 30.0,
    ) -> None:
        """Wait for an Arr command queued automatically for one resource."""

        @retry(
            timeout=timeout,
            interval=0.5,
            log_interval=2.0,
            exceptions=(AssertionError, httpx.RequestError),
        )
        def check_command() -> None:
            response = self._make_request("GET", "/api/v3/command")
            response.raise_for_status()
            matching_commands = [
                command
                for command in response.json()
                if command.get("name", "").lower() == command_name.lower()
                and resource_id in command.get("body", {}).get(resource_id_field, [])
            ]
            assert matching_commands, (
                f"{command_name} command for {resource_id} not queued yet"
            )
            command = max(matching_commands, key=lambda item: item["id"])
            self._assert_command_completed(command)

        check_command()

    def _wait_for_command(self, command_id: int, timeout: float = 30.0) -> None:
        """Wait for one Arr command to complete successfully."""

        @retry(
            timeout=timeout,
            interval=0.5,
            log_interval=2.0,
            exceptions=(AssertionError, httpx.RequestError),
        )
        def check_command() -> None:
            response = self._make_request("GET", f"/api/v3/command/{command_id}")
            response.raise_for_status()
            self._assert_command_completed(response.json())

        check_command()

    def _configure_metadata_settings(
        self, provider_names: tuple[str, ...], field_values: dict[str, bool]
    ) -> bool:
        """Enable one metadata provider after Arr finishes registering it."""

        @retry(timeout=30.0, interval=0.5, log_interval=2.0)
        def get_provider() -> dict[str, Any]:
            response = self._make_request("GET", "/api/v3/metadata")
            response.raise_for_status()
            provider = next(
                (
                    config
                    for config in response.json()
                    if any(
                        name in config.get("name", "").lower()
                        for name in provider_names
                    )
                    and set(field_values).issubset(
                        {
                            field.get("name", "").lower()
                            for field in config.get("fields", [])
                        }
                    )
                ),
                None,
            )
            assert provider is not None, (
                f"{self.service_name} metadata providers are not initialized yet"
            )
            return cast(dict[str, Any], provider)

        provider = get_provider()
        provider["enable"] = True
        for field in provider.get("fields", []):
            field_name = field.get("name", "").lower()
            if field_name in field_values:
                field["value"] = field_values[field_name]

        response = self._make_request(
            "PUT", f"/api/v3/metadata/{provider['id']}", json=provider
        )
        return response.is_success

    def _assert_command_completed(self, command: dict[str, Any]) -> None:
        """Validate command state, retrying active commands via AssertionError."""
        status = str(command.get("status", "")).lower()
        if status == "completed":
            return
        if status in {"failed", "aborted"}:
            raise RuntimeError(
                f"{self.service_name} command {command.get('id')} ended with status "
                f"{status}: {command.get('message', '')}"
            )
        raise AssertionError(
            f"{self.service_name} command {command.get('id')} still has status "
            f"{status or 'unknown'}"
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
