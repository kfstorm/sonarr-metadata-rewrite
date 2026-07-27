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
AMELIE_TMDB_ID = 194
AMELIE_FRENCH_TITLE = "Le Fabuleux Destin d'Amélie Poulain"
HI_MOM_TMDB_ID = 758891
HI_MOM_TRADITIONAL_TITLE = "你好\uff0c李煥英"


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
    assert radarr_container.configure_metadata_settings(use_movie_nfo), (
        "Failed to configure Radarr Kodi/Emby metadata provider"
    )

    if service_config.get("ENABLE_FILE_SCANNER") == "false":
        with (
            ServiceRunner(
                temp_radarr_media_root,
                service_config,
                startup_pattern="File monitor started",
            ),
            MovieWithNfos(
                radarr_container,
                temp_radarr_media_root,
                FIGHT_CLUB_TMDB_ID,
                use_movie_nfo,
            ) as (nfo_file, image_files),
        ):
            verify_movie_output(nfo_file, image_files)
    else:
        with (
            MovieWithNfos(
                radarr_container,
                temp_radarr_media_root,
                FIGHT_CLUB_TMDB_ID,
                use_movie_nfo,
            ) as (nfo_file, image_files),
            ServiceRunner(temp_radarr_media_root, service_config),
        ):
            verify_movie_output(nfo_file, image_files)


@pytest.mark.integration
@pytest.mark.slow
def test_radarr_french_movie_title_is_not_replaced_by_english_fallback(
    temp_radarr_media_root: Path,
    radarr_container: RadarrClient,
) -> None:
    """Keep Radarr's French original title when English is a fallback language."""
    assert radarr_container.configure_metadata_settings(
        use_movie_nfo=True,
        movie_metadata_language=2,
    ), "Failed to configure Radarr French metadata"

    try:
        with MovieWithNfos(
            radarr_container,
            temp_radarr_media_root,
            AMELIE_TMDB_ID,
            use_movie_nfo=True,
        ) as (nfo_file, _):
            assert parse_nfo_content(nfo_file)["title"] == AMELIE_FRENCH_TITLE

            with ServiceRunner(
                temp_radarr_media_root,
                {
                    "ENABLE_FILE_MONITOR": "false",
                    "ENABLE_IMAGE_REWRITE": "false",
                    "PREFERRED_LANGUAGES": "fr-FR,en-US",
                },
            ):
                verify_translations([nfo_file], "fr", ["fr", "en"])

            assert parse_nfo_content(nfo_file)["title"] == AMELIE_FRENCH_TITLE
    finally:
        assert radarr_container.configure_metadata_settings(
            use_movie_nfo=True,
            movie_metadata_language=1,
        ), "Failed to reset Radarr English metadata"


@pytest.mark.integration
@pytest.mark.slow
def test_radarr_prefers_traditional_chinese_movie_metadata(
    temp_radarr_media_root: Path,
    radarr_container: RadarrClient,
) -> None:
    """Rewrite a mainland Chinese movie with the configured Traditional Chinese data."""
    assert radarr_container.configure_metadata_settings(use_movie_nfo=True), (
        "Failed to configure Radarr movie metadata"
    )

    with MovieWithNfos(
        radarr_container,
        temp_radarr_media_root,
        HI_MOM_TMDB_ID,
        use_movie_nfo=True,
    ) as (nfo_file, _):
        with ServiceRunner(
            temp_radarr_media_root,
            {
                "ENABLE_FILE_MONITOR": "false",
                "ENABLE_IMAGE_REWRITE": "false",
                "PREFERRED_LANGUAGES": "zh-TW,zh-CN",
            },
        ):
            verify_translations([nfo_file], "zh", ["zh", "en"])

        assert parse_nfo_content(nfo_file)["title"] == HI_MOM_TRADITIONAL_TITLE


@pytest.mark.integration
@pytest.mark.slow
def test_movie_metadata_url_nfo_rewrite(
    temp_radarr_media_root: Path,
    radarr_container: RadarrClient,
) -> None:
    """Rewrite a real Radarr combination NFO without losing scraper URLs."""
    assert radarr_container.configure_metadata_settings(
        use_movie_nfo=True, movie_metadata_url=True
    ), "Failed to enable Radarr movie metadata URL"

    expected_urls = [
        "https://www.themoviedb.org/movie/550",
        "https://www.imdb.com/title/tt0137523",
    ]
    try:
        with MovieWithNfos(
            radarr_container,
            temp_radarr_media_root,
            FIGHT_CLUB_TMDB_ID,
            use_movie_nfo=True,
        ) as (nfo_file, _):
            original_content = nfo_file.read_text(encoding="utf-8")
            original_xml, closing_tag, original_suffix = original_content.partition(
                "</movie>"
            )
            assert closing_tag == "</movie>"
            assert "<movie>" in original_xml
            assert original_suffix.splitlines() == ["", *expected_urls]

            with ServiceRunner(
                temp_radarr_media_root,
                {
                    "ENABLE_FILE_MONITOR": "false",
                    "ENABLE_IMAGE_REWRITE": "false",
                },
            ):
                verify_translations([nfo_file], "zh", ["zh", "en"])

            _, closing_tag, rewritten_suffix = nfo_file.read_text(
                encoding="utf-8"
            ).partition("</movie>")
            assert closing_tag == "</movie>"
            assert rewritten_suffix == original_suffix
            assert rewritten_suffix.splitlines() == ["", *expected_urls]
    finally:
        assert radarr_container.configure_metadata_settings(
            use_movie_nfo=True, movie_metadata_url=False
        ), "Failed to reset Radarr movie metadata URL"


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
    assert radarr_container.configure_metadata_settings(use_movie_nfo), (
        "Failed to configure Radarr Kodi/Emby metadata provider"
    )
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
    assert radarr_container.configure_metadata_settings(use_movie_nfo), (
        "Failed to configure Radarr Kodi/Emby metadata provider"
    )

    with (
        MovieWithNfos(
            radarr_container,
            temp_radarr_media_root,
            FIGHT_CLUB_TMDB_ID,
            use_movie_nfo,
        ) as (nfo_file, image_files),
        ServiceRunner(
            temp_radarr_media_root,
            {"ENABLE_NFO_REWRITE": "false"},
        ),
    ):
        verify_images(image_files, expected_language="zh-CN")
        verify_translations([nfo_file], "en", ["zh", "en"])
