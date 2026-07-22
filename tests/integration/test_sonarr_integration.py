"""Integration test with real Sonarr container using simple container management."""

from pathlib import Path

import pytest

from tests.integration.fixtures.series_manager import SeriesManager
from tests.integration.fixtures.sonarr_client import SonarrClient
from tests.integration.test_helpers import (
    SeriesWithNfos,
    ServiceRunner,
    create_fake_multi_episode_file,
    parse_nfo_content,
    verify_images,
    verify_translations,
    wait_for_nfo_files,
)


def season_poster_image_filenames(season_count: int, with_specials: bool) -> list[str]:
    """Generate expected season poster image filenames for given season count.

    Args:
        season_count: Total number of seasons in the series
        with_specials: Whether to include specials season poster

    Returns:
        List of expected season poster image filenames
    """
    filenames: list[str] = []
    if with_specials:
        filenames.append("season-specials-poster.jpg")
    filenames.extend(
        f"season{season_num:02d}-poster.jpg"
        for season_num in range(1, season_count + 1)
    )
    return filenames


# Series TVDB IDs for testing
BREAKING_BAD_TVDB_ID = 81189
BREAKING_BAD_IMAGES = [
    "poster.jpg",
    "clearlogo.png",
    *season_poster_image_filenames(5, with_specials=True),
]
MING_DYNASTY_TVDB_ID = 300635
MING_DYNASTY_IMAGES = [
    "poster.jpg",
]  # Sonarr only generates series poster image
EVERY_TREASURE_TELLS_A_STORY_TVDB_ID = 364698
EVERY_TREASURE_TELLS_A_STORY_IMAGES = [
    "poster.jpg",
]  # Sonarr only generates series poster image
CAPE_FEAR_TVDB_ID = 456813
CAPE_FEAR_EPISODE_TVDB_ID = 11593814
GEN_V_TVDB_ID = 417909
GEN_V_IMAGES = [
    "poster.jpg",
    "clearlogo.png",
    *season_poster_image_filenames(2, with_specials=True),
]


@pytest.mark.integration
@pytest.mark.slow
def test_file_monitor_workflow(
    temp_sonarr_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test file monitor-only workflow with real-time NFO and image processing.

    This test verifies that the file monitor component can detect and process
    NFO files and images in real-time when they are created by Sonarr.
    """
    with (
        ServiceRunner(
            temp_sonarr_media_root,
            {"ENABLE_FILE_SCANNER": "false"},
            startup_pattern="File monitor started",
        ),
        SeriesWithNfos(
            configured_sonarr_container,
            temp_sonarr_media_root,
            BREAKING_BAD_TVDB_ID,
            BREAKING_BAD_IMAGES,
        ) as (nfo_files, image_files),
    ):
        verify_translations(
            nfo_files, expected_language="zh", possible_languages=["zh", "en"]
        )
        verify_images(image_files, expected_language="zh-CN")


@pytest.mark.integration
@pytest.mark.slow
def test_file_scanner_workflow(
    temp_sonarr_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test file scanner-only workflow with periodic directory scanning.

    This test verifies that the file scanner component can discover and process
    existing NFO files and images through periodic directory scanning.
    """
    with (
        SeriesWithNfos(
            configured_sonarr_container,
            temp_sonarr_media_root,
            BREAKING_BAD_TVDB_ID,
            BREAKING_BAD_IMAGES,
        ) as (nfo_files, image_files),
        ServiceRunner(temp_sonarr_media_root, {"ENABLE_FILE_MONITOR": "false"}),
    ):
        verify_translations(
            nfo_files, expected_language="zh", possible_languages=["zh", "en"]
        )
        verify_images(image_files, expected_language="zh-CN")


@pytest.mark.integration
@pytest.mark.slow
def test_rollback_service_mode(
    temp_sonarr_media_root: Path,
    configured_sonarr_container: SonarrClient,
    tmp_path: Path,
) -> None:
    """Test rollback service mode that restores original NFO files and images.

    This test verifies that the rollback service mode can restore original
    NFO content and images after files have been translated to Chinese.
    """
    # Create backup directory outside media root to avoid interference
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(exist_ok=True)

    with SeriesWithNfos(
        configured_sonarr_container,
        temp_sonarr_media_root,
        BREAKING_BAD_TVDB_ID,
        BREAKING_BAD_IMAGES,
    ) as (nfo_files, image_files):
        # First, translate files to Chinese using rewrite mode with backups enabled
        with ServiceRunner(
            temp_sonarr_media_root,
            {
                "ORIGINAL_FILES_BACKUP_DIR": str(backup_dir),
            },
        ):
            verify_translations(
                nfo_files, expected_language="zh", possible_languages=["zh", "en"]
            )
            verify_images(image_files, expected_language="zh-CN")

        # Then, rollback using rollback service mode
        with ServiceRunner(
            temp_sonarr_media_root,
            {"SERVICE_MODE": "rollback", "ORIGINAL_FILES_BACKUP_DIR": str(backup_dir)},
        ):
            verify_translations(
                nfo_files, expected_language="en", possible_languages=["zh", "en"]
            )
            # After rollback, images should not have markers (original images)
            verify_images(image_files, expected_language=None)


@pytest.mark.integration
@pytest.mark.slow
def test_nfo_rewrite_disabled(
    temp_sonarr_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Test that NFO rewrite can be disabled independently of image rewriting.

    When ENABLE_NFO_REWRITE=false, NFO files should remain in their original
    language (English, as generated by Sonarr) while images are still rewritten
    with the preferred language markers.
    """
    with (
        SeriesWithNfos(
            configured_sonarr_container,
            temp_sonarr_media_root,
            BREAKING_BAD_TVDB_ID,
            BREAKING_BAD_IMAGES,
        ) as (nfo_files, image_files),
        ServiceRunner(
            temp_sonarr_media_root,
            {"ENABLE_NFO_REWRITE": "false"},
        ),
    ):
        # Images should still be rewritten with zh-CN markers
        # (verify_images uses retry, so this confirms the service is active)
        verify_images(image_files, expected_language="zh-CN")
        # NFO files must remain in English since NFO rewrite is disabled
        verify_translations(
            nfo_files, expected_language="en", possible_languages=["zh", "en"]
        )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize(
    "tvdb_id,images,service_config,expected_language",
    [
        # Translation fallback when preferred language has empty titles (issue #26).
        # Tests Chinese series "大明王朝1566" where some Chinese translations have
        # empty titles but valid descriptions, requiring fallback to complete.
        (MING_DYNASTY_TVDB_ID, MING_DYNASTY_IMAGES, {}, "zh"),
        # External ID lookup workflow using TVDB ID to find TMDB ID (issue #29).
        # Tests "Every Treasure Tells a Story" series (TVDB: 364698 -> TMDB: 86965)
        # to verify TMDB ID resolution from TVDB ID when direct TMDB ID unavailable.
        (
            EVERY_TREASURE_TELLS_A_STORY_TVDB_ID,
            EVERY_TREASURE_TELLS_A_STORY_IMAGES,
            {},
            "zh",
        ),
        # Smart fallback translation merging (issue #50).
        # Tests "Gen V" series where fr-CA and fr-FR translations are merged
        # to create complete French translations avoiding English fallback.
        (
            GEN_V_TVDB_ID,
            GEN_V_IMAGES,
            {"PREFERRED_LANGUAGES": "fr-CA,fr-FR"},
            "fr",
        ),
    ],
    ids=["translation-fallback", "external-id-lookup", "smart-fallback-merging"],
)
def test_advanced_translation_scenarios(
    temp_sonarr_media_root: Path,
    configured_sonarr_container: SonarrClient,
    tvdb_id: int,
    images: list[str],
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

    # For Every Treasure Tells a Story (86965/364698) and Gen V (205715/417909),
    # TMDB zh-CN has empty taglines, so we allow them to be empty.
    require_tagline = tvdb_id not in {
        EVERY_TREASURE_TELLS_A_STORY_TVDB_ID,
        GEN_V_TVDB_ID,
    }

    with (
        SeriesWithNfos(
            configured_sonarr_container, temp_sonarr_media_root, tvdb_id, images
        ) as (
            nfo_files,
            _,
        ),
        ServiceRunner(temp_sonarr_media_root, service_config),
    ):
        verify_translations(
            nfo_files,
            expected_language,
            possible_languages=list(possible_languages),
            require_tagline=require_tagline,
        )


@pytest.mark.integration
@pytest.mark.slow
def test_episode_tvdb_external_id_lookup(
    temp_sonarr_media_root: Path,
    configured_sonarr_container: SonarrClient,
) -> None:
    """Translate a Sonarr episode NFO with only an episode TVDB ID (issue #105)."""
    with SeriesWithNfos(
        configured_sonarr_container,
        temp_sonarr_media_root,
        CAPE_FEAR_TVDB_ID,
        [],
        episodes=[("Episode 8", 1, 8)],
    ) as (nfo_files, _):
        nfo_metadata = {nfo_path: parse_nfo_content(nfo_path) for nfo_path in nfo_files}
        parent_nfos = [
            nfo_path
            for nfo_path in nfo_files
            if nfo_metadata[nfo_path]["root_tag"] == "tvshow"
        ]
        assert len(parent_nfos) == 1
        episode_nfos = [
            nfo_path
            for nfo_path in nfo_files
            if nfo_metadata[nfo_path]["tvdb_id"] == CAPE_FEAR_EPISODE_TVDB_ID
        ]
        assert len(episode_nfos) == 1
        assert nfo_metadata[episode_nfos[0]]["tmdb_id"] is None
        parent_nfos[0].unlink()

        with ServiceRunner(
            temp_sonarr_media_root,
            {
                "ENABLE_FILE_MONITOR": "false",
                "ENABLE_IMAGE_REWRITE": "false",
                "PREFERRED_LANGUAGES": "fr-FR",
            },
        ):
            verify_translations(
                episode_nfos,
                expected_language="fr",
                possible_languages=["en", "fr"],
                require_tagline=False,
            )


@pytest.mark.integration
@pytest.mark.slow
def test_multi_episode_nfo_rewrite_and_rollback(
    temp_sonarr_media_root: Path,
    configured_sonarr_container: SonarrClient,
    tmp_path: Path,
) -> None:
    """Test rewrite and rollback for Sonarr-style multi-episode NFO files."""
    backup_dir = tmp_path / "multi_episode_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    with SeriesManager(
        configured_sonarr_container,
        BREAKING_BAD_TVDB_ID,
        "/tv",
        temp_sonarr_media_root,
    ) as series:
        create_fake_multi_episode_file(
            temp_sonarr_media_root,
            series.slug,
            season=1,
            first_episode=1,
            last_episode=2,
            title="Pilot + Cat's in the Bag",
        )

        scan_success = configured_sonarr_container.trigger_disk_scan(series.id)
        assert scan_success, "Failed to trigger disk scan"

        series_path = temp_sonarr_media_root / series.slug
        nfo_files = wait_for_nfo_files(series_path, expected_count=2, timeout=30.0)
        multi_episode_nfos = [
            nfo_file for nfo_file in nfo_files if "E01-E02" in nfo_file.name
        ]
        assert len(multi_episode_nfos) == 1, (
            f"Expected one Sonarr-generated multi-episode NFO, got {nfo_files}"
        )
        multi_episode_nfo = multi_episode_nfos[0]

        original_content = multi_episode_nfo.read_text(encoding="utf-8")
        assert original_content.count("<episodedetails>") == 2
        assert "</episodedetails>\n<episodedetails>" in original_content

        with ServiceRunner(
            temp_sonarr_media_root,
            {
                "ENABLE_FILE_MONITOR": "false",
                "ORIGINAL_FILES_BACKUP_DIR": str(backup_dir),
            },
        ):
            verify_translations(
                nfo_files,
                expected_language="zh",
                possible_languages=["zh", "en"],
            )
            rewritten_content = multi_episode_nfo.read_text(encoding="utf-8")
            assert rewritten_content.count("<episodedetails>") == 2
            assert "</episodedetails>\n<episodedetails>" in rewritten_content

        with ServiceRunner(
            temp_sonarr_media_root,
            {
                "SERVICE_MODE": "rollback",
                "ENABLE_FILE_MONITOR": "false",
                "ORIGINAL_FILES_BACKUP_DIR": str(backup_dir),
            },
        ):
            verify_translations(
                nfo_files,
                expected_language="en",
                possible_languages=["zh", "en"],
            )
            rolled_back_content = multi_episode_nfo.read_text(encoding="utf-8")
            assert rolled_back_content.count("<episodedetails>") == 2
            assert "</episodedetails>\n<episodedetails>" in rolled_back_content
