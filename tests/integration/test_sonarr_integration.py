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


def trigger_file_monitor_events(nfo_files: list[Path]) -> None:
    """Trigger file monitor events by touching NFO files.

    Args:
        nfo_files: List of NFO files to touch
    """
    for nfo_file in nfo_files:
        nfo_file.touch()


@pytest.mark.integration
@pytest.mark.slow
def test_file_monitor_workflow(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test file monitor-only workflow with real-time NFO file processing.

    This test verifies that the file monitor component can detect and process
    NFO files in real-time when they are modified (touched).
    """
    with SeriesWithNfos(
        configured_sonarr_container, temp_media_root, BREAKING_BAD_TVDB_ID
    ) as (nfo_files, series_id):
        with ServiceRunner(
            temp_media_root, {"ENABLE_FILE_SCANNER": "false"}
        ) as service:
            assert service.is_running()
            trigger_file_monitor_events(nfo_files)
            verify_translations(nfo_files, expect_chinese=True)


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
    ) as (nfo_files, series_id):
        with ServiceRunner(
            temp_media_root, {"ENABLE_FILE_MONITOR": "false"}
        ) as service:
            assert service.is_running()
            verify_translations(nfo_files, expect_chinese=True)


@pytest.mark.integration
@pytest.mark.slow
def test_rollback_mechanism(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test rollback mechanism when service stops and Sonarr regenerates original files.

    This test verifies that when the translation service is stopped, Sonarr can
    regenerate the original NFO files, effectively rolling back the translations.
    """
    with SeriesWithNfos(
        configured_sonarr_container, temp_media_root, BREAKING_BAD_TVDB_ID
    ) as (nfo_files, series_id):
        with ServiceRunner(temp_media_root, {}) as service:
            assert service.is_running()
            verify_translations(nfo_files, expect_chinese=True)

        for nfo_file in nfo_files:
            if nfo_file.exists():
                nfo_file.unlink()

        assert configured_sonarr_container.refresh_series(series_id)

        verify_translations(nfo_files, expect_chinese=False)


@pytest.mark.integration
@pytest.mark.slow
def test_translation_fallback_for_empty_titles(
    temp_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test translation fallback when preferred language has empty titles.

    This test verifies the original language detection feature (issue #26) that
    correctly handles series with incomplete preferred language translations by
    falling back to the original language when titles are empty.

    Specifically tests Chinese series "大明王朝1566" where some Chinese translations
    have empty titles but valid descriptions, requiring fallback to complete
    translations.
    """
    with SeriesWithNfos(
        configured_sonarr_container, temp_media_root, MING_DYNASTY_TVDB_ID
    ) as (nfo_files, series_id):
        with ServiceRunner(temp_media_root, {}) as service:
            assert service.is_running()
            verify_translations(nfo_files, expect_chinese=True)
