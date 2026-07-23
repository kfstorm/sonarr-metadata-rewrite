"""Integration tests against the live TMDB API."""

from pathlib import Path

import pytest
from diskcache import Cache  # type: ignore[import-untyped]

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.models import TmdbIds
from sonarr_metadata_rewrite.translator import Translator

BERSERK_TMDB_ID = 35935
BERSERK_EPISODE_6_TVDB_ID = 127401
BERSERK_EPISODE_16_TVDB_ID = 127411


@pytest.mark.integration
@pytest.mark.slow
def test_berserk_episode_tvdb_lookup_and_french_translations(
    tmp_path: Path,
) -> None:
    """Reproduce both Berserk lookup failures reported after v1.2.3."""
    settings = Settings(
        cache_dir=tmp_path / "cache",
        rewrite_root_dirs=[tmp_path],
        preferred_languages=["fr-FR"],
    )
    cache = Cache(str(settings.cache_dir))
    translator = Translator(settings, cache)

    try:
        resolved_ids = {
            episode_tvdb_id: translator.find_tmdb_id_by_external_id(
                str(episode_tvdb_id),
                "tvdb_id",
                resource_type="episode",
            )
            for episode_tvdb_id in (
                BERSERK_EPISODE_6_TVDB_ID,
                BERSERK_EPISODE_16_TVDB_ID,
            )
        }
        episode_6 = translator.get_translations(
            TmdbIds(
                tmdb_id=BERSERK_TMDB_ID,
                media_type="tv",
                season=1,
                episode=6,
            )
        )
        episode_16 = translator.get_translations(
            TmdbIds(
                tmdb_id=BERSERK_TMDB_ID,
                media_type="tv",
                season=1,
                episode=16,
            )
        )

        assert episode_6["fr-FR"].title.content == "Zodd l'immortel"
        assert episode_16["fr-FR"].title.content == "Le conquérant"
        assert resolved_ids == {
            BERSERK_EPISODE_6_TVDB_ID: BERSERK_TMDB_ID,
            BERSERK_EPISODE_16_TVDB_ID: BERSERK_TMDB_ID,
        }
    finally:
        translator.client.close()
        cache.close()
