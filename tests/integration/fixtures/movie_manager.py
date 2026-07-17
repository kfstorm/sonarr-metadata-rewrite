"""Movie lifecycle management for integration tests."""

from pathlib import Path
from types import TracebackType
from typing import Any

from tests.integration.fixtures.radarr_client import RadarrClient


class MovieManager:
    """Context manager for Radarr movie lifecycle in tests."""

    def __init__(
        self,
        radarr_client: RadarrClient,
        tmdb_id: int,
        root_folder: str,
        temp_media_root: Path,
        quality_profile_id: int = 1,
    ):
        self.radarr_client = radarr_client
        self.tmdb_id = tmdb_id
        self.root_folder = root_folder
        self.temp_media_root = temp_media_root
        self.quality_profile_id = quality_profile_id
        self.movie_data: dict[str, Any] | None = None

    def __enter__(self) -> "MovieManager":
        """Add movie to Radarr."""
        self.movie_data = self.radarr_client.add_movie(
            self.tmdb_id, self.root_folder, self.quality_profile_id
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Delete movie files and Radarr entry."""
        del exc_type, exc_val, exc_tb
        if self.movie_data is None:
            return
        try:
            self.radarr_client.remove_movie(self.id, self.directory)
        except Exception as exc:
            print(f"Error during movie cleanup: {exc}")

    @property
    def id(self) -> int:
        """Radarr movie ID."""
        return self.data["id"]

    @property
    def title(self) -> str:
        """Movie title returned by Radarr."""
        return self.data["title"]

    @property
    def directory(self) -> Path:
        """Host path corresponding to Radarr movie path."""
        movie_path = Path(self.data["path"])
        return self.temp_media_root / movie_path.relative_to(self.root_folder)

    @property
    def data(self) -> dict[str, Any]:
        """Full movie data."""
        if self.movie_data is None:
            raise RuntimeError("Movie not added yet - use within context manager")
        return self.movie_data
