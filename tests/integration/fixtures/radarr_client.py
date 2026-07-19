"""Radarr API client for integration testing."""

from pathlib import Path
from typing import Any, cast

from sonarr_metadata_rewrite.retry_utils import retry
from tests.integration.fixtures.arr_client import ArrClient


class RadarrClient(ArrClient):
    """Small Radarr API client used by integration tests."""

    service_name = "Radarr"

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
        added_movie = cast(dict[str, Any], response.json())
        self._wait_for_queued_command(
            "RefreshMovie", "movieIds", cast(int, added_movie["id"])
        )
        return added_movie

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
        if response.status_code not in (200, 201):
            return False

        command = cast(dict[str, Any], response.json())
        self._wait_for_command(cast(int, command["id"]))
        return True

    def get_movie(self, movie_id: int) -> dict[str, Any]:
        """Get movie details, including imported file state."""
        response = self._make_request("GET", f"/api/v3/movie/{movie_id}")
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def configure_metadata_settings(self, use_movie_nfo: bool) -> bool:
        """Enable Kodi/Emby movie metadata and images for selected NFO mode."""
        field_values = {
            "moviemetadata": True,
            "movieimages": True,
            "usemovienfo": use_movie_nfo,
        }

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
            assert provider is not None, (
                "Radarr metadata providers are not initialized yet"
            )
            return cast(dict[str, Any], provider)

        provider = get_provider()
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
        movie_directory: Path,
        timeout: float = 30.0,
    ) -> bool:
        """Remove movie and wait for Radarr to delete its directory."""
        response = self._make_request(
            "DELETE", f"/api/v3/movie/{movie_id}", params={"deleteFiles": "true"}
        )
        if not response.is_success:
            return False

        return self._wait_for_directory_removal(movie_directory, "Movie", timeout)
