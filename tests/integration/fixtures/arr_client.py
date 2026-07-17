"""Shared HTTP client support for Arr integration fixtures."""

from typing import Any

import httpx


class ArrClient:
    """Authenticated HTTP client shared by Sonarr and Radarr test fixtures."""

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

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
