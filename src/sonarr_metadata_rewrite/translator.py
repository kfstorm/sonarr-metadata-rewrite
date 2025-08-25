"""TMDB API client with translation caching."""

from typing import Any

import httpx
from diskcache import Cache  # type: ignore[import-untyped]

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.models import TmdbIds, TranslatedContent


class Translator:
    """TMDB API client with caching and rate limiting."""

    def __init__(self, settings: Settings, cache: Cache):
        self.settings = settings
        self.api_key = settings.tmdb_api_key
        self.cache = cache
        self.cache_expire_seconds = settings.cache_duration_hours * 3600
        self.client = httpx.Client(
            base_url="https://api.themoviedb.org/3",
            params={"api_key": self.api_key},
            timeout=30.0,
        )

    def get_translations(self, tmdb_ids: TmdbIds) -> dict[str, TranslatedContent]:
        """Get all translations for TV series or episode.

        Args:
            tmdb_ids: TMDB identifiers containing series_id and optional season/episode

        Returns:
            Dictionary mapping language codes to TranslatedContent objects
        """
        cache_key = f"translations:{tmdb_ids}"

        # Check cache first
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Build endpoint and fetch from API
        endpoint = f"/{tmdb_ids}/translations"
        response = self.client.get(endpoint)
        response.raise_for_status()
        api_data = response.json()

        # Parse translations
        translations = self._parse_api_translations(api_data)

        # Store in cache with expiration
        self.cache.set(cache_key, translations, expire=self.cache_expire_seconds)

        return translations

    def _parse_api_translations(
        self, api_data: dict[str, Any]
    ) -> dict[str, TranslatedContent]:
        """Parse TMDB API response into TranslatedContent objects."""
        translations = {}

        for translation in api_data.get("translations", []):
            language_code = translation.get("iso_639_1", "")
            country_code = translation.get("iso_3166_1", "")
            data = translation.get("data", {})

            # Skip if no language code or no translated data
            if not language_code or not data:
                continue

            # Use language-country format if country is available
            full_language_code = (
                f"{language_code}-{country_code}" if country_code else language_code
            )

            # Extract title and description, skip if both are empty
            title = data.get("title", "").strip()
            description = data.get("overview", "").strip()

            if not title and not description:
                continue

            translations[full_language_code] = TranslatedContent(
                title=title,
                description=description,
                language=full_language_code,
            )

        return translations

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
