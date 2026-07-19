"""TMDB API client with translation caching."""

import time
from collections.abc import Callable
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
        cache_key = f"translations:{tmdb_ids}"

        def fetch_translations() -> dict[str, TranslatedContent]:
            endpoint = f"/{tmdb_ids}/translations"
            api_data = self._fetch_with_retry(endpoint)
            return self._parse_api_translations(api_data, tmdb_ids.media_type)

        translations = self._get_with_cache(
            cache_key, fetch_translations, default_on_404={}
        )
        return self._ensure_new_format(translations)

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

    def _get_with_cache(
        self,
        cache_key: str,
        fetch_func: Callable[[], Any],
        default_on_404: Any = None,
    ) -> Any:
        """Generic cache wrapper that handles 404 caching.

        Args:
            cache_key: Cache key to use
            fetch_func: Function that performs the API fetch
            default_on_404: Value to cache and return on 404 errors

        Returns:
            Cached or fetched data, or default_on_404 for 404 responses
        """
        # Check cache first
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            # Execute the fetch function
            result = fetch_func()
            # Cache successful result
            self.cache.set(cache_key, result, expire=self.cache_expire_seconds)
            return result
        except httpx.HTTPStatusError as e:
            if e.response.status_code == httpx.codes.NOT_FOUND:
                # Cache 404 with default value
                self.cache.set(
                    cache_key, default_on_404, expire=self.cache_expire_seconds
                )
                return default_on_404
            # Re-raise other HTTP errors
            raise

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
        cache_key = f"original_details:{tmdb_ids}"

        def fetch_details() -> tuple[str, str] | None:
            # For episodes, we need both episode name and series original language
            if tmdb_ids.media_type == "movie":
                api_data = self._fetch_with_retry(f"/movie/{tmdb_ids.tmdb_id}")
                original_language = api_data.get("original_language", "")
                original_title = api_data.get("original_title", "")
            elif tmdb_ids.season is not None and tmdb_ids.episode is not None:
                # Get episode details for the name
                episode_endpoint = (
                    f"/tv/{tmdb_ids.tmdb_id}/season/{tmdb_ids.season}"
                    f"/episode/{tmdb_ids.episode}"
                )
                episode_data = self._fetch_with_retry(episode_endpoint)

                # Get series details for the original language
                series_endpoint = f"/tv/{tmdb_ids.tmdb_id}"
                series_data = self._fetch_with_retry(series_endpoint)

                original_language = series_data.get("original_language", "")
                original_title = episode_data.get("name", "")
            else:
                # Series details endpoint
                endpoint = f"/tv/{tmdb_ids.tmdb_id}"
                api_data = self._fetch_with_retry(endpoint)

                original_language = api_data.get("original_language", "")
                original_title = api_data.get("original_name", "")

            if original_language and original_title:
                return (original_language, original_title.strip())

            return None

        return cast(
            tuple[str, str] | None,
            self._get_with_cache(cache_key, fetch_details, default_on_404=None),
        )

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

        def fetch_external_id() -> int | None:
            # Use TMDB's find endpoint with external source
            endpoint = f"/find/{external_id}"
            params = {"external_source": external_source}

            api_data = self._fetch_with_retry(endpoint, params)

            # Look for TV results
            tv_results = api_data.get("tv_results", [])
            if tv_results:
                tmdb_id = tv_results[0].get("id")
                if tmdb_id:
                    return int(tmdb_id)

            return None

        return cast(
            int | None,
            self._get_with_cache(cache_key, fetch_external_id, default_on_404=None),
        )

    def _ensure_new_format(
        self, cached_data: dict[str, TranslatedContent]
    ) -> dict[str, TranslatedContent]:
        """Ensure cached data is in new format with TranslatedString objects.

        This handles backward compatibility for cache data from before the
        model change where TranslatedContent had string fields instead of
        TranslatedString objects.

        Args:
            cached_data: Dictionary of cached translation data

        Returns:
            Dictionary with TranslatedContent objects in new format
        """
        converted_data = {}

        for lang_code, content in cached_data.items():
            has_tagline = hasattr(content, "tagline")
            tagline = getattr(
                content,
                "tagline",
                TranslatedString(content="", language="unknown"),
            )
            if (
                isinstance(content.title, str)
                or not has_tagline
                or not isinstance(tagline, TranslatedString)
            ):
                # Old format - convert to new format
                converted_content = TranslatedContent(
                    title=(
                        TranslatedString(
                            content=content.title,
                            language=getattr(content, "language", lang_code),
                        )
                        if isinstance(content.title, str)
                        else content.title
                    ),
                    description=(
                        TranslatedString(
                            content=str(content.description),
                            language=getattr(content, "language", lang_code),
                        )
                        if isinstance(content.description, str)
                        else content.description
                    ),
                    tagline=(
                        tagline
                        if isinstance(tagline, TranslatedString)
                        else TranslatedString(
                            content=str(tagline),
                            language=getattr(content, "language", lang_code),
                        )
                    ),
                )
                converted_data[lang_code] = converted_content
            else:
                # Already in new format
                converted_data[lang_code] = content

        return converted_data

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
        # Cache by endpoint only since server response is independent of
        # preference ordering; selection happens client-side.
        cache_key = f"images:{endpoint}"

        def fetch_images() -> dict[str, Any]:
            return self._fetch_with_retry(endpoint)

        api_data = self._get_with_cache(cache_key, fetch_images, default_on_404={})

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
