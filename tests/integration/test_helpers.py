"""Helper functions for integration tests."""

import shutil
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tests.integration.fixtures.series_manager import SeriesManager
from tests.integration.fixtures.sonarr_client import SonarrClient
from tests.integration.fixtures.subprocess_service_manager import (
    SubprocessServiceManager,
)


def create_fake_episode_file(
    media_root: Path,
    series_slug: str,
    season: int,
    episode: int,
    title: str = "Episode",
) -> Path:
    """Create a fake episode video file to trigger Sonarr processing.

    Uses a pre-generated minimal valid MKV file to ensure Sonarr's FFprobe
    can successfully parse media information.

    Args:
        media_root: Root media directory
        series_slug: Series directory name (e.g., "breaking-bad")
        season: Season number
        episode: Episode number
        title: Episode title

    Returns:
        Path to created file
    """
    series_dir = media_root / series_slug
    season_dir = series_dir / f"Season {season:02d}"
    season_dir.mkdir(parents=True, exist_ok=True)

    # Convert series slug to title for proper Sonarr naming
    series_title = series_slug.replace("-", " ").title()
    filename = f"{series_title} - S{season:02d}E{episode:02d} - {title}.mkv"
    episode_file = season_dir / filename

    # Copy valid sample MKV file to avoid FFprobe "EBML header parsing failed" errors
    # Sample generated with: ffmpeg -f lavfi -i color=black:size=64x64:duration=1 \
    #   -f lavfi -i sine=frequency=1000:duration=1 -c:v libx264 -c:a aac \
    #   -preset ultrafast -y sample_episode.mkv
    sample_file = Path(__file__).parent / "fixtures" / "sample_episode.mkv"
    shutil.copy2(sample_file, episode_file)
    return episode_file


def retry(
    timeout: float = 15.0, interval: float = 0.5, log_interval: float = 2.0
) -> Callable[[Callable[[], None]], Callable[[], None]]:
    """Retry decorator that catches any exception and retries until timeout.

    Args:
        timeout: Maximum time to retry in seconds
        interval: Time between retries in seconds
        log_interval: Time between log messages in seconds

    Returns:
        Decorator function
    """

    def decorator(func: Callable[[], None]) -> Callable[[], None]:
        def wrapper() -> None:
            start_time = time.time()
            last_log = 0.0
            last_error = None

            while time.time() - start_time < timeout:
                try:
                    func()
                    return  # Success
                except Exception as e:
                    last_error = e

                elapsed = time.time() - start_time
                if elapsed - last_log >= log_interval:
                    print(f"Still waiting... ({elapsed:.1f}s elapsed)")
                    last_log = elapsed

                time.sleep(interval)

            # Timeout reached, re-raise the last error
            if last_error:
                raise last_error
            else:
                raise AssertionError("Timeout reached with no errors captured")

        return wrapper

    return decorator


def wait_for_nfo_files(
    series_path: Path, expected_count: int, timeout: float = 5.0
) -> list[Path]:
    """Wait for .nfo files to be generated in series directory.

    Args:
        series_path: Path to series directory
        expected_count: Expected number of .nfo files
        timeout: Maximum time to wait in seconds

    Returns:
        List of .nfo files found

    Raises:
        AssertionError: If expected number of .nfo files not found within timeout
    """
    print(
        f"Waiting for {expected_count} .nfo files in {series_path} "
        f"(timeout: {timeout}s)"
    )

    @retry(timeout=timeout, interval=0.5, log_interval=1.0)
    def check_nfo_files() -> None:
        nfo_files = list(series_path.rglob("*.nfo"))
        if len(nfo_files) >= expected_count:
            print(f"Found {len(nfo_files)} .nfo files: {nfo_files}")
        else:
            assert len(nfo_files) >= expected_count, (
                f"Expected {expected_count} .nfo files, but only found "
                f"{len(nfo_files)} in {series_path}. Files found: {nfo_files}"
            )

    check_nfo_files()

    # Wait a bit more to ensure files are fully written
    time.sleep(0.5)
    return sorted(series_path.rglob("*.nfo"))


def parse_nfo_content(nfo_path: Path) -> dict[str, Any]:
    """Parse .nfo file and extract key metadata.

    Args:
        nfo_path: Path to .nfo file

    Returns:
        Dictionary with parsed metadata
    """
    tree = ET.parse(nfo_path)
    root = tree.getroot()

    metadata: dict[str, Any] = {
        "root_tag": root.tag,
        "title": "",
        "plot": "",
        "tmdb_id": None,
        "tvdb_id": None,
    }

    # Extract title
    title_elem = root.find("title")
    if title_elem is not None and title_elem.text:
        metadata["title"] = title_elem.text.strip()

    # Extract plot/overview
    plot_elem = root.find("plot")
    if plot_elem is not None and plot_elem.text:
        metadata["plot"] = plot_elem.text.strip()

    # Extract IDs
    for uniqueid in root.findall(".//uniqueid"):
        id_type = uniqueid.get("type")
        id_value = uniqueid.text

        if id_type == "tmdb" and id_value:
            try:
                metadata["tmdb_id"] = int(id_value.strip())
            except ValueError:
                pass
        elif id_type == "tvdb" and id_value:
            try:
                metadata["tvdb_id"] = int(id_value.strip())
            except ValueError:
                pass

    return metadata


class SeriesWithNfos:
    """Context manager for setting up series with NFO files."""

    def __init__(
        self,
        configured_sonarr_container: SonarrClient,
        temp_media_root: Path,
        tvdb_id: int,
        episodes: list[tuple[str, int, int]] | None = None,
    ):
        """Initialize the context manager.

        Args:
            configured_sonarr_container: Configured Sonarr client
            temp_media_root: Temporary media root directory
            tvdb_id: TVDB ID of the series to set up
            episodes: List of (title, season, episode) tuples, defaults to 2 episodes
        """
        self.sonarr = configured_sonarr_container
        self.media_root = temp_media_root
        self.tvdb_id = tvdb_id
        self.episodes = episodes or [("Episode 1", 1, 1), ("Episode 2", 1, 2)]
        self.series: SeriesManager | None = None

    def __enter__(self) -> list[Path]:
        """Set up series and return series info.

        Returns:
            List of NFO file paths
        """
        self.series = SeriesManager(self.sonarr, self.tvdb_id, "/tv", self.media_root)
        self.series.__enter__()

        # Create fake episode files to trigger Sonarr processing
        episode_files = []
        for title, season, episode in self.episodes:
            episode_file = create_fake_episode_file(
                self.media_root, self.series.slug, season, episode, title
            )
            episode_files.append(episode_file)

        # Trigger disk scan to detect episode files
        series_path = self.media_root / self.series.slug
        scan_success = self.sonarr.trigger_disk_scan(self.series.id)
        if not scan_success:
            raise RuntimeError("Failed to trigger disk scan")

        # Wait for disk scan to complete and import files
        @retry(timeout=15.0, interval=1.0, log_interval=2.0)
        def check_disk_scan_complete() -> None:
            assert self.series is not None
            imported_files = self.sonarr.get_episode_files(self.series.id)
            assert len(imported_files) >= len(episode_files), (
                f"Disk scan still in progress: expected {len(episode_files)} "
                f"episode files, but only {len(imported_files)} imported so far"
            )

        check_disk_scan_complete()

        # Trigger metadata refresh to ensure .nfo files are generated
        metadata_success = self.sonarr.refresh_series(self.series.id)
        if not metadata_success:
            raise RuntimeError("Failed to trigger metadata refresh")

        # Wait for .nfo files to be generated
        expected_nfo_count = len(episode_files) + 1  # episodes + series
        nfo_files = wait_for_nfo_files(series_path, expected_nfo_count, timeout=30.0)

        return nfo_files

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Clean up series."""
        if self.series:
            self.series.__exit__(exc_type, exc_val, exc_tb)


class ServiceRunner:
    """Context manager for running service with given configuration."""

    def __init__(
        self,
        temp_media_root: Path,
        service_config: dict[str, str],
        startup_pattern: str | None = None,
    ):
        # Base configuration
        env_overrides = {
            "REWRITE_ROOT_DIR": str(temp_media_root),
            "ENABLE_FILE_MONITOR": "true",
            "ENABLE_FILE_SCANNER": "true",
            "PREFERRED_LANGUAGES": "zh-CN",
        }

        # Apply service-specific configuration overrides
        env_overrides.update(service_config)

        self.service = SubprocessServiceManager(
            env_overrides=env_overrides, startup_pattern=startup_pattern
        )

    def __enter__(self) -> SubprocessServiceManager:
        self.service.start()
        return self.service

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.service.stop()


def verify_translations(nfo_files: list[Path], expect_chinese: bool) -> None:
    """Wait for and verify translation results.

    Args:
        nfo_files: List of .nfo files to check
        expect_chinese: True if files should contain Chinese, False if not

    Raises:
        AssertionError: If files don't match expected state
    """
    state_desc = "Chinese translations" if expect_chinese else "non-Chinese content"
    print(f"Waiting for {state_desc} in {len(nfo_files)} files...")

    @retry(timeout=15.0, interval=0.5, log_interval=2.0)
    def check_translation_state() -> None:
        chinese_count = 0
        for nfo_file in nfo_files:
            metadata = parse_nfo_content(nfo_file)
            # Both title and plot must have Chinese characters for complete translation
            both_fields_have_chinese = all(
                any("\u4e00" <= char <= "\u9fff" for char in text)
                for text in [metadata.get("title", ""), metadata.get("plot", "")]
            )
            if both_fields_have_chinese:
                chinese_count += 1

        if expect_chinese:
            assert chinese_count == len(nfo_files), (
                f"Expected all {len(nfo_files)} files to have Chinese in both title "
                f"and plot, but only {chinese_count} do"
            )
        else:
            assert chinese_count == 0, (
                f"Expected no files to have Chinese in both title and plot, "
                f"but {chinese_count} out of {len(nfo_files)} still do"
            )

    check_translation_state()

    result_desc = "contain Chinese" if expect_chinese else "contain no Chinese"
    print(f"✅ All {len(nfo_files)} files verified to {result_desc}")
