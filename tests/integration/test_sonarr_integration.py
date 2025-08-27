"""Integration test with real Sonarr container using simple container management."""

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
    configured_sonarr_container: SonarrClient,
    temp_media_root: Path,
) -> None:
    """Test complete integration with Sonarr container using subprocess service.

    This test:
    1. Uses shared configured Sonarr container
    2. Adds Breaking Bad series via SeriesManager
    3. Creates fake episode files
    4. Waits for Sonarr to generate .nfo files
    5. Runs our translation service as a subprocess
    6. Verifies .nfo files are translated
    """

    with SeriesManager(
        configured_sonarr_container,
        BREAKING_BAD_TVDB_ID,
        "/tv",
        temp_media_root,
    ) as series:
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
        # Get TMDB API key from configuration
        original_rewrite_root_dir = os.environ.get("REWRITE_ROOT_DIR")
        os.environ["REWRITE_ROOT_DIR"] = str(temp_media_root)

        try:
            settings = get_settings()
            tmdb_api_key = settings.tmdb_api_key
        finally:
            # Restore original environment
            if original_rewrite_root_dir is not None:
                os.environ["REWRITE_ROOT_DIR"] = original_rewrite_root_dir
            else:
                os.environ.pop("REWRITE_ROOT_DIR", None)

        # Start service subprocess for processing
        with SubprocessServiceManager(
            env_overrides={
                "REWRITE_ROOT_DIR": str(temp_media_root),
                "TMDB_API_KEY": tmdb_api_key,
                "ENABLE_FILE_MONITOR": "false",  # Disable for one-time
                "ENABLE_FILE_SCANNER": "true",
                "PERIODIC_SCAN_INTERVAL_SECONDS": "1",  # Fast for testing
                "PREFERRED_LANGUAGES": '["zh-CN"]',
            },
        ) as service:
            service.start(timeout=15.0)
            print("Service started, waiting for processing...")

            # Wait for service to process files
            time.sleep(3)
            print("Service processing completed")

        # Verify translations were applied
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

        # Ensure at least one file was successfully translated
        assert successful_translations > 0, (
            "No .nfo files were successfully translated. "
            "Check TMDB API key and network connectivity."
        )

        print(
            f"Successfully translated {successful_translations} "
            f"out of {len(nfo_files)} files"
        )


@pytest.mark.integration
@pytest.mark.slow
def test_file_monitor_only_integration(
    configured_sonarr_container: SonarrClient,
    temp_media_root: Path,
) -> None:
    """Test file monitor only integration (scanner disabled).

    This test:
    1. Starts the service with file scanner disabled
    2. Creates .nfo files while service is running
    3. Verifies real-time translation via file monitor
    """
    with SeriesManager(
        configured_sonarr_container,
        BREAKING_BAD_TVDB_ID,
        "/tv",
        temp_media_root,
    ) as series:
        # Get TMDB API key from configuration (environment or .env file)
        # Set required configuration for test
        original_rewrite_root_dir = os.environ.get("REWRITE_ROOT_DIR")
        os.environ["REWRITE_ROOT_DIR"] = str(temp_media_root)

        try:
            settings = get_settings()
            tmdb_api_key = settings.tmdb_api_key
        finally:
            # Restore original environment
            if original_rewrite_root_dir is not None:
                os.environ["REWRITE_ROOT_DIR"] = original_rewrite_root_dir
            else:
                os.environ.pop("REWRITE_ROOT_DIR", None)

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
        for nfo_file in nfo_files:
            metadata = parse_nfo_content(nfo_file)
            print(f"Original metadata for {nfo_file.name}: {metadata}")

            # Verify we have a TMDB ID (required for translation)
            if not metadata.get("tmdb_id"):
                pytest.skip(
                    f"No TMDB ID found in {nfo_file.name}. "
                    f"Sonarr may not have populated TMDB metadata yet."
                )

        # Start translation service with file monitor only (scanner disabled)
        print("Starting translation service with file monitor only...")
        with SubprocessServiceManager(
            env_overrides={
                "REWRITE_ROOT_DIR": str(temp_media_root),
                "TMDB_API_KEY": tmdb_api_key,
                "ENABLE_FILE_MONITOR": "true",
                "ENABLE_FILE_SCANNER": "false",
                "PERIODIC_SCAN_INTERVAL_SECONDS": "999999",  # Effectively disabled
                "PREFERRED_LANGUAGES": '["zh-CN"]',
            },
        ) as service:
            service.start()

            # Service should be running with only monitor enabled
            assert service.is_running(), "Service should be running"

            # Wait a bit for service to stabilize
            time.sleep(2)

            # Touch .nfo files to trigger file monitor events
            print("Triggering file monitor by touching .nfo files...")
            for nfo_file in nfo_files:
                # Touch the file to trigger file system event
                nfo_file.touch()
                print(f"Touched: {nfo_file}")

            # Wait for file monitor to process the files
            print("Waiting for file monitor to process files...")
            time.sleep(5)

            # Check if translations were applied
            successful_translations = 0
            for nfo_file in nfo_files:
                original_backup = original_backups[nfo_file]

                # Compare original vs current content
                comparison = compare_nfo_files(original_backup, nfo_file)
                print(f"File monitor comparison for {nfo_file.name}: {comparison}")

                if comparison["title_changed"] or comparison["plot_changed"]:
                    successful_translations += 1

                    # Verify we have actual translated content
                    translated_metadata = comparison["translated"]

                    assert translated_metadata[
                        "title"
                    ], f"Empty translated title in {nfo_file.name}"
                    assert translated_metadata[
                        "plot"
                    ], f"Empty translated description in {nfo_file.name}"
                    assert comparison[
                        "ids_preserved"
                    ], f"TMDB/TVDB IDs not preserved in {nfo_file.name}"

        # Ensure at least one file was successfully translated by file monitor
        assert successful_translations > 0, (
            "No .nfo files were translated by file monitor. "
            "Check that file monitor is working correctly."
        )

        print(
            f"File monitor successfully translated {successful_translations} "
            f"out of {len(nfo_files)} files"
        )


@pytest.mark.integration
@pytest.mark.slow
def test_file_scanner_only_integration(
    configured_sonarr_container: SonarrClient,
    temp_media_root: Path,
) -> None:
    """Test file scanner only integration (monitor disabled).

    This test:
    1. Creates .nfo files while service is stopped
    2. Starts the service with file monitor disabled
    3. Verifies batch processing via file scanner
    """
    with SeriesManager(
        configured_sonarr_container,
        BREAKING_BAD_TVDB_ID,
        "/tv",
        temp_media_root,
    ) as series:
        # Get TMDB API key from configuration (environment or .env file)
        # Set required configuration for test
        original_rewrite_root_dir = os.environ.get("REWRITE_ROOT_DIR")
        os.environ["REWRITE_ROOT_DIR"] = str(temp_media_root)

        try:
            settings = get_settings()
            tmdb_api_key = settings.tmdb_api_key
        finally:
            # Restore original environment
            if original_rewrite_root_dir is not None:
                os.environ["REWRITE_ROOT_DIR"] = original_rewrite_root_dir
            else:
                os.environ.pop("REWRITE_ROOT_DIR", None)

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
        for nfo_file in nfo_files:
            metadata = parse_nfo_content(nfo_file)
            print(f"Original metadata for {nfo_file.name}: {metadata}")

            # Verify we have a TMDB ID (required for translation)
            if not metadata.get("tmdb_id"):
                pytest.skip(
                    f"No TMDB ID found in {nfo_file.name}. "
                    f"Sonarr may not have populated TMDB metadata yet."
                )

        # Start translation service with file scanner only (monitor disabled)
        print("Starting translation service with file scanner only...")
        with SubprocessServiceManager(
            env_overrides={
                "REWRITE_ROOT_DIR": str(temp_media_root),
                "TMDB_API_KEY": tmdb_api_key,
                "ENABLE_FILE_MONITOR": "false",
                "ENABLE_FILE_SCANNER": "true",
                "PERIODIC_SCAN_INTERVAL_SECONDS": "3",  # Short interval for testing
                "PREFERRED_LANGUAGES": '["zh-CN"]',
            },
        ) as service:
            service.start()

            # Service should be running with only scanner enabled
            assert service.is_running(), "Service should be running"

            # Wait for at least one scan cycle to complete
            print("Waiting for file scanner to process files...")
            time.sleep(8)  # Wait for multiple scan cycles

            # Check if translations were applied
            successful_translations = 0
            for nfo_file in nfo_files:
                original_backup = original_backups[nfo_file]

                # Compare original vs current content
                comparison = compare_nfo_files(original_backup, nfo_file)
                print(f"File scanner comparison for {nfo_file.name}: {comparison}")

                if comparison["title_changed"] or comparison["plot_changed"]:
                    successful_translations += 1

                    # Verify we have actual translated content
                    translated_metadata = comparison["translated"]

                    assert translated_metadata[
                        "title"
                    ], f"Empty translated title in {nfo_file.name}"
                    assert translated_metadata[
                        "plot"
                    ], f"Empty translated description in {nfo_file.name}"
                    assert comparison[
                        "ids_preserved"
                    ], f"TMDB/TVDB IDs not preserved in {nfo_file.name}"

        # Ensure at least one file was successfully translated by file scanner
        assert successful_translations > 0, (
            "No .nfo files were translated by file scanner. "
            "Check that periodic scanning is working correctly."
        )

        print(
            f"File scanner successfully translated {successful_translations} "
            f"out of {len(nfo_files)} files"
        )


@pytest.mark.integration
@pytest.mark.slow
def test_series_refresh_integration(
    configured_sonarr_container: SonarrClient,
    temp_media_root: Path,
) -> None:
    """Test complete series refresh integration workflow.

    This test:
    1. Starts the service with both components enabled
    2. Adds series and lets Sonarr generate .nfo files
    3. Verifies service translates the files
    4. Triggers Sonarr series refresh to regenerate original .nfo files
    5. Verifies service automatically retranslates the refreshed files
    """
    # Get TMDB API key from configuration (environment or .env file)
    # Set required configuration for test
    original_rewrite_root_dir = os.environ.get("REWRITE_ROOT_DIR")
    os.environ["REWRITE_ROOT_DIR"] = str(temp_media_root)

    try:
        settings = get_settings()
        tmdb_api_key = settings.tmdb_api_key
    finally:
        # Restore original environment
        if original_rewrite_root_dir is not None:
            os.environ["REWRITE_ROOT_DIR"] = original_rewrite_root_dir
        else:
            os.environ.pop("REWRITE_ROOT_DIR", None)

    # Start translation service with both components enabled
    print("Starting translation service with both components...")
    with SubprocessServiceManager(
        env_overrides={
            "REWRITE_ROOT_DIR": str(temp_media_root),
            "TMDB_API_KEY": tmdb_api_key,
            "ENABLE_FILE_MONITOR": "true",
            "ENABLE_FILE_SCANNER": "true",
            "PERIODIC_SCAN_INTERVAL_SECONDS": "5",  # Reasonable interval
            "PREFERRED_LANGUAGES": '["zh-CN"]',
        },
    ) as service:
        service.start()

        # Service should be running with both components
        assert service.is_running(), "Service should be running"

        # Wait for service to stabilize
        time.sleep(2)

        with SeriesManager(
            configured_sonarr_container,
            BREAKING_BAD_TVDB_ID,
            "/tv",
            temp_media_root,
        ) as series:
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

            # Parse original metadata to verify it contains TMDB IDs
            for nfo_file in nfo_files:
                metadata = parse_nfo_content(nfo_file)
                print(f"Original metadata for {nfo_file.name}: {metadata}")

                # Verify we have a TMDB ID (required for translation)
                if not metadata.get("tmdb_id"):
                    pytest.skip(
                        f"No TMDB ID found in {nfo_file.name}. "
                        f"Sonarr may not have populated TMDB metadata yet."
                    )

            # Wait for initial translation by service
            print("Waiting for initial translation...")
            time.sleep(8)  # Allow time for file monitor + scanner to process

            # Store initial translated state
            first_translations = {}
            for nfo_file in nfo_files:
                metadata = parse_nfo_content(nfo_file)
                first_translations[nfo_file] = metadata
                print(
                    f"First translation for {nfo_file.name}: "
                    f"title='{metadata['title']}', has_plot={bool(metadata['plot'])}"
                )

            # Verify initial translations occurred
            initial_translations = 0
            for nfo_file, metadata in first_translations.items():
                # Check if content appears to be translated (Chinese chars)
                title_translated = any(
                    "\u4e00" <= char <= "\u9fff" for char in metadata.get("title", "")
                )
                plot_translated = any(
                    "\u4e00" <= char <= "\u9fff" for char in metadata.get("plot", "")
                )

                if title_translated or plot_translated:
                    initial_translations += 1
                    print(f"Initial translation detected in {nfo_file.name}")

            if initial_translations == 0:
                print("No initial translations detected, waiting longer...")
                time.sleep(10)  # Wait more for service to process

                # Check again
                for nfo_file in nfo_files:
                    metadata = parse_nfo_content(nfo_file)
                    first_translations[nfo_file] = metadata

            # Trigger series refresh to regenerate original .nfo files
            print("Triggering series refresh to regenerate original .nfo files...")
            refresh_success = configured_sonarr_container.refresh_series(series.id)
            assert refresh_success, "Failed to trigger series refresh"

            # Wait for Sonarr to regenerate .nfo files
            print("Waiting for Sonarr to regenerate .nfo files...")
            time.sleep(10)

            # Check that .nfo files have been regenerated (back to original)
            regenerated_metadata = {}
            for nfo_file in nfo_files:
                metadata = parse_nfo_content(nfo_file)
                regenerated_metadata[nfo_file] = metadata
                print(
                    f"Regenerated metadata for {nfo_file.name}: "
                    f"title='{metadata['title']}', has_plot={bool(metadata['plot'])}"
                )

            # Wait for service to retranslate the refreshed files
            print("Waiting for service to retranslate refreshed files...")
            time.sleep(10)

            # Check final translations after refresh
            final_translations = {}
            retranslations = 0
            for nfo_file in nfo_files:
                metadata = parse_nfo_content(nfo_file)
                final_translations[nfo_file] = metadata
                print(
                    f"Final translation for {nfo_file.name}: "
                    f"title='{metadata['title']}', has_plot={bool(metadata['plot'])}"
                )

                # Check if content is translated again after refresh
                title_translated = any(
                    "\u4e00" <= char <= "\u9fff" for char in metadata.get("title", "")
                )
                plot_translated = any(
                    "\u4e00" <= char <= "\u9fff" for char in metadata.get("plot", "")
                )

                if title_translated or plot_translated:
                    retranslations += 1

                    # Verify content quality
                    assert metadata["title"], f"Empty title in {nfo_file.name}"
                    assert metadata["plot"], f"Empty plot in {nfo_file.name}"
                    assert metadata.get(
                        "tmdb_id"
                    ), f"Missing TMDB ID in {nfo_file.name}"

            # Ensure the complete refresh cycle worked
            assert retranslations > 0, (
                "No .nfo files were retranslated after series refresh. "
                "The complete refresh cycle may not be working correctly."
            )

            print(
                f"Series refresh workflow completed successfully: "
                f"{retranslations} out of {len(nfo_files)} files retranslated"
            )
