"""Integration test with real Sonarr container using simple container management."""

import time
from pathlib import Path

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
    verify_translations,
    wait_and_verify_translations,
    wait_for_nfo_files,
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
            refresh_success = configured_sonarr_container.refresh_series(series_id)
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
        refresh_success = configured_sonarr_container.refresh_series(series_id)
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


# Chinese series TVDB ID for "大明王朝1566"
MING_DYNASTY_TVDB_ID = 300635


@pytest.mark.integration
@pytest.mark.slow
def test_chinese_series_translation(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test translation of Chinese series "大明王朝1566" for Chinese titles.

    This test verifies that the original language detection feature correctly handles
    Chinese content when preferred language translation has incomplete data.
    """
    print("Testing Chinese series translation for 大明王朝1566...")

    # Set up the specific Chinese series
    series = SeriesManager(
        configured_sonarr_container,
        MING_DYNASTY_TVDB_ID,
        "/tv",
        temp_media_root,
    )

    with series:
        print(f"Added series: {series.title} (TVDB: {series.tvdb_id})")

        # Create fake episode files to trigger Sonarr processing
        print("Creating fake episode files...")
        episode_files = [
            create_fake_episode_file(temp_media_root, series.slug, 1, 1, "Episode 1"),
            create_fake_episode_file(temp_media_root, series.slug, 1, 2, "Episode 2"),
        ]

        for episode_file in episode_files:
            print(f"Created: {episode_file}")

        # Trigger disk scan to detect episode files
        print("Triggering disk scan to detect episode files...")
        series_path = temp_media_root / series.slug
        scan_success = configured_sonarr_container.trigger_disk_scan(series.id)
        if not scan_success:
            pytest.fail("Failed to trigger disk scan")
        print("Disk scan command submitted successfully")

        # Wait for .nfo files to be generated
        print("Waiting for .nfo files to be generated...")
        episode_count = len(episode_files)
        expected_nfo_count = episode_count + 1  # episodes + series
        nfo_files = wait_for_nfo_files(series_path, expected_nfo_count, timeout=15.0)

        if not nfo_files:
            # List what files exist for debugging
            all_files = list(series_path.rglob("*")) if series_path.exists() else []
            print(f"No .nfo files found. All files in {series_path}: {all_files}")
            pytest.fail(
                "Sonarr did not generate .nfo files within timeout after disk scan"
            )

        print(f"Found .nfo files: {nfo_files}")

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

        # Configure service for Chinese translation
        service_config = {
            "ENABLE_FILE_MONITOR": "true",
            "ENABLE_FILE_SCANNER": "false",
            "PREFERRED_LANGUAGES": "zh-CN",  # Specifically test Chinese
            "PERIODIC_SCAN_INTERVAL_SECONDS": "999999",
        }

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

            # Verify translations occurred
            print("Verifying Chinese translations...")
            translated_count = 0

            for nfo_file in nfo_files:
                current_metadata = parse_nfo_content(nfo_file)
                original = original_metadata[nfo_file]

                print(f"Translation check for {nfo_file.name}:")
                print(f"  Original title: {original.get('title')}")
                print(f"  Current title: {current_metadata.get('title')}")

                # Check if translation occurred
                if current_metadata.get("title") != original.get(
                    "title"
                ) or current_metadata.get("plot") != original.get("plot"):

                    translated_count += 1

                    # Verify we have a non-empty Chinese title
                    chinese_title = current_metadata.get("title", "")
                    assert chinese_title, f"Empty translated title in {nfo_file.name}"

                    # For tvshow.nfo, specifically check for the Chinese title
                    if nfo_file.name == "tvshow.nfo":
                        assert "大明王朝" in chinese_title, (
                            f"Chinese series title '大明王朝' not found in "
                            f"translated title: {chinese_title}"
                        )
                        print(f"✅ Chinese title correctly translated: {chinese_title}")

                    # Verify plot has content
                    chinese_plot = current_metadata.get("plot", "")
                    assert chinese_plot, f"Empty translated plot in {nfo_file.name}"

                    # Verify IDs are preserved
                    assert current_metadata.get("tmdb_id") == original.get(
                        "tmdb_id"
                    ), f"TMDB ID not preserved in {nfo_file.name}"

                    print(f"✅ Successfully translated {nfo_file.name}")
                else:
                    print(f"⚠️ No translation changes detected in {nfo_file.name}")

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


def test_external_id_lookup_chinese_series(integration_environment):
    """Test external ID lookup with real Chinese series '如果国宝会说话' (TVDB ID: 364698).
    
    This test verifies that the external ID lookup functionality works correctly
    by processing a series .nfo file that contains only TVDB ID (no TMDB ID).
    """
    temp_media_root, sonarr_client, service_config = integration_environment

    with SeriesManager(
        sonarr_client=sonarr_client,
        tvdb_id=364698,  # "如果国宝会说话"
        root_folder="/tv",
        temp_media_root=temp_media_root,
    ) as series:
        print(f"Added series: {series.series_title}")

        # Wait for Sonarr to create the directory structure and potentially .nfo files
        wait_for_nfo_files(series.local_path, expected_count=1, timeout=30)

        # Get the tvshow.nfo file path
        tvshow_nfo = series.local_path / "tvshow.nfo"
        assert tvshow_nfo.exists(), f"tvshow.nfo not found at {tvshow_nfo}"

        # Read original content
        original_content = parse_nfo_content(tvshow_nfo)
        print(f"Original title: {original_content.get('title')}")
        print(f"Original TMDB ID: {original_content.get('tmdb_id')}")

        # Create a test .nfo file with only TVDB ID (no TMDB ID) to simulate external ID lookup
        test_nfo_content = f"""<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<tvshow>
    <title>如果国宝会说话</title>
    <uniqueid type="tvdb" default="true">364698</uniqueid>
    <plot>A documentary series about Chinese cultural treasures and artifacts.</plot>
    <genre>Documentary</genre>
    <runtime>15</runtime>
    <status>Continuing</status>
</tvshow>"""

        # Write the test content (without TMDB ID)
        tvshow_nfo.write_text(test_nfo_content, encoding="utf-8")
        print("Created test .nfo file with only TVDB ID")

        # Configure service for external ID processing
        test_config = service_config.copy()
        test_config.update({
            "ENABLE_FILE_MONITOR": "true",
            "ENABLE_FILE_SCANNER": "false",
            "PERIODIC_SCAN_INTERVAL_SECONDS": "999999",
        })

        with run_service_with_config(test_config, temp_media_root):
            print("Service started, triggering file monitor...")
            
            # Touch the file to trigger file monitor
            tvshow_nfo.touch()
            print(f"Touched: {tvshow_nfo}")

            # Wait for processing
            time.sleep(10)

            # Verify external ID lookup and translation occurred
            processed_content = parse_nfo_content(tvshow_nfo)
            print(f"Processed title: {processed_content.get('title')}")
            print(f"Processed TMDB ID: {processed_content.get('tmdb_id')}")

            # Verify that external ID lookup worked
            assert processed_content.get('tmdb_id'), (
                "TMDB ID should be populated via external ID lookup"
            )

            # Verify the file was processed (title should be different or content enhanced)
            # Since this is a Chinese series, it might get translated if Chinese is in preferred languages
            processed_title = processed_content.get('title', '')
            processed_plot = processed_content.get('plot', '')
            
            assert processed_title, "Processed title should not be empty"
            assert processed_plot, "Processed plot should not be empty"
            
            print(f"✅ External ID lookup successful for Chinese series")
            print(f"✅ Final title: {processed_title}")
            print(f"✅ TMDB ID discovered: {processed_content.get('tmdb_id')}")
