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

    def refresh_series(self, series_id: int) -> bool:
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

    def manual_import(self, series_id: int, files: list[str]) -> bool:
        """Manually import episode files into Sonarr using proper manual import API.

        Args:
            series_id: Sonarr series ID
            files: List of file paths to import

        Returns:
            True if manual import was successful
        """
        print(f"Starting manual import for series {series_id}")
        
        # First, get the series to obtain quality profile and language profile
        response = self._make_request("GET", f"/api/v3/series/{series_id}")
        if not response.is_success:
            print(f"Failed to get series {series_id}: {response.status_code}")
            return False

        series_data = response.json()
        quality_profile_id = series_data.get("qualityProfileId", 1)
        language_profile_id = series_data.get("languageProfileId", 1)
        series_path = series_data.get("path", "")

        # For each file, check which directory to scan
        scanned_folders = set()
        all_import_items = []
        
        for file_path in files:
            file_obj = Path(file_path)
            folder_to_scan = str(file_obj.parent)
            
            if folder_to_scan not in scanned_folders:
                # Step 1: Scan the folder to get potential import decisions
                params = {
                    "folder": folder_to_scan,
                    "filterExistingFiles": "true",
                    "replaceExistingFiles": "false",
                }
                
                response = self._make_request("GET", "/api/v3/manualimport", params=params)
                if not response.is_success:
                    print(f"Failed to scan folder for manual import: {response.status_code}")
                    print(f"Response: {response.text}")
                    continue

                potential_imports = response.json()
                
                # Step 2: Filter for the files we want to import from this folder
                for item in potential_imports:
                    item_path = item.get("path", "")
                    item_name = Path(item_path).name
                    
                    # Check if this item matches any of our target files
                    if any(Path(f).name == item_name for f in files):
                        # Check for rejections that would prevent import
                        rejections = item.get("rejections", [])
                        permanent_rejections = [r for r in rejections if r.get("type") == "permanent"]
                        
                        if permanent_rejections:
                            print(f"Item has permanent rejections: {permanent_rejections}")
                            # Skip items with permanent rejections that we can't handle
                            continue
                        
                        all_import_items.append(item)
                
                scanned_folders.add(folder_to_scan)

        if not all_import_items:
            print("No matching files found in scan results or all had permanent rejections")
            return False

        # Step 3: Use the direct manual import API endpoint (POST)
        response = self._make_request("POST", "/api/v3/manualimport", json=all_import_items)
        if response.status_code in (200, 201, 202):
            return True
        else:
            print(f"Failed to execute manual import: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    def get_episode_files(self, series_id: int) -> list[dict[str, Any]]:
        """Get episode files for a series to verify imports.

        Args:
            series_id: Sonarr series ID

        Returns:
            List of episode file data from Sonarr API
        """
        params = {"seriesId": series_id}
        response = self._make_request("GET", "/api/v3/episodefile", params=params)
        if response.is_success:
            episode_files = response.json()
            return episode_files
        else:
            print(f"Failed to get episode files: {response.status_code}")
            print(f"Response: {response.text}")
            return []

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

        # Look for Kodi/XBMC metadata provider and enable it
        kodi_config = None
        for config in metadata_configs:
            config_name = config.get("name", "").lower()
            if any(name in config_name for name in ["kodi", "xbmc"]):
                kodi_config = config
                break

        if not kodi_config:
            raise ValueError("No Kodi/XBMC metadata provider found")

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
                "seriesMetadataUrl",
            ]:
                field["value"] = True

        # Update the configuration
        response = self._make_request(
            "PUT", f"/api/v3/metadata/{kodi_config['id']}", json=kodi_config
        )

        if response.is_success:
            return True
        else:
            print(f"Failed to update metadata settings: {response.status_code}")
            print(f"Response body: {response.text}")
            return False

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
