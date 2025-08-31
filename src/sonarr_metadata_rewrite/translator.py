"""TMDB API client with translation caching."""

import time
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

        # Build endpoint and fetch from API with retry logic
        endpoint = f"/{tmdb_ids}/translations"
        api_data = self._fetch_with_retry(endpoint)

        # Parse translations
        translations = self._parse_api_translations(api_data)

        # Store in cache with expiration
        self.cache.set(cache_key, translations, expire=self.cache_expire_seconds)

        return translations

    def _fetch_with_retry(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Fetch data from TMDB API with exponential backoff retry for rate limits.

        Args:
            endpoint: API endpoint to fetch
            params: Optional query parameters

        Returns:
            JSON response data

        Raises:
            httpx.HTTPError: If request fails after all retries
        """
        max_retries = self.settings.tmdb_max_retries
        initial_delay = self.settings.tmdb_initial_retry_delay
        max_delay = self.settings.tmdb_max_retry_delay

        for attempt in range(max_retries + 1):
            try:
                response = self.client.get(endpoint, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                # Handle rate limiting (HTTP 429)
                if e.response.status_code == 429 and attempt < max_retries:
                    # Calculate exponential backoff delay
                    delay = min(initial_delay * (2**attempt), max_delay)
                    time.sleep(delay)
                    continue
                # Re-raise for other HTTP errors or if max retries exceeded
                raise
            except (httpx.HTTPError, Exception):
                # Re-raise all other errors immediately (no retry)
                raise

        # This should never be reached due to the logic above
        raise RuntimeError("Unexpected code path in _fetch_with_retry")

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

    def find_tmdb_id_by_external_id(
        self, external_id: str, external_source: str
    ) -> int | None:
        """Find TMDB ID using external ID (TVDB or IMDB).

        Args:
            external_id: The external ID (e.g., TVDB or IMDB ID)
            external_source: Source type ('tvdb_id' or 'imdb_id')

        Returns:
            TMDB series ID if found, None otherwise
        """
        cache_key = f"external_find:{external_source}:{external_id}"

        # Check cache first
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            # Use TMDB's find endpoint with external source
            endpoint = f"/find/{external_id}"
            params = {"external_source": external_source}

            api_data = self._fetch_with_retry(endpoint, params)

            # Look for TV results
            tv_results = api_data.get("tv_results", [])
            if tv_results:
                tmdb_id = tv_results[0].get("id")
                if tmdb_id:
                    result = int(tmdb_id)
                    # Store in cache with expiration
                    self.cache.set(cache_key, result, expire=self.cache_expire_seconds)
                    return result

        except Exception:
            # If API call fails, return None
            pass

        # Cache negative result to avoid repeated API calls
        self.cache.set(cache_key, None, expire=self.cache_expire_seconds)
        return None

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
