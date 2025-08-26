"""Sonarr API client for integration testing."""

import time
from typing import Any

import httpx


class SonarrClient:
    """Simple Sonarr API client for integration tests."""

    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.Client(timeout=30.0)

    def wait_for_ready(self, max_attempts: int = 30, delay: float = 1.0) -> bool:
        """Wait for Sonarr to be ready and responding."""
        print(
            f"Waiting for Sonarr at {self.base_url} "
            f"(max {max_attempts} attempts, {delay}s delay)"
        )
        for attempt in range(max_attempts):
            try:
                # Use API key if we have one
                params = {}
                if self.api_key:
                    params["apikey"] = self.api_key

                response = self.client.get(
                    f"{self.base_url}/api/v3/system/status", params=params, timeout=5.0
                )
                if response.status_code == 200:
                    print(f"Sonarr ready after {attempt + 1} attempts")
                    return True
                else:
                    print(f"Attempt {attempt + 1}: HTTP {response.status_code}")
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                print(f"Attempt {attempt + 1}: {type(e).__name__}: {e}")
            time.sleep(delay)
        print(f"Sonarr failed to become ready after {max_attempts} attempts")
        return False

    def _make_request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> httpx.Response:
        """Make authenticated request to Sonarr API."""
        url = f"{self.base_url}{endpoint}"

        # Add API key if we have one
        if self.api_key:
            if "params" not in kwargs:
                kwargs["params"] = {}
            kwargs["params"]["apikey"] = self.api_key

        return self.client.request(method, url, **kwargs)

    def add_series(
        self,
        tvdb_id: int,
        root_folder: str = "/tv",
        quality_profile_id: int = 1,
    ) -> dict[str, Any]:
        """Add a TV series to Sonarr.

        Args:
            tvdb_id: TVDB series ID
            title: Series title
            root_folder: Root folder path (default: /tv)
            quality_profile_id: Quality profile ID (default: 1)

        Returns:
            Series data from Sonarr API
        """
        # First, lookup the series from TVDB
        params = {"term": f"tvdb:{tvdb_id}"}
        response = self._make_request("GET", "/api/v3/series/lookup", params=params)
        response.raise_for_status()

        lookup_results = response.json()
        if not lookup_results:
            raise ValueError(f"No series found for TVDB ID: {tvdb_id}")

        series_data = lookup_results[0]

        # Add the series
        add_data = {
            "title": series_data["title"],
            "sortTitle": series_data.get("sortTitle", series_data["title"]),
            "seasonFolder": True,
            "monitored": True,
            "tvdbId": tvdb_id,
            "titleSlug": series_data["titleSlug"],
            "images": series_data.get("images", []),
            "seasons": series_data.get("seasons", []),
            "path": f"{root_folder}/{series_data['titleSlug']}",
            "qualityProfileId": quality_profile_id,
            "languageProfileId": 1,
            "seriesType": "standard",
            "useSceneNumbering": False,
            "tags": [],
        }

        response = self._make_request("POST", "/api/v3/series", json=add_data)
        response.raise_for_status()
        return response.json()

    def trigger_disk_scan(self, series_id: int) -> bool:
        """Trigger a disk scan for episode files.

        Args:
            series_id: Sonarr series ID

        Returns:
            True if disk scan command was accepted
        """
        command_data = {
            "name": "RescanSeries",
            "seriesId": series_id,
        }

        response = self._make_request("POST", "/api/v3/command", json=command_data)
        return response.status_code in (200, 201)

    def configure_metadata_settings(self) -> bool:
        """Configure Sonarr to enable NFO metadata generation.

        Returns:
            True if configuration was successful
        """
        # Get existing metadata settings
        response = self._make_request("GET", "/api/v3/metadata")
        if not response.is_success:
            print(f"Failed to get metadata settings: {response.status_code}")
            return False

        metadata_configs = response.json()
        print(f"Found {len(metadata_configs)} metadata configurations")

        # Print all available providers for debugging
        for config in metadata_configs:
            name = config.get("name", "Unknown")
            enabled = config.get("enable", False)
            print(f"  - {name}: enabled={enabled}")

        # Look for Kodi/XBMC metadata provider and enable it
        kodi_config = None
        for config in metadata_configs:
            config_name = config.get("name", "").lower()
            if any(name in config_name for name in ["kodi", "xbmc"]):
                kodi_config = config
                break

        if not kodi_config:
            raise ValueError("No Kodi/XBMC metadata provider found")

        print(f"Found Kodi metadata config: {kodi_config['name']}")

        # Enable all metadata types for Kodi
        kodi_config.update(
            {
                "enable": True,
                "seriesMetadata": True,
                "episodeMetadata": True,
                "episodeImages": True,
                "seriesImages": True,
                "seasonImages": True,
            }
        )

        # Update the configuration
        response = self._make_request(
            "PUT", f"/api/v3/metadata/{kodi_config['id']}", json=kodi_config
        )

        if response.is_success:
            print("Successfully enabled Kodi metadata generation")
            return True
        else:
            print(f"Failed to update metadata settings: {response.status_code}")
            return False

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
