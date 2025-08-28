"""Helper functions for integration tests."""

import shutil
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

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


def wait_with_retry(
    check_func: Callable[[], bool],
    timeout: float = 10.0,
    interval: float = 0.5,
    log_interval: float = 1.0,
) -> bool:
    """Common wait and retry logic for tests.

    Args:
        check_func: Function that returns True when condition is met
        timeout: Maximum time to wait in seconds
        interval: Time between checks in seconds
        log_interval: Time between log messages in seconds

    Returns:
        True if condition was met within timeout, False otherwise
    """
    start_time = time.time()
    last_log = 0.0

    while time.time() - start_time < timeout:
        if check_func():
            return True

        elapsed = time.time() - start_time
        if elapsed - last_log >= log_interval:
            print(f"Still waiting... ({elapsed:.1f}s elapsed)")
            last_log = elapsed

        time.sleep(interval)

    return False


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
        RuntimeError: If expected number of .nfo files not found within timeout
    """
    print(
        f"Waiting for {expected_count} .nfo files in {series_path} "
        f"(timeout: {timeout}s)"
    )

    def check_nfo_files() -> bool:
        nfo_files = list(series_path.rglob("*.nfo"))
        if len(nfo_files) >= expected_count:
            print(f"Found {len(nfo_files)} .nfo files: {nfo_files}")
            return True
        return False

    if wait_with_retry(
        check_nfo_files, timeout=timeout, interval=0.5, log_interval=1.0
    ):
        # Wait a bit more to ensure files are fully written
        time.sleep(0.5)
        return sorted(series_path.rglob("*.nfo"))

    # Failed to find enough files
    nfo_files = list(series_path.rglob("*.nfo"))
    raise RuntimeError(
        f"Expected {expected_count} .nfo files, but only found {len(nfo_files)} "
        f"after {timeout:.1f}s timeout. Files found: {nfo_files}"
    )


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

    # Wait for disk scan to complete
    time.sleep(10)

    # Check if disk scan already imported the files
    print("Checking if disk scan automatically imported episode files...")
    imported_files = configured_sonarr_container.get_episode_files(series.id)
    print(f"After disk scan, found {len(imported_files)} imported episode files")

    # Only do manual import if disk scan didn't import the files
    if len(imported_files) < len(episode_files):
        print("Manual import needed as disk scan didn't import all files...")
        # Manual import the episode files to ensure Sonarr recognizes them
        print("Manually importing episode files into Sonarr...")

        # Convert host paths to container paths for manual import
        # Host: /tmp/sonarr_media_xyz/series/season/file.mkv
        # Container: /tv/series/season/file.mkv
        container_paths = []
        for episode_file in episode_files:
            # Get path relative to temp_media_root
            relative_path = episode_file.relative_to(temp_media_root)
            # Convert to container path
            container_path = f"/tv/{relative_path}"
            container_paths.append(container_path)
            print(f"Converting {episode_file} -> {container_path}")

        import_success = configured_sonarr_container.manual_import(
            series.id, container_paths
        )
        if not import_success:
            series.__exit__(None, None, None)
            raise RuntimeError("Failed to manually import episode files")
        print("Manual import command submitted successfully")

        # Verify that episode files were imported by checking Sonarr's episode files API
        print("Verifying episode files were imported...")

        def check_import_complete() -> bool:
            imported_files = configured_sonarr_container.get_episode_files(series.id)
            return len(imported_files) >= len(episode_files)

        if not wait_with_retry(
            check_import_complete, timeout=15.0, interval=1.0, log_interval=2.0
        ):
            imported_files = configured_sonarr_container.get_episode_files(series.id)
            series.__exit__(None, None, None)
            raise RuntimeError(
                f"Manual import verification failed: expected {len(episode_files)} "
                f"episode files, but only {len(imported_files)} were imported into "
                f"Sonarr"
            )

    imported_files = configured_sonarr_container.get_episode_files(series.id)
    print(f"✅ Successfully have {len(imported_files)} episode files in Sonarr")

    # Also trigger metadata refresh to ensure .nfo files are generated for episodes
    print("Triggering metadata refresh to ensure episode .nfo files are generated...")
    metadata_success = configured_sonarr_container.refresh_series(series.id)
    if not metadata_success:
        series.__exit__(None, None, None)
        raise RuntimeError("Failed to trigger metadata refresh")
    print("Metadata refresh command submitted successfully")

    # Wait for .nfo files to be generated (allow more time for episode files)
    print("Waiting for .nfo files to be generated...")
    episode_count = len(episode_files)
    expected_nfo_count = episode_count + 1  # episodes + series

    nfo_files = wait_for_nfo_files(series_path, expected_nfo_count, timeout=30.0)

    print(f"Found .nfo files: {nfo_files}")

    # List all files to debug what Sonarr actually generated
    all_files = list(series_path.rglob("*")) if series_path.exists() else []
    print(f"All files in series directory: {all_files}")

    print(
        f"✅ Sonarr generated {len(nfo_files)} .nfo files for {episode_count} "
        f"episode media files"
    )

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

        # For series files, TMDB ID is required directly
        # For episode files, TMDB ID can be looked up from parent
        if metadata["root_tag"] == "tvshow" and not metadata.get("tmdb_id"):
            series.__exit__(None, None, None)
            pytest.fail(
                f"No TMDB ID found in series file {nfo_file.name}. "
                f"Sonarr may not have populated TMDB metadata yet."
            )

    return series, nfo_files, original_backups


class ServiceRunner:
    """Context manager for running service with given configuration."""

    def __init__(
        self,
        temp_media_root: Path,
        service_config: dict[str, str],
        startup_wait: float = 2.0,
    ):
        # Base configuration
        env_overrides = {
            "REWRITE_ROOT_DIR": str(temp_media_root),
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
    service_config: dict[str, str],
    startup_wait: float = 2.0,
) -> ServiceRunner:
    """Run service with given configuration.

    Args:
        temp_media_root: Temporary media root directory
        service_config: Service configuration overrides
        startup_wait: Time to wait after service starts

    Returns:
        Service runner (context manager)
    """
    return ServiceRunner(temp_media_root, service_config, startup_wait)


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


def is_translated(metadata: dict[str, Any]) -> bool:
    """Check if metadata contains Chinese translations.

    Args:
        metadata: Parsed metadata dictionary

    Returns:
        True if either title or plot contains Chinese characters
    """
    title_translated = any(
        "\u4e00" <= char <= "\u9fff" for char in metadata.get("title", "")
    )
    plot_translated = any(
        "\u4e00" <= char <= "\u9fff" for char in metadata.get("plot", "")
    )
    return title_translated or plot_translated


def count_translations(nfo_files: list[Path]) -> int:
    """Count how many NFO files have been translated.

    Args:
        nfo_files: List of NFO files to check

    Returns:
        Number of files containing Chinese translations
    """
    translations = 0
    for nfo_file in nfo_files:
        metadata = parse_nfo_content(nfo_file)
        if is_translated(metadata):
            translations += 1
    return translations


def metadata_matches(current: dict[str, Any], original: dict[str, Any]) -> bool:
    """Check if current metadata matches original metadata.

    Args:
        current: Current metadata dictionary
        original: Original metadata dictionary

    Returns:
        True if both title and plot match exactly
    """
    title_matches = current.get("title") == original.get("title")
    plot_matches = current.get("plot") == original.get("plot")
    return title_matches and plot_matches


def wait_and_verify_translations(
    nfo_files: list[Path], wait_seconds: int, min_expected: int = 1
) -> int:
    """Wait for translations and verify they occurred.

    Args:
        nfo_files: List of NFO files to check
        wait_seconds: Seconds to wait before checking
        min_expected: Minimum number of expected translations

    Returns:
        Number of translations found

    Raises:
        AssertionError: If fewer than min_expected translations found
    """
    time.sleep(wait_seconds)
    translations = count_translations(nfo_files)
    assert (
        translations >= min_expected
    ), f"Expected at least {min_expected} translations, got {translations}"
    return translations
