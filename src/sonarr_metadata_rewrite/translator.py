"""TMDB API client with translation caching."""

import time
from typing import Any, cast

import httpx
from diskcache import Cache  # type: ignore[import-untyped]

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.models import (
    ImageCandidate,
    TmdbIds,
    TranslatedContent,
    TranslatedString,
)


class Translator:
    """TMDB API client with caching and rate limiting."""

    _RESPONSE_CACHE_NAMESPACE = "tmdb:v3:response:v2"

    def __init__(self, settings: Settings, cache: Cache):
        """Initialize client and cache settings."""
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
        """Get all translations for TV, episode, or movie resources.

        Args:
            tmdb_ids: TMDB identifiers containing media type and optional TV episode

        Returns:
            Dictionary mapping language codes to TranslatedContent objects
        """
        endpoint = f"/{tmdb_ids}/translations"
        api_data = self._get_cached_json(endpoint)
        if api_data is None:
            return {}

        return self._parse_api_translations(api_data, tmdb_ids.media_type)

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
            response, rate_limit_error = self._request(endpoint, params)
            if response.status_code != httpx.codes.TOO_MANY_REQUESTS:
                response.raise_for_status()
                return cast(dict[str, Any], response.json())

            if attempt == max_retries:
                if rate_limit_error is not None:
                    raise rate_limit_error
                response.raise_for_status()
            delay = min(initial_delay * (2**attempt), max_delay)
            time.sleep(delay)

        # This should never be reached due to the logic above
        raise RuntimeError("Unexpected code path in _fetch_with_retry")

    def _request(
        self, endpoint: str, params: dict[str, Any] | None
    ) -> tuple[httpx.Response, httpx.HTTPStatusError | None]:
        """Issue one request and preserve a rate-limit error for final re-raise."""
        try:
            return self.client.get(endpoint, params=params), None
        except httpx.HTTPStatusError as error:
            if error.response.status_code != httpx.codes.TOO_MANY_REQUESTS:
                raise
            return error.response, error

    def _get_cached_json(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Get one TMDB JSON response, caching only 200 and 404 outcomes."""
        cache_key = self._response_cache_key(endpoint, params)
        cached_outcome = self.cache.get(cache_key)
        if cached_outcome is not None:
            if cached_outcome["status"] == httpx.codes.NOT_FOUND:
                return None
            return cast(dict[str, Any], cached_outcome["body"])

        try:
            api_data = self._fetch_with_retry(endpoint, params)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != httpx.codes.NOT_FOUND:
                raise
            self.cache.set(
                cache_key,
                {"status": httpx.codes.NOT_FOUND},
                expire=self.cache_expire_seconds,
            )
            return None

        self.cache.set(
            cache_key,
            {"status": httpx.codes.OK, "body": api_data},
            expire=self.cache_expire_seconds,
        )
        return api_data

    def _response_cache_key(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> str:
        """Build a cache key from HTTPX's serialized GET request URL."""
        request = self.client.build_request("GET", endpoint, params=params)
        return f"{self._RESPONSE_CACHE_NAMESPACE}:{request.method}:{request.url}"

    def _parse_api_translations(
        self, api_data: dict[str, Any], media_type: str
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

            title_key = "title" if media_type == "movie" else "name"
            title = data.get(title_key, "").strip()
            description = data.get("overview", "").strip()
            tagline = data.get("tagline", "").strip()

            # Skip records without any localizable metadata.
            if not title and not description and not tagline:
                continue

            translations[full_language_code] = TranslatedContent(
                title=TranslatedString(content=title, language=full_language_code),
                description=TranslatedString(
                    content=description, language=full_language_code
                ),
                tagline=TranslatedString(content=tagline, language=full_language_code),
            )

        return translations

    def get_original_details(self, tmdb_ids: TmdbIds) -> tuple[str, str] | None:
        """Get original language and title for TV, episode, or movie resources.

        Args:
            tmdb_ids: TMDB identifiers containing media type and optional TV episode

        Returns:
            Tuple of (original_language, original_title) if found, None otherwise
        """
        # For episodes, we need both episode name and series original language.
        if tmdb_ids.media_type == "movie":
            api_data = self._get_cached_json(f"/movie/{tmdb_ids.tmdb_id}")
            if api_data is None:
                return None
            original_language = api_data.get("original_language", "")
            original_title = api_data.get("original_title", "")
        elif tmdb_ids.season is not None and tmdb_ids.episode is not None:
            episode_endpoint = (
                f"/tv/{tmdb_ids.tmdb_id}/season/{tmdb_ids.season}"
                f"/episode/{tmdb_ids.episode}"
            )
            episode_data = self._get_cached_json(episode_endpoint)
            if episode_data is None:
                return None

            series_data = self._get_cached_json(f"/tv/{tmdb_ids.tmdb_id}")
            if series_data is None:
                return None

            original_language = series_data.get("original_language", "")
            original_title = episode_data.get("name", "")
        else:
            api_data = self._get_cached_json(f"/tv/{tmdb_ids.tmdb_id}")
            if api_data is None:
                return None
            original_language = api_data.get("original_language", "")
            original_title = api_data.get("original_name", "")

        if original_language and original_title:
            return (original_language, original_title.strip())

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
        endpoint = f"/find/{external_id}"
        api_data = self._get_cached_json(endpoint, {"external_source": external_source})
        if api_data is None:
            return None

        # Look for TV results.
        tv_results = api_data.get("tv_results", [])
        if tv_results:
            tmdb_id = tv_results[0].get("id")
            if tmdb_id:
                return int(tmdb_id)

        tv_episode_results = api_data.get("tv_episode_results", [])
        if tv_episode_results:
            show_id = tv_episode_results[0].get("show_id")
            if show_id:
                return int(show_id)

        return None

    def select_best_image(
        self,
        tmdb_ids: TmdbIds,
        preferred_languages: list[str],
        kind: str,
    ) -> ImageCandidate | None:
        """Select the best image candidate based on language preferences.

        Args:
            tmdb_ids: TMDB identifiers (media type and optional TV season)
            preferred_languages: List of language codes in preference order
                (e.g., ["en-US", "ja-JP"])
            kind: Image kind - "poster" or "clearlogo"

        Returns:
            ImageCandidate with file_path and language info, or None if no match
        """
        # Determine endpoint based on kind and season
        if kind == "poster" and tmdb_ids.season is not None:
            endpoint = f"/tv/{tmdb_ids.tmdb_id}/season/{tmdb_ids.season}/images"
        else:
            endpoint = f"/{tmdb_ids.media_type}/{tmdb_ids.tmdb_id}/images"

        # Fetch images from TMDB
        # NOTE: Do NOT pass include_image_language due to TMDB API bug;
        # fetch all images and filter locally in Python.
        api_data = self._get_cached_json(endpoint)
        if api_data is None:
            return None

        # Select from appropriate array
        if kind == "poster":
            candidates = api_data.get("posters", [])
        elif kind == "clearlogo":
            candidates = api_data.get("logos", [])
        else:
            return None

        # Match against preferred languages in order
        for pref_lang in preferred_languages:
            # Split lang-country format (e.g., "en-US" -> "en", "US")
            if "-" not in pref_lang:
                continue  # Skip if not in lang-country format

            lang_part, country_part = pref_lang.split("-", 1)

            # Find first candidate matching this language-country combination
            for candidate in candidates:
                iso_639_1 = candidate.get("iso_639_1")
                iso_3166_1 = candidate.get("iso_3166_1")

                # Skip candidates with null language or country
                if iso_639_1 is None or iso_3166_1 is None:
                    continue

                # Check for exact match
                if iso_639_1 == lang_part and iso_3166_1 == country_part:
                    file_path = candidate.get("file_path", "")
                    if file_path:
                        return ImageCandidate(
                            file_path=file_path,
                            iso_639_1=iso_639_1,
                            iso_3166_1=iso_3166_1,
                        )

        # No match found
        return None

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
