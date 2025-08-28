"""Integration test with real Sonarr container using simple container management."""

import time
from pathlib import Path

import pytest

from tests.integration.fixtures.sonarr_client import SonarrClient
from tests.integration.test_helpers import (
    count_translations,
    is_translated,
    metadata_matches,
    parse_nfo_content,
    run_service_with_config,
    verify_translations,
    wait_and_verify_translations,
)


@pytest.mark.parametrize(
    "service_config,test_behavior",
    [
        pytest.param(
            {
                "ENABLE_FILE_MONITOR": "true",
                "ENABLE_FILE_SCANNER": "false",
                "PERIODIC_SCAN_INTERVAL_SECONDS": "999999",
            },
            "touch_files",
            id="file_monitor_only",
        ),
        pytest.param(
            {
                "ENABLE_FILE_MONITOR": "false",
                "ENABLE_FILE_SCANNER": "true",
                "PERIODIC_SCAN_INTERVAL_SECONDS": "3",
            },
            "wait_scanning",
            id="file_scanner_only",
        ),
        pytest.param(
            {
                "ENABLE_FILE_MONITOR": "true",
                "ENABLE_FILE_SCANNER": "true",
                "PERIODIC_SCAN_INTERVAL_SECONDS": "5",
            },
            "full_with_refresh",
            id="series_refresh",
        ),
        pytest.param(
            {
                "ENABLE_FILE_MONITOR": "true",
                "ENABLE_FILE_SCANNER": "true",
                "PERIODIC_SCAN_INTERVAL_SECONDS": "5",
            },
            "rollback_test",
            id="rollback_mechanism",
        ),
    ],
)
@pytest.mark.integration
@pytest.mark.slow
def test_integration_workflow(
    prepared_series_with_nfos: tuple[Path, list[Path], dict[Path, Path], int],
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
    service_config: dict[str, str],
    test_behavior: str,
) -> None:
    """Test integration workflows with different service configurations.

    Args:
        prepared_series_with_nfos: Series setup with .nfo files, backups, and series ID
        temp_media_root: Temporary media root directory
        configured_sonarr_container: Configured Sonarr client
        service_config: Service configuration overrides
        test_behavior: Test behavior type
    """
    series_path, nfo_files, original_backups, series_id = prepared_series_with_nfos

    if test_behavior == "full_with_refresh":
        # Full workflow with series refresh - start service first
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
            refresh_success = configured_sonarr_container.refresh_metadata(series_id)
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

    elif test_behavior == "rollback_test":
        # Rollback test workflow - translate, stop service, refresh, verify rollback
        print("Starting rollback test workflow...")

        # Store original metadata before any translation
        print("Storing original metadata for rollback verification...")
        original_metadata = {}
        for nfo_file in nfo_files:
            original_metadata[nfo_file] = parse_nfo_content(nfo_file)

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
        refresh_success = configured_sonarr_container.refresh_metadata(series_id)
        assert refresh_success, "Failed to trigger series refresh for rollback"

        # Wait for Sonarr to regenerate original files
        print("Waiting for Sonarr to restore original files...")
        time.sleep(15)

        # Verify rollback - files should match original metadata
        print("Verifying rollback to original metadata...")
        rollback_verified = 0
        for nfo_file in nfo_files:
            current_metadata = parse_nfo_content(nfo_file)
            original = original_metadata[nfo_file]

            if metadata_matches(current_metadata, original):
                rollback_verified += 1
                print(f"✅ Rollback verified for {nfo_file.name}")
            else:
                print(f"❌ Rollback failed for {nfo_file.name}")
                print(f"   Original title: {original.get('title')}")
                print(f"   Current title: {current_metadata.get('title')}")

        assert rollback_verified > 0, "No .nfo files were successfully rolled back"
        print(
            f"Rollback successful: {rollback_verified}/{len(nfo_files)} files restored"
        )

    else:
        # Standard workflow - start service and test
        print(f"Starting service with {test_behavior} configuration...")
        with run_service_with_config(temp_media_root, service_config) as service:
            assert service.is_running(), "Service should be running"

            if test_behavior == "touch_files":
                # Touch files to trigger file monitor events
                print("Triggering file monitor by touching .nfo files...")
                for nfo_file in nfo_files:
                    nfo_file.touch()
                    print(f"Touched: {nfo_file}")

                print("Waiting for file monitor to process files...")
                time.sleep(5)

            elif test_behavior == "wait_scanning":
                # Wait for file scanner to process
                print("Waiting for file scanner to process files...")
                time.sleep(8)

            # Verify translations were applied
            verify_translations(nfo_files, original_backups)
