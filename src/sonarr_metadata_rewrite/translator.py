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
            headers={"Authorization": f"Bearer {self.api_key}"},
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

            title = data.get("name", "").strip()
            description = data.get("overview", "").strip()

            # Skip if both title and description are empty
            if not title and not description:
                continue

            translations[full_language_code] = TranslatedContent(
                title=title,
                description=description,
                language=full_language_code,
            )

        return translations

    def get_original_details(self, tmdb_ids: TmdbIds) -> tuple[str, str] | None:
        """Get original language and title for TV series or episode.

        Args:
            tmdb_ids: TMDB identifiers containing series_id and optional season/episode

        Returns:
            Tuple of (original_language, original_title) if found, None otherwise
        """
        cache_key = f"original_details:{tmdb_ids}"

        # Check cache first
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            # For episodes, we need both episode name and series original language
            if tmdb_ids.season is not None and tmdb_ids.episode is not None:
                # Get episode details for the name
                episode_endpoint = (
                    f"/tv/{tmdb_ids.series_id}/season/{tmdb_ids.season}"
                    f"/episode/{tmdb_ids.episode}"
                )
                episode_response = self.client.get(episode_endpoint)
                episode_response.raise_for_status()
                episode_data = episode_response.json()

                # Get series details for the original language
                series_endpoint = f"/tv/{tmdb_ids.series_id}"
                series_response = self.client.get(series_endpoint)
                series_response.raise_for_status()
                series_data = series_response.json()

                original_language = series_data.get("original_language", "")
                original_title = episode_data.get("name", "")
            else:
                # Series details endpoint
                endpoint = f"/tv/{tmdb_ids.series_id}"
                response = self.client.get(endpoint)
                response.raise_for_status()
                api_data = response.json()

                original_language = api_data.get("original_language", "")
                original_title = api_data.get("original_name", "")

            if original_language and original_title:
                result = (original_language, original_title.strip())
                # Store in cache with expiration
                self.cache.set(cache_key, result, expire=self.cache_expire_seconds)
                return result

        except Exception:
            # If API call fails, return None (will fall back to existing logic)
            pass

        return None

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
