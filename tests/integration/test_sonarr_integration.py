"""Integration test with real Sonarr container using simple container management."""

import time
from pathlib import Path
from typing import Any

import pytest

from tests.integration.fixtures.series_manager import SeriesManager
from tests.integration.fixtures.sonarr_client import SonarrClient
from tests.integration.test_helpers import (
    count_translations,
    is_translated,
    parse_nfo_content,
    run_service_with_config,
    run_standard_translation_workflow,
    setup_series_with_nfos,
    verify_chinese_translations,
    verify_rollback_results,
    verify_translations,
    wait_and_verify_translations,
)

# Chinese series TVDB ID for "大明王朝1566"
MING_DYNASTY_TVDB_ID = 300635


def get_base_service_config() -> dict[str, str]:
    """Get base service configuration with both file scanner and monitor enabled.

    Returns:
        Base environment configuration dict that individual tests can modify
    """
    return {
        "ENABLE_FILE_MONITOR": "true",
        "ENABLE_FILE_SCANNER": "true",
        "PREFERRED_LANGUAGES": "zh-CN",
    }


def _setup_test_series(
    configured_sonarr_container: SonarrClient,
    temp_media_root: Path,
    tvdb_id: int | None = None,
    episode_configs: list[dict[str, Any]] | None = None,
) -> tuple[SeriesManager, list[Path], dict[Path, dict[str, Any]]]:
    """Set up test series and parse original metadata.

    Args:
        configured_sonarr_container: Configured Sonarr client
        temp_media_root: Temporary media root directory
        tvdb_id: TVDB ID for the series (defaults to Breaking Bad)
        episode_configs: List of episode configurations

    Returns:
        Tuple of (series, nfo_files, original_metadata)
    """
    # Set up series with .nfo files using generalized helper
    series, nfo_files, original_backups = setup_series_with_nfos(
        configured_sonarr_container, temp_media_root, tvdb_id, episode_configs
    )

    # Parse original metadata for comparison
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

    return series, nfo_files, original_metadata


def _cleanup_series(
    series: SeriesManager, configured_sonarr_container: SonarrClient
) -> None:
    """Clean up test series safely.

    Args:
        series: Series manager to clean up
        configured_sonarr_container: Configured Sonarr client (unused - cleanup handled by SeriesManager)
    """
    # SeriesManager.__exit__ handles the cleanup automatically
    series.__exit__(None, None, None)


@pytest.mark.integration
@pytest.mark.slow
def test_file_monitor_only(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test file monitor functionality with file scanner disabled.

    This test verifies that the file monitor component can detect .nfo file changes
    and trigger translations when files are touched, while the file scanner remains
    disabled. This tests the inotify-based file watching capabilities.

    Args:
        temp_media_root: Temporary media root directory
        configured_sonarr_container: Configured Sonarr client
    """
    service_config = get_base_service_config()
    service_config.update(
        {
            "ENABLE_FILE_SCANNER": "false",
        }
    )

    series, nfo_files, original_metadata = _setup_test_series(
        configured_sonarr_container, temp_media_root
    )

    try:
        # Run standard workflow with touch_files behavior
        run_standard_translation_workflow(
            temp_media_root, service_config, nfo_files, "touch_files"
        )

        # Verify translations were applied
        original_backups = {nfo: nfo.with_suffix(".nfo.original") for nfo in nfo_files}
        verify_translations(nfo_files, original_backups)

    finally:
        _cleanup_series(series, configured_sonarr_container)


@pytest.mark.integration
@pytest.mark.slow
def test_file_scanner_only(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test file scanner functionality with file monitor disabled.

    This test verifies that the file scanner component can periodically scan
    for .nfo files and trigger translations based on the scanning interval,
    while the file monitor remains disabled. This tests the periodic scanning
    capabilities for environments where file system events are unreliable.

    Args:
        temp_media_root: Temporary media root directory
        configured_sonarr_container: Configured Sonarr client
    """
    service_config = get_base_service_config()
    service_config.update(
        {
            "ENABLE_FILE_MONITOR": "false",
            "PERIODIC_SCAN_INTERVAL_SECONDS": "3",
        }
    )

    series, nfo_files, original_metadata = _setup_test_series(
        configured_sonarr_container, temp_media_root
    )

    try:
        # Run standard workflow with wait_scanning behavior
        run_standard_translation_workflow(
            temp_media_root, service_config, nfo_files, "wait_scanning"
        )

        # Verify translations were applied
        original_backups = {nfo: nfo.with_suffix(".nfo.original") for nfo in nfo_files}
        verify_translations(nfo_files, original_backups)

    finally:
        _cleanup_series(series, configured_sonarr_container)


@pytest.mark.integration
@pytest.mark.slow
def test_full_workflow_with_series_refresh(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test complete workflow with both components enabled and series refresh handling.

    This test verifies that when both file monitor and scanner are enabled, the service
    can handle initial translations and properly retranslate files when Sonarr performs
    a series refresh that regenerates original .nfo files. This tests the service's
    ability to detect and retranslate files that have been reverted by Sonarr.

    Args:
        temp_media_root: Temporary media root directory
        configured_sonarr_container: Configured Sonarr client
    """
    service_config = get_base_service_config()
    service_config.update(
        {
            "PERIODIC_SCAN_INTERVAL_SECONDS": "5",
        }
    )

    series, nfo_files, original_metadata = _setup_test_series(
        configured_sonarr_container, temp_media_root
    )

    try:
        # Start translation service with both components
        print("Starting translation service with both components...")
        with run_service_with_config(temp_media_root, service_config) as service:
            assert service.is_running(), "Service should be running"

            # Wait for initial translation
            print("Waiting for initial translation...")
            time.sleep(8)

            # Check initial translations
            initial_translations = count_translations(nfo_files)

            if initial_translations == 0:
                print("No initial translations detected, waiting longer...")
                time.sleep(10)

            # Trigger series refresh to regenerate original .nfo files
            print("Triggering series refresh to regenerate original .nfo files...")
            refresh_success = configured_sonarr_container.refresh_series(series.id)
            assert refresh_success, "Failed to trigger series refresh"

            # Wait for Sonarr to regenerate and service to retranslate
            print("Waiting for service to retranslate refreshed files...")
            time.sleep(20)

            # Verify retranslations
            retranslations = count_translations(nfo_files)

            # Ensure translated content is not empty
            for nfo_file in nfo_files:
                metadata = parse_nfo_content(nfo_file)
                if is_translated(metadata):
                    assert metadata["title"], f"Empty title in {nfo_file.name}"
                    assert metadata["plot"], f"Empty plot in {nfo_file.name}"

            assert (
                retranslations > 0
            ), "No .nfo files were retranslated after series refresh"
            print(f"Series refresh: {retranslations}/{len(nfo_files)} retranslated")

    finally:
        _cleanup_series(series, configured_sonarr_container)


@pytest.mark.integration
@pytest.mark.slow
def test_rollback_mechanism(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test rollback mechanism when service is stopped and files are regenerated.

    This test verifies that when the translation service is stopped and Sonarr
    regenerates .nfo files (e.g., during series refresh), the files are restored
    to their original English state without translated content. This ensures that
    stopping the service allows users to revert to original metadata.

    Args:
        temp_media_root: Temporary media root directory
        configured_sonarr_container: Configured Sonarr client
    """
    service_config = get_base_service_config()
    service_config.update(
        {
            "PERIODIC_SCAN_INTERVAL_SECONDS": "5",
        }
    )

    series, nfo_files, original_metadata = _setup_test_series(
        configured_sonarr_container, temp_media_root
    )

    try:
        # Rollback test workflow - translate, stop service, refresh, verify rollback
        print("Starting rollback test workflow...")

        with run_service_with_config(temp_media_root, service_config) as service:
            assert service.is_running(), "Service should be running"

            # Wait for initial translation
            print("Waiting for initial translation...")
            time.sleep(8)

            # Verify translations occurred
            translations = wait_and_verify_translations(nfo_files, 0, min_expected=1)
            print(f"Initial translations: {translations}/{len(nfo_files)} translated")

        # Service is now stopped - verify service shutdown
        print("Service stopped - proceeding with rollback test...")

        # Delete existing .nfo files to force Sonarr to regenerate them
        print("Deleting existing .nfo files to force regeneration...")
        for nfo_file in nfo_files:
            if nfo_file.exists():
                nfo_file.unlink()
                print(f"Deleted: {nfo_file}")

        # Trigger series refresh to regenerate original .nfo files
        print("Triggering series refresh to restore original metadata...")
        refresh_success = configured_sonarr_container.refresh_series(series.id)
        assert refresh_success, "Failed to trigger series refresh for rollback"

        # Wait for Sonarr to regenerate original files
        print("Waiting for Sonarr to restore original files...")
        time.sleep(15)

        # Verify rollback - files should match original metadata
        rollback_verified = verify_rollback_results(nfo_files, original_metadata)

        assert rollback_verified > 0, "No .nfo files were successfully rolled back"
        print(
            f"Rollback successful: {rollback_verified}/{len(nfo_files)} files restored"
        )

    finally:
        _cleanup_series(series, configured_sonarr_container)


@pytest.mark.integration
@pytest.mark.slow
def test_chinese_series_translation(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test Chinese series translation with original language detection.

    This test verifies that the service can properly translate Chinese content
    using the "大明王朝1566" series as a test case. It tests the original language
    detection feature where the service should detect that the content is originally
    in Chinese and translate it to the preferred language. This ensures proper
    handling of non-English source content.

    Args:
        temp_media_root: Temporary media root directory
        configured_sonarr_container: Configured Sonarr client
    """
    service_config = get_base_service_config()
    service_config.update(
        {
            "ENABLE_FILE_SCANNER": "false",
        }
    )

    episode_configs = [
        {"season": 1, "episode": 1, "title": "Episode 1"},
        {"season": 1, "episode": 2, "title": "Episode 2"},
    ]

    series, nfo_files, original_metadata = _setup_test_series(
        configured_sonarr_container,
        temp_media_root,
        MING_DYNASTY_TVDB_ID,
        episode_configs,
    )

    try:
        print("Testing Chinese series translation for 大明王朝1566...")
        expected_title_text = "大明王朝"

        # Start translation service
        print("Starting translation service with Chinese preferences...")
        with run_service_with_config(temp_media_root, service_config) as service:
            assert service.is_running(), "Service should be running"

            # Touch files to trigger file monitor events
            print("Triggering file monitor by touching .nfo files...")
            for nfo_file in nfo_files:
                nfo_file.touch()
                print(f"Touched: {nfo_file}")

            print("Waiting for file monitor to process files...")
            time.sleep(8)  # Give more time for translation

            # Verify Chinese translations with specific assertions
            translated_count = verify_chinese_translations(
                nfo_files, original_metadata, expected_title_text
            )

            # Ensure at least one file was translated
            assert translated_count > 0, (
                "No .nfo files were successfully translated with Chinese content. "
                "This may indicate an issue with the original language detection "
                "feature."
            )

            print(
                f"Successfully translated {translated_count} out of "
                f"{len(nfo_files)} files with Chinese content"
            )

    finally:
        _cleanup_series(series, configured_sonarr_container)
