"""Helper functions for integration tests."""

import os
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from sonarr_metadata_rewrite.config import get_settings
from tests.integration.fixtures.series_manager import SeriesManager
from tests.integration.fixtures.sonarr_client import SonarrClient
from tests.integration.fixtures.subprocess_service_manager import (
    SubprocessServiceManager,
)

# Breaking Bad TVDB ID (well-known series with good metadata)
BREAKING_BAD_TVDB_ID = 81189


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

    filename = f"S{season:02d}E{episode:02d} - {title}.mkv"
    episode_file = season_dir / filename

    # Copy valid sample MKV file to avoid FFprobe "EBML header parsing failed" errors
    # Sample generated with: ffmpeg -f lavfi -i color=black:size=64x64:duration=1 \
    #   -c:v libx264 -preset ultrafast -y sample_episode.mkv
    sample_file = Path(__file__).parent / "fixtures" / "sample_episode.mkv"
    shutil.copy2(sample_file, episode_file)
    return episode_file


def wait_for_nfo_files(series_path: Path, timeout: float = 5.0) -> list[Path]:
    """Wait for .nfo files to be generated in series directory.

    Args:
        series_path: Path to series directory
        timeout: Maximum time to wait in seconds

    Returns:
        List of .nfo files found
    """
    print(f"Waiting for .nfo files in {series_path} (timeout: {timeout}s)")
    start_time = time.time()
    last_check = 0.0

    while time.time() - start_time < timeout:
        elapsed = time.time() - start_time
        if elapsed - last_check >= 2:  # Log every 2 seconds
            print(f"Still waiting for .nfo files... ({elapsed:.1f}s elapsed)")
            last_check = elapsed

        nfo_files = list(series_path.rglob("*.nfo"))
        if nfo_files:
            print(f"Found .nfo files after {elapsed:.1f}s: {nfo_files}")
            # Wait a bit more to ensure files are fully written
            time.sleep(1)
            return sorted(nfo_files)
        time.sleep(1)

    elapsed = time.time() - start_time
    print(f"No .nfo files found after {elapsed:.1f}s timeout")
    return []


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


def compare_nfo_files(original_path: Path, translated_path: Path) -> dict[str, Any]:
    """Compare original and translated .nfo files.

    Args:
        original_path: Path to original .nfo file
        translated_path: Path to translated .nfo file

    Returns:
        Dictionary with comparison results
    """
    original = parse_nfo_content(original_path)
    translated = parse_nfo_content(translated_path)

    return {
        "original": original,
        "translated": translated,
        "title_changed": original["title"] != translated["title"],
        "plot_changed": original["plot"] != translated["plot"],
        "ids_preserved": (
            original["tmdb_id"] == translated["tmdb_id"]
            and original["tvdb_id"] == translated["tvdb_id"]
        ),
    }


def setup_series_with_nfos(
    configured_sonarr_container: SonarrClient,
    temp_media_root: Path,
) -> tuple[SeriesManager, list[Path], dict[Path, Path]]:
    """Set up series with .nfo files and return backup mapping.

    Args:
        configured_sonarr_container: Configured Sonarr client
        temp_media_root: Temporary media root directory

    Returns:
        Tuple of (SeriesManager, nfo_files, original_backups)
    """
    series = SeriesManager(
        configured_sonarr_container,
        BREAKING_BAD_TVDB_ID,
        "/tv",
        temp_media_root,
    )
    series.__enter__()

    # Create fake episode files to trigger Sonarr processing
    print("Creating fake episode files...")
    episode_files = [
        create_fake_episode_file(temp_media_root, series.slug, 1, 1, "Pilot"),
        create_fake_episode_file(
            temp_media_root, series.slug, 1, 2, "Cat's in the Bag"
        ),
    ]

    for episode_file in episode_files:
        print(f"Created: {episode_file}")

    # Trigger disk scan to detect episode files
    print("Triggering disk scan to detect episode files...")
    series_path = temp_media_root / series.slug
    scan_success = configured_sonarr_container.trigger_disk_scan(series.id)
    if not scan_success:
        series.__exit__(None, None, None)
        raise RuntimeError("Failed to trigger disk scan")
    print("Disk scan command submitted successfully")

    # Wait for .nfo files to be generated
    print("Waiting for .nfo files to be generated...")
    nfo_files = wait_for_nfo_files(series_path, timeout=10.0)

    if not nfo_files:
        # List what files exist for debugging
        all_files = list(series_path.rglob("*")) if series_path.exists() else []
        print(f"No .nfo files found. All files in {series_path}: {all_files}")
        series.__exit__(None, None, None)
        pytest.fail("Sonarr did not generate .nfo files within timeout after disk scan")

    print(f"Found .nfo files: {nfo_files}")

    # Backup original .nfo files for comparison
    original_backups = {}
    for nfo_file in nfo_files:
        backup_path = nfo_file.with_suffix(".nfo.original")
        shutil.copy2(nfo_file, backup_path)
        original_backups[nfo_file] = backup_path

    # Parse original metadata to verify it contains TMDB IDs
    for nfo_file in nfo_files:
        metadata = parse_nfo_content(nfo_file)
        print(f"Original metadata for {nfo_file.name}: {metadata}")

        # Verify we have a TMDB ID (required for translation)
        if not metadata.get("tmdb_id"):
            series.__exit__(None, None, None)
            pytest.skip(
                f"No TMDB ID found in {nfo_file.name}. "
                f"Sonarr may not have populated TMDB metadata yet."
            )

    return series, nfo_files, original_backups


def get_tmdb_api_key(temp_media_root: Path) -> str:
    """Get TMDB API key with proper environment handling.

    Args:
        temp_media_root: Temporary media root directory

    Returns:
        TMDB API key
    """
    original_rewrite_root_dir = os.environ.get("REWRITE_ROOT_DIR")
    os.environ["REWRITE_ROOT_DIR"] = str(temp_media_root)

    try:
        settings = get_settings()
        return settings.tmdb_api_key
    finally:
        # Restore original environment
        if original_rewrite_root_dir is not None:
            os.environ["REWRITE_ROOT_DIR"] = original_rewrite_root_dir
        else:
            os.environ.pop("REWRITE_ROOT_DIR", None)


class ServiceRunner:
    """Context manager for running service with given configuration."""

    def __init__(
        self,
        temp_media_root: Path,
        tmdb_api_key: str,
        service_config: dict[str, str],
        startup_wait: float = 2.0,
    ):
        # Base configuration
        env_overrides = {
            "REWRITE_ROOT_DIR": str(temp_media_root),
            "TMDB_API_KEY": tmdb_api_key,
            "PREFERRED_LANGUAGES": "zh-CN",
        }

        # Apply service-specific configuration
        env_overrides.update(service_config)

        self.service = SubprocessServiceManager(env_overrides=env_overrides)
        self.startup_wait = startup_wait

    def __enter__(self) -> SubprocessServiceManager:
        self.service.start()
        if self.service.is_running():
            time.sleep(self.startup_wait)
        return self.service

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.service.stop()


def run_service_with_config(
    temp_media_root: Path,
    tmdb_api_key: str,
    service_config: dict[str, str],
    startup_wait: float = 2.0,
) -> ServiceRunner:
    """Run service with given configuration.

    Args:
        temp_media_root: Temporary media root directory
        tmdb_api_key: TMDB API key
        service_config: Service configuration overrides
        startup_wait: Time to wait after service starts

    Returns:
        Service runner (context manager)
    """
    return ServiceRunner(temp_media_root, tmdb_api_key, service_config, startup_wait)


def verify_translations(
    nfo_files: list[Path],
    original_backups: dict[Path, Path],
    expected_count: int | None = None,
) -> int:
    """Verify translation results.

    Args:
        nfo_files: List of .nfo files to check
        original_backups: Mapping of nfo_file -> backup_path
        expected_count: Expected translations (if None, require > 0)

    Returns:
        Number of successful translations
    """
    print("Verifying translations...")
    successful_translations = 0

    for nfo_file in nfo_files:
        original_backup = original_backups[nfo_file]

        # Compare original vs translated content
        comparison = compare_nfo_files(original_backup, nfo_file)
        print(f"Comparison for {nfo_file.name}: {comparison}")

        # Check if translation occurred
        if comparison["title_changed"] or comparison["plot_changed"]:
            successful_translations += 1

            # Verify we have actual translated content, not just fallback
            translated_metadata = comparison["translated"]

            # Check that translated title is not empty (real translation)
            assert translated_metadata["title"], (
                f"Empty translated title in {nfo_file.name}. "
                "This indicates TMDB API returned empty translation data."
            )

            # Check that translated description is not empty
            assert translated_metadata["plot"], (
                f"Empty translated description in {nfo_file.name}. "
                "This indicates TMDB API returned empty translation data."
            )

            # Verify IDs are preserved
            assert comparison[
                "ids_preserved"
            ], f"TMDB/TVDB IDs not preserved in {nfo_file.name}"

            print(f"✅ Successfully translated {nfo_file.name}")
        else:
            print(f"⚠️ No translation changes detected in {nfo_file.name}")

    # Ensure expected number of translations
    if expected_count is not None:
        assert (
            successful_translations == expected_count
        ), f"Expected {expected_count} translations, got {successful_translations}"
    else:
        assert successful_translations > 0, (
            "No .nfo files were successfully translated. "
            "Check TMDB API key and network connectivity."
        )

    print(
        f"Successfully translated {successful_translations} "
        f"out of {len(nfo_files)} files"
    )

    return successful_translations
