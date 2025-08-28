"""Integration test with real Sonarr container using simple container management."""

import time
from pathlib import Path
from typing import Any

import pytest

from tests.integration.fixtures.series_manager import SeriesManager
from tests.integration.fixtures.sonarr_client import SonarrClient
from tests.integration.test_helpers import (
    count_translations,
    create_fake_episode_file,
    is_translated,
    metadata_matches,
    parse_nfo_content,
    run_service_with_config,
    run_standard_translation_workflow,
    setup_series_with_nfos,
    verify_chinese_translations,
    verify_rollback_results,
    verify_translations,
    wait_and_verify_translations,
    wait_for_nfo_files,
)

# Chinese series TVDB ID for "大明王朝1566"
MING_DYNASTY_TVDB_ID = 300635


@pytest.mark.parametrize(
    "service_config,test_behavior,series_config",
    [
        pytest.param(
            {
                "ENABLE_FILE_MONITOR": "true",
                "ENABLE_FILE_SCANNER": "false",
                "PERIODIC_SCAN_INTERVAL_SECONDS": "999999",
            },
            "touch_files",
            None,  # Use default Breaking Bad series
            id="file_monitor_only",
        ),
        pytest.param(
            {
                "ENABLE_FILE_MONITOR": "false",
                "ENABLE_FILE_SCANNER": "true",
                "PERIODIC_SCAN_INTERVAL_SECONDS": "3",
            },
            "wait_scanning",
            None,
            id="file_scanner_only",
        ),
        pytest.param(
            {
                "ENABLE_FILE_MONITOR": "true",
                "ENABLE_FILE_SCANNER": "true",
                "PERIODIC_SCAN_INTERVAL_SECONDS": "5",
            },
            "full_with_refresh",
            None,
            id="series_refresh",
        ),
        pytest.param(
            {
                "ENABLE_FILE_MONITOR": "true",
                "ENABLE_FILE_SCANNER": "true",
                "PERIODIC_SCAN_INTERVAL_SECONDS": "5",
            },
            "rollback_test",
            None,
            id="rollback_mechanism",
        ),
        pytest.param(
            {
                "ENABLE_FILE_MONITOR": "true",
                "ENABLE_FILE_SCANNER": "false",
                "PREFERRED_LANGUAGES": "zh-CN",
                "PERIODIC_SCAN_INTERVAL_SECONDS": "999999",
            },
            "chinese_translation",
            {
                "tvdb_id": MING_DYNASTY_TVDB_ID,  # Ming Dynasty TVDB ID
                "expected_title_text": "大明王朝",
                "episode_configs": [
                    {"season": 1, "episode": 1, "title": "Episode 1"},
                    {"season": 1, "episode": 2, "title": "Episode 2"},
                ],
            },
            id="chinese_translation",
        ),
    ],
)
@pytest.mark.integration
@pytest.mark.slow
def test_integration_workflow(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
    service_config: dict[str, str],
    test_behavior: str,
    series_config: dict[str, Any] | None,
) -> None:
    """Test integration workflows with different service configurations.

    Args:
        temp_media_root: Temporary media root directory
        configured_sonarr_container: Configured Sonarr client
        service_config: Service configuration overrides
        test_behavior: Test behavior type
        series_config: Optional series-specific configuration
    """
    # Extract series configuration if provided
    tvdb_id = series_config.get("tvdb_id") if series_config else None
    episode_configs = series_config.get("episode_configs") if series_config else None
    
    # Set up series with .nfo files using generalized helper
    series, nfo_files, original_backups = setup_series_with_nfos(
        configured_sonarr_container, temp_media_root, tvdb_id, episode_configs
    )

    try:
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

        # Execute test behavior specific workflows
        if test_behavior == "chinese_translation":
            print("Testing Chinese series translation for 大明王朝1566...")
            expected_title_text = series_config["expected_title_text"]
            
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

        elif test_behavior == "full_with_refresh":
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

        elif test_behavior == "rollback_test":
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

        else:
            # Standard workflow for touch_files and wait_scanning
            run_standard_translation_workflow(temp_media_root, service_config, nfo_files, test_behavior)
            
            # Verify translations were applied using existing helper
            verify_translations(nfo_files, original_backups)
            
    finally:
        # Clean up series
        try:
            configured_sonarr_container.remove_series(series.id)
        except Exception as e:
            print(f"Warning: Failed to clean up series {series.id}: {e}")
        finally:
            series.__exit__(None, None, None)


