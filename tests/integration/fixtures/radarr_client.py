"""Radarr API client for integration testing."""

import time
from pathlib import Path
from typing import Any

import httpx

from sonarr_metadata_rewrite.retry_utils import retry
from tests.integration.fixtures.arr_client import ArrClient


class RadarrClient(ArrClient):
    """Small Radarr API client used by integration tests."""

    def wait_for_ready(self, max_attempts: int = 30, delay: float = 1.0) -> bool:
        """Wait for Radarr API readiness."""
        timeout_sec = max_attempts * delay

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
            return check_status()
        except Exception as exc:
            print(f"Radarr failed to become ready: {exc}")
            return False

    def add_movie(
        self,
        tmdb_id: int,
        root_folder: str = "/movies",
        quality_profile_id: int = 1,
    ) -> dict[str, Any]:
        """Add movie from TMDB lookup without searching for a release."""
        self.ensure_root_folder(root_folder)
        response = self._make_request(
            "GET", "/api/v3/movie/lookup", params={"term": f"tmdb:{tmdb_id}"}
        )
        response.raise_for_status()
        lookup_results = response.json()
        if not lookup_results:
            raise ValueError(f"No movie found for TMDB ID: {tmdb_id}")

        movie_data = lookup_results[0]
        movie_data.update(
            {
                "tmdbId": tmdb_id,
                "rootFolderPath": root_folder,
                "qualityProfileId": quality_profile_id,
                "monitored": True,
                "minimumAvailability": "released",
                "addOptions": {"searchForMovie": False},
            }
        )
        response = self._make_request("POST", "/api/v3/movie", json=movie_data)
        response.raise_for_status()
        return response.json()

    def ensure_root_folder(self, root_folder: str) -> None:
        """Register mounted movie root when Radarr has not seen it yet."""
        response = self._make_request("GET", "/api/v3/rootfolder")
        response.raise_for_status()
        if any(folder.get("path") == root_folder for folder in response.json()):
            return
        response = self._make_request(
            "POST", "/api/v3/rootfolder", json={"path": root_folder}
        )
        response.raise_for_status()

    def trigger_disk_scan(self, movie_id: int) -> bool:
        """Trigger a Radarr rescan for one movie."""
        response = self._make_request(
            "POST", "/api/v3/command", json={"name": "RescanMovie", "movieId": movie_id}
        )
        return response.status_code in (200, 201)

    def get_movie(self, movie_id: int) -> dict[str, Any]:
        """Get movie details, including imported file state."""
        response = self._make_request("GET", f"/api/v3/movie/{movie_id}")
        response.raise_for_status()
        return response.json()

    def configure_metadata_settings(self, use_movie_nfo: bool) -> bool:
        """Enable Kodi/Emby movie metadata and images for selected NFO mode."""
        response = self._make_request("GET", "/api/v3/metadata")
        response.raise_for_status()
        metadata_configs = response.json()
        field_values = {
            "moviemetadata": True,
            "movieimages": True,
            "usemovienfo": use_movie_nfo,
        }
        provider = next(
            (
                config
                for config in metadata_configs
                if any(
                    name in config.get("name", "").lower()
                    for name in ("kodi", "xbmc", "emby")
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
        if provider is None:
            raise ValueError(
                "No Kodi/XBMC/Emby metadata provider supports movieMetadata, "
                "movieImages, and UseMovieNfo"
            )
        provider["enable"] = True
        for field in provider["fields"]:
            field_name = field.get("name", "").lower()
            if field_name in field_values:
                field["value"] = field_values[field_name]

        response = self._make_request(
            "PUT", f"/api/v3/metadata/{provider['id']}", json=provider
        )
        return response.is_success

    def remove_movie(
        self,
        movie_id: int,
        media_root: Path,
        movie_directory: Path,
        timeout: float = 30.0,
    ) -> bool:
        """Remove movie and wait for Radarr to delete its directory."""
        response = self._make_request(
            "DELETE", f"/api/v3/movie/{movie_id}", params={"deleteFiles": "true"}
        )
        if not response.is_success:
            return False

        start_time = time.time()
        while time.time() - start_time < timeout:
            if not movie_directory.exists():
                return True
            time.sleep(1)

        if movie_directory.exists():
            remaining_files = list(movie_directory.rglob("*"))
            raise RuntimeError(
                f"Movie directory {movie_directory} still exists after {timeout}s. "
                f"Remaining files: {remaining_files}"
            )
        return True
