"""Helper functions for integration tests."""

import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

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
        "overview": "",
        "tmdb_id": None,
        "tvdb_id": None,
    }

    # Extract title
    title_elem = root.find("title")
    if title_elem is not None and title_elem.text:
        metadata["title"] = title_elem.text.strip()

    # Extract plot
    plot_elem = root.find("plot")
    if plot_elem is not None and plot_elem.text:
        metadata["plot"] = plot_elem.text.strip()

    # Extract overview (Emby format)
    overview_elem = root.find("overview")
    if overview_elem is not None and overview_elem.text:
        metadata["overview"] = overview_elem.text.strip()

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

    # Check if any description field changed (plot or overview)
    description_changed = (
        original["plot"] != translated["plot"]
        or original["overview"] != translated["overview"]
    )

    return {
        "original": original,
        "translated": translated,
        "title_changed": original["title"] != translated["title"],
        "plot_changed": original["plot"] != translated["plot"],
        "overview_changed": original["overview"] != translated["overview"],
        "description_changed": description_changed,
        "ids_preserved": (
            original["tmdb_id"] == translated["tmdb_id"]
            and original["tvdb_id"] == translated["tvdb_id"]
        ),
    }


def setup_series_with_nfos(
    sonarr_container: SonarrClient,
    temp_media_root: Path,
) -> tuple[SeriesManager, list[Path], dict[Path, Path]]:
    """Set up series without requiring initial .nfo files.

    Args:
        sonarr_container: Sonarr client (may or may not have metadata providers enabled)
        temp_media_root: Temporary media root directory

    Returns:
        Tuple of (SeriesManager, empty_nfo_list, empty_backup_mapping)

    Note: This function no longer generates .nfo files initially.
    The integration tests will enable metadata providers and generate .nfo files
    as needed.
    """
    series = SeriesManager(
        sonarr_container,
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
    scan_success = sonarr_container.trigger_disk_scan(series.id)
    if not scan_success:
        series.__exit__(None, None, None)
        raise RuntimeError("Failed to trigger disk scan")
    print("Disk scan command submitted successfully")

    # Wait for Sonarr to process the media files (not .nfo files)
    print("Waiting for Sonarr to process media files...")
    time.sleep(5)

    # Check that basic series structure exists
    if not series_path.exists():
        series.__exit__(None, None, None)
        raise RuntimeError(f"Series directory {series_path} was not created")

    print(f"Series setup complete: {series_path}")

    # Return empty lists for nfo_files and backups since they'll be generated
    # per provider
    return series, [], {}


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
            "TMDB_API_KEY": "test_key_integration_12345",
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
        if comparison["title_changed"] or comparison["description_changed"]:
            successful_translations += 1

            # Verify we have actual translated content, not just fallback
            translated_metadata = comparison["translated"]

            # Check that translated title is not empty (real translation)
            assert translated_metadata["title"], (
                f"Empty translated title in {nfo_file.name}. "
                "This indicates TMDB API returned empty translation data."
            )

            # Check that translated description is not empty (plot or overview)
            has_description = (
                translated_metadata["plot"] or translated_metadata["overview"]
            )
            assert has_description, (
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
        True if either title, plot, or overview contains Chinese characters
    """
    title_translated = any(
        "\u4e00" <= char <= "\u9fff" for char in metadata.get("title", "")
    )
    plot_translated = any(
        "\u4e00" <= char <= "\u9fff" for char in metadata.get("plot", "")
    )
    overview_translated = any(
        "\u4e00" <= char <= "\u9fff" for char in metadata.get("overview", "")
    )
    return title_translated or plot_translated or overview_translated


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
