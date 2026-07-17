"""Integration tests using real Radarr-generated movie metadata and artwork."""

from pathlib import Path

import pytest

from tests.integration.fixtures.radarr_client import RadarrClient
from tests.integration.test_helpers import (
    MovieWithNfos,
    ServiceRunner,
    parse_nfo_content,
    verify_images,
    verify_translations,
)

# Verified against TMDB /movie/550/images during test development: zh-CN has
# poster and logo candidates. Missing upstream assets must fail this test.
FIGHT_CLUB_TMDB_ID = 550


def verify_movie_output(nfo_file: Path, image_files: list[Path]) -> None:
    """Verify translated movie document and localized artwork markers."""
    verify_translations([nfo_file], "zh", ["zh", "en"])
    verify_images(image_files, expected_language="zh-CN")
    metadata = parse_nfo_content(nfo_file)
    assert metadata["root_tag"] == "movie"
    assert metadata["title"].strip(), "Movie NFO has no translated title"
    assert metadata["plot"].strip(), "Movie NFO has no translated plot"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize(
    ("use_movie_nfo", "service_config"),
    [
        (True, {"ENABLE_FILE_SCANNER": "false"}),
        (False, {"ENABLE_FILE_SCANNER": "false"}),
        (True, {"ENABLE_FILE_MONITOR": "false"}),
        (False, {"ENABLE_FILE_MONITOR": "false"}),
    ],
    ids=[
        "movie-nfo-file-monitor",
        "video-named-nfo-file-monitor",
        "movie-nfo-file-scanner",
        "video-named-nfo-file-scanner",
    ],
)
def test_radarr_movie_metadata_and_images(
    temp_radarr_media_root: Path,
    radarr_container: RadarrClient,
    use_movie_nfo: bool,
    service_config: dict[str, str],
) -> None:
    """Rewrite real Radarr movie NFO and localized poster."""
    assert radarr_container.configure_metadata_settings(
        use_movie_nfo
    ), "Failed to configure Radarr Kodi/Emby metadata provider"

    if service_config.get("ENABLE_FILE_SCANNER") == "false":
        with ServiceRunner(
            temp_radarr_media_root,
            service_config,
            startup_pattern="File monitor started",
        ):
            with MovieWithNfos(
                radarr_container,
                temp_radarr_media_root,
                FIGHT_CLUB_TMDB_ID,
                use_movie_nfo,
            ) as (nfo_file, image_files):
                verify_movie_output(nfo_file, image_files)
    else:
        with MovieWithNfos(
            radarr_container,
            temp_radarr_media_root,
            FIGHT_CLUB_TMDB_ID,
            use_movie_nfo,
        ) as (nfo_file, image_files):
            with ServiceRunner(temp_radarr_media_root, service_config):
                verify_movie_output(nfo_file, image_files)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize(
    "use_movie_nfo",
    [True, False],
    ids=["movie-nfo", "video-named-nfo"],
)
def test_radarr_movie_rollback_service_mode(
    temp_radarr_media_root: Path,
    radarr_container: RadarrClient,
    tmp_path: Path,
    use_movie_nfo: bool,
) -> None:
    """Restore original Radarr movie NFO and poster from backup."""
    assert radarr_container.configure_metadata_settings(
        use_movie_nfo
    ), "Failed to configure Radarr Kodi/Emby metadata provider"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    with MovieWithNfos(
        radarr_container,
        temp_radarr_media_root,
        FIGHT_CLUB_TMDB_ID,
        use_movie_nfo,
    ) as (nfo_file, image_files):
        with ServiceRunner(
            temp_radarr_media_root,
            {"ORIGINAL_FILES_BACKUP_DIR": str(backup_dir)},
        ):
            verify_movie_output(nfo_file, image_files)

        with ServiceRunner(
            temp_radarr_media_root,
            {
                "SERVICE_MODE": "rollback",
                "ORIGINAL_FILES_BACKUP_DIR": str(backup_dir),
            },
        ):
            verify_translations([nfo_file], "en", ["zh", "en"])
            verify_images(image_files, expected_language=None)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize(
    "use_movie_nfo",
    [True, False],
    ids=["movie-nfo", "video-named-nfo"],
)
def test_radarr_nfo_rewrite_disabled(
    temp_radarr_media_root: Path,
    radarr_container: RadarrClient,
    use_movie_nfo: bool,
) -> None:
    """Keep Radarr movie NFO English while rewriting localized poster."""
    assert radarr_container.configure_metadata_settings(
        use_movie_nfo
    ), "Failed to configure Radarr Kodi/Emby metadata provider"

    with MovieWithNfos(
        radarr_container,
        temp_radarr_media_root,
        FIGHT_CLUB_TMDB_ID,
        use_movie_nfo,
    ) as (nfo_file, image_files):
        with ServiceRunner(
            temp_radarr_media_root,
            {"ENABLE_NFO_REWRITE": "false"},
        ):
            verify_images(image_files, expected_language="zh-CN")
            verify_translations([nfo_file], "en", ["zh", "en"])
