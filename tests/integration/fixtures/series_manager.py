"""Series lifecycle management for integration tests."""

from pathlib import Path
from types import TracebackType
from typing import Any

from tests.integration.fixtures.sonarr_client import SonarrClient


class SeriesManager:
    """Context manager for automatic series lifecycle management in tests."""

    def __init__(
        self,
        sonarr_client: SonarrClient,
        tvdb_id: int,
        root_folder: str,
        temp_media_root: Path,
        quality_profile_id: int = 1,
    ):
        """Initialize series manager.

        Args:
            sonarr_client: Configured Sonarr API client
            tvdb_id: TVDB series ID to add
            root_folder: Sonarr root folder path (e.g., "/tv")
            temp_media_root: Local media root directory path
            quality_profile_id: Quality profile ID (default: 1)
        """
        self.sonarr_client = sonarr_client
        self.tvdb_id = tvdb_id
        self.root_folder = root_folder
        self.temp_media_root = temp_media_root
        self.quality_profile_id = quality_profile_id

        # Will be populated on __enter__
        self.series_data: dict[str, Any] | None = None
        self.series_id: int | None = None
        self.series_slug: str | None = None
        self.series_title: str | None = None

    def __enter__(self) -> "SeriesManager":
        """Add series and return self."""
        print(f"Adding series with TVDB ID {self.tvdb_id}...")
        self.series_data = self.sonarr_client.add_series(
            tvdb_id=self.tvdb_id,
            root_folder=self.root_folder,
            quality_profile_id=self.quality_profile_id,
        )

        self.series_id = self.series_data["id"]
        self.series_slug = self.series_data["titleSlug"]
        self.series_title = self.series_data["title"]

        print(
            f"Added series: {self.series_title} "
            f"(ID: {self.series_id}, slug: {self.series_slug})"
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        del exc_type, exc_val, exc_tb  # Unused parameters
        """Clean up series and verify removal."""
        if self.series_id is None or self.series_slug is None:
            print("No series to clean up (series was not successfully added)")
            return

        try:
            print(f"Cleaning up series {self.series_id} ({self.series_slug})...")
            self.sonarr_client.remove_series(
                series_id=self.series_id,
                media_root=self.temp_media_root,
                series_slug=self.series_slug,
                delete_files=True,
            )
            print(f"Successfully cleaned up series {self.series_id}")
        except Exception as e:
            print(f"Error during series cleanup: {e}")
            # Don't raise - we don't want cleanup failures to mask test failures

    @property
    def id(self) -> int:
        """Get series ID (available after entering context)."""
        if self.series_id is None:
            raise RuntimeError("Series not added yet - use within context manager")
        return self.series_id

    @property
    def slug(self) -> str:
        """Get series slug (available after entering context)."""
        if self.series_slug is None:
            raise RuntimeError("Series not added yet - use within context manager")
        return self.series_slug

    @property
    def title(self) -> str:
        """Get series title (available after entering context)."""
        if self.series_title is None:
            raise RuntimeError("Series not added yet - use within context manager")
        return self.series_title

    @property
    def data(self) -> dict[str, Any]:
        """Get full series data (available after entering context)."""
        if self.series_data is None:
            raise RuntimeError("Series not added yet - use within context manager")
        return self.series_data
