"""Integration test with real Sonarr container using simple container management."""

from pathlib import Path

import pytest

from tests.integration.fixtures.sonarr_client import SonarrClient
from tests.integration.test_helpers import (
    SeriesWithNfos,
    ServiceRunner,
    verify_translations,
)

# Series TVDB IDs for testing
BREAKING_BAD_TVDB_ID = 81189
MING_DYNASTY_TVDB_ID = 300635
EVERY_TREASURE_TELLS_A_STORY_TVDB_ID = 364698
GEN_V_TVDB_ID = 417909


@pytest.mark.integration
@pytest.mark.slow
def test_file_monitor_workflow(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test file monitor-only workflow with real-time NFO file processing.

    This test verifies that the file monitor component can detect and process
    NFO files in real-time when they are created by Sonarr.
    """
    with ServiceRunner(
        temp_media_root,
        {"ENABLE_FILE_SCANNER": "false"},
        startup_pattern="File monitor started",
    ):
        # Service startup waits for "File monitor started" log, so no sleep needed
        with SeriesWithNfos(
            configured_sonarr_container, temp_media_root, BREAKING_BAD_TVDB_ID
        ) as nfo_files:
            verify_translations(
                nfo_files, expected_language="zh", possible_languages=["zh", "en"]
            )


@pytest.mark.integration
@pytest.mark.slow
def test_file_scanner_workflow(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test file scanner-only workflow with periodic directory scanning.

    This test verifies that the file scanner component can discover and process
    existing NFO files through periodic directory scanning.
    """
    with SeriesWithNfos(
        configured_sonarr_container, temp_media_root, BREAKING_BAD_TVDB_ID
    ) as nfo_files:
        with ServiceRunner(temp_media_root, {"ENABLE_FILE_MONITOR": "false"}):
            verify_translations(
                nfo_files, expected_language="zh", possible_languages=["zh", "en"]
            )


@pytest.mark.integration
@pytest.mark.slow
def test_rollback_service_mode(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
    tmp_path: Path,
) -> None:
    """Test rollback service mode that restores original NFO files.

    This test verifies that the rollback service mode can restore original
    NFO content after files have been translated to Chinese.
    """
    # Create backup directory outside media root to avoid interference
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(exist_ok=True)

    with SeriesWithNfos(
        configured_sonarr_container, temp_media_root, BREAKING_BAD_TVDB_ID
    ) as nfo_files:
        # First, translate files to Chinese using rewrite mode with backups enabled
        with ServiceRunner(
            temp_media_root,
            {
                "ORIGINAL_FILES_BACKUP_DIR": str(backup_dir),
            },
        ):
            verify_translations(
                nfo_files, expected_language="zh", possible_languages=["zh", "en"]
            )

        # Then, rollback using rollback service mode
        with ServiceRunner(
            temp_media_root,
            {"SERVICE_MODE": "rollback", "ORIGINAL_FILES_BACKUP_DIR": str(backup_dir)},
        ):
            verify_translations(
                nfo_files, expected_language="en", possible_languages=["zh", "en"]
            )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize(
    "tvdb_id,service_config,expected_language",
    [
        # Translation fallback when preferred language has empty titles (issue #26).
        # Tests Chinese series "大明王朝1566" where some Chinese translations have
        # empty titles but valid descriptions, requiring fallback to complete.
        (MING_DYNASTY_TVDB_ID, {}, "zh"),
        # External ID lookup workflow using TVDB ID to find TMDB ID (issue #29).
        # Tests "Every Treasure Tells a Story" series (TVDB: 364698 -> TMDB: 86965)
        # to verify TMDB ID resolution from TVDB ID when direct TMDB ID unavailable.
        (EVERY_TREASURE_TELLS_A_STORY_TVDB_ID, {}, "zh"),
        # Smart fallback translation merging (issue #50).
        # Tests "Gen V" series where fr-CA and fr-FR translations are merged
        # to create complete French translations avoiding English fallback.
        (GEN_V_TVDB_ID, {"PREFERRED_LANGUAGES": "fr-CA,fr-FR"}, "fr"),
    ],
    ids=["translation-fallback", "external-id-lookup", "smart-fallback-merging"],
)
def test_advanced_translation_scenarios(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
    tvdb_id: int,
    service_config: dict[str, str],
    expected_language: str,
) -> None:
    """Test advanced translation scenarios that require special handling."""
    possible_languages = {"en"}

    # Parse PREFERRED_LANGUAGES from service config if present
    if "PREFERRED_LANGUAGES" in service_config:
        preferred_langs = service_config["PREFERRED_LANGUAGES"].split(",")
        for lang in preferred_langs:
            # Convert language codes like "fr-CA" to base language "fr"
            base_lang = lang.strip().split("-")[0]
            possible_languages.add(base_lang)
    else:
        possible_languages.add("zh")

    with SeriesWithNfos(
        configured_sonarr_container, temp_media_root, tvdb_id
    ) as nfo_files:
        with ServiceRunner(temp_media_root, service_config):
            verify_translations(
                nfo_files,
                expected_language,
                possible_languages=list(possible_languages),
            )
