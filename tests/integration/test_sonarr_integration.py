"""Integration test with real Sonarr container using simple container management."""

import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.rewrite_service import RewriteService
from tests.integration.fixtures.sonarr_client import SonarrClient


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


# Breaking Bad TVDB ID (well-known series with good metadata)
BREAKING_BAD_TVDB_ID = 81189


@pytest.mark.integration
@pytest.mark.slow
def test_sonarr_container_integration(
    sonarr_container: SonarrClient,
    temp_media_root: Path,
) -> None:
    """Test complete integration with Sonarr container.

    This test:
    1. Uses our simple container manager to start a Sonarr container
    2. Adds Breaking Bad series via API
    3. Creates fake episode files
    4. Waits for Sonarr to generate .nfo files
    5. Runs our translation service
    6. Verifies .nfo files are translated
    """

    try:
        # Add Breaking Bad series to Sonarr
        print("Adding Breaking Bad series to Sonarr...")
        series_data = sonarr_container.add_series(
            tvdb_id=BREAKING_BAD_TVDB_ID,
            root_folder="/tv",
        )
        series_id = series_data["id"]
        series_slug = series_data["titleSlug"]

        print(f"Added series: {series_data['title']} (ID: {series_id})")

        # Configure metadata settings to enable NFO generation
        print("Configuring metadata settings...")
        metadata_config_success = sonarr_container.configure_metadata_settings()
        assert metadata_config_success, "Failed to configure metadata settings"

        # Create fake episode files to trigger Sonarr processing
        print("Creating fake episode files...")
        episode_files = [
            create_fake_episode_file(temp_media_root, series_slug, 1, 1, "Pilot"),
            create_fake_episode_file(
                temp_media_root, series_slug, 1, 2, "Cat's in the Bag"
            ),
        ]

        for episode_file in episode_files:
            print(f"Created: {episode_file}")

        # Trigger disk scan to detect episode files
        print("Triggering disk scan to detect episode files...")
        series_path = temp_media_root / series_slug
        scan_success = sonarr_container.trigger_disk_scan(series_id)
        assert scan_success, "Failed to trigger disk scan"
        print("Disk scan command submitted successfully")

        # Wait for .nfo files to be generated
        print("Waiting for .nfo files to be generated...")
        nfo_files = wait_for_nfo_files(series_path, timeout=10.0)

        if not nfo_files:
            # List what files exist for debugging
            all_files = list(series_path.rglob("*")) if series_path.exists() else []
            print(f"No .nfo files found. All files in {series_path}: {all_files}")
            pytest.fail(
                "Sonarr did not generate .nfo files within timeout after disk scan"
            )

        print(f"Found .nfo files: {nfo_files}")

        # Backup original .nfo files for comparison
        original_backups = {}
        for nfo_file in nfo_files:
            backup_path = nfo_file.with_suffix(".nfo.original")
            shutil.copy2(nfo_file, backup_path)
            original_backups[nfo_file] = backup_path

        # Parse original metadata to verify it contains TMDB IDs
        original_metadata = {}
        for nfo_file in nfo_files:
            metadata = parse_nfo_content(nfo_file)
            original_metadata[nfo_file] = metadata
            print(f"Original metadata for {nfo_file.name}: {metadata}")

            # Verify we have a TMDB ID (required for translation)
            if not metadata.get("tmdb_id"):
                pytest.skip(
                    f"No TMDB ID found in {nfo_file.name}. "
                    f"Sonarr may not have populated TMDB metadata yet."
                )

        # Setup our translation service
        print("Setting up translation service...")
        with tempfile.TemporaryDirectory(prefix="translation_test_") as temp_dir:
            temp_path = Path(temp_dir)

            settings = Settings(
                rewrite_root_dir=temp_media_root,
                preferred_languages="zh-CN",  # Chinese translation
                periodic_scan_interval_seconds=1,  # Fast for testing
                original_files_backup_dir=temp_path / "backups",
                cache_dir=temp_path / "cache",
            )

            # Run translation service (one-time processing)
            service = RewriteService(settings)

            # Process each .nfo file individually
            processed_files = []
            for nfo_file in nfo_files:
                print(f"Processing {nfo_file}...")
                result = service.metadata_processor.process_file(nfo_file)
                processed_files.append((nfo_file, result))
                print(f"Processing result: {result}")

            service.stop()  # Cleanup resources

        # Verify translations were applied
        print("Verifying translations...")
        successful_translations = 0

        for nfo_file, process_result in processed_files:
            original_backup = original_backups[nfo_file]

            if process_result.success:
                successful_translations += 1

                # Compare original vs translated content
                comparison = compare_nfo_files(original_backup, nfo_file)
                print(f"Comparison for {nfo_file.name}: {comparison}")

                # Verify translation occurred
                assert (
                    comparison["title_changed"] or comparison["plot_changed"]
                ), f"No translation changes detected in {nfo_file.name}"

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

                # Verify selected language
                assert process_result.selected_language == "zh-CN", (
                    f"Expected Chinese translation, got: "
                    f"{process_result.selected_language}"
                )

            else:
                print(
                    f"Translation failed for {nfo_file.name}: {process_result.message}"
                )

        # Ensure at least one file was successfully translated
        assert successful_translations > 0, (
            "No .nfo files were successfully translated. "
            "Check TMDB API key and network connectivity."
        )

        print(
            f"Successfully translated {successful_translations} "
            f"out of {len(nfo_files)} files"
        )

    finally:
        # Container cleanup is handled by the fixture
        pass
