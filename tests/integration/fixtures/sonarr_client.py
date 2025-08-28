"""Sonarr API client for integration testing."""

import json
import time
from pathlib import Path
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

    def refresh_metadata(self, series_id: int) -> bool:
        """Force metadata refresh for a series to regenerate .nfo files.

        Args:
            series_id: Sonarr series ID

        Returns:
            True if metadata refresh command was accepted
        """
        command_data = {
            "name": "RefreshSeries",
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

        # Debug: Print current Kodi configuration
        print(f"Current Kodi config before update: {json.dumps(kodi_config, indent=2)}")
        
        # Enable the provider itself
        kodi_config["enable"] = True
        
        # Update the individual field values in the fields array
        for field in kodi_config.get("fields", []):
            field_name = field.get("name")
            if field_name in [
                "seriesMetadata",
                "episodeMetadata", 
                "episodeMetadataUrl",
                "episodeImages",
                "seriesImages", 
                "seasonImages",
                "seriesMetadataUrl"
            ]:
                field["value"] = True
                print(f"  Setting {field_name} = True")
        
        print(f"Updated Kodi config: {json.dumps(kodi_config, indent=2)}")

        # Update the configuration
        response = self._make_request(
            "PUT", f"/api/v3/metadata/{kodi_config['id']}", json=kodi_config
        )

        if response.is_success:
            print("Successfully enabled Kodi metadata generation")
            
            # Verify the configuration was applied
            verify_response = self._make_request("GET", "/api/v3/metadata")
            if verify_response.is_success:
                metadata_configs = verify_response.json()
                for config in metadata_configs:
                    if config.get("id") == kodi_config["id"]:
                        print(f"Verified Kodi config after update: {json.dumps(config, indent=2)}")
                        break
            
            return True
        else:
            print(f"Failed to update metadata settings: {response.status_code}")
            print(f"Response body: {response.text}")
            return False

    def refresh_series(self, series_id: int) -> bool:
        """Refresh series metadata and regenerate NFO files.

        Args:
            series_id: Sonarr series ID

        Returns:
            True if refresh command was accepted
        """
        command_data = {
            "name": "RefreshSeries",
            "seriesId": series_id,
        }

        response = self._make_request("POST", "/api/v3/command", json=command_data)
        return response.status_code in (200, 201)

    def remove_series(
        self,
        series_id: int,
        media_root: Path,
        series_slug: str,
        delete_files: bool = True,
        timeout: float = 30.0,
    ) -> bool:
        """Remove series and verify cleanup.

        Args:
            series_id: Sonarr series ID
            media_root: Root media directory path
            series_slug: Series directory slug (e.g., "breaking-bad")
            delete_files: Whether to delete media files
            timeout: Maximum time to wait for deletion

        Returns:
            True if series was removed and directory is gone

        Raises:
            RuntimeError: If series directory still exists after deletion
        """
        # Delete the series via API
        params = {"deleteFiles": str(delete_files).lower()}
        response = self._make_request(
            "DELETE", f"/api/v3/series/{series_id}", params=params
        )

        if not response.is_success:
            print(f"Failed to delete series {series_id}: HTTP {response.status_code}")
            return False

        print(f"Series {series_id} deletion command sent successfully")

        # Wait for series directory to be removed from filesystem
        series_dir = media_root / series_slug
        start_time = time.time()

        while time.time() - start_time < timeout:
            if not series_dir.exists():
                print(f"Series directory {series_dir} successfully removed")
                return True

            time.sleep(1)
            elapsed = time.time() - start_time
            if elapsed % 5 == 0:  # Log every 5 seconds
                print(
                    f"Still waiting for series directory removal... "
                    f"({elapsed:.1f}s elapsed)"
                )

        # Directory still exists after timeout
        if series_dir.exists():
            remaining_files = list(series_dir.rglob("*"))
            raise RuntimeError(
                f"Series directory {series_dir} still exists after {timeout}s. "
                f"Remaining files: {remaining_files}"
            )

        return True

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
