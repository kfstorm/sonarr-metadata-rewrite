"""Unit tests for translator."""

import json
from collections.abc import Generator
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, call, patch

import httpx
import pytest
from diskcache import Cache  # type: ignore[import-untyped]

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.models import TmdbIds, TranslatedString
from sonarr_metadata_rewrite.translator import Translator


def mock_not_found_error() -> httpx.HTTPStatusError:
    """Create a TMDB 404 error response."""
    response = Mock(status_code=404)
    return httpx.HTTPStatusError("Not Found", request=Mock(), response=response)


def configure_image_response(mock_get: Mock, response: dict[str, Any]) -> None:
    """Configure a successful image API response."""
    mock_get.return_value.json.return_value = response
    mock_get.return_value.raise_for_status = Mock()


@pytest.fixture
def translator(test_settings: Settings) -> Generator[Translator]:
    """Create translator instance."""
    cache = Cache(str(test_settings.cache_dir))
    translator = Translator(test_settings, cache)
    # Clear the cache to ensure clean tests
    translator.cache.clear()
    yield translator
    translator.close()
    cache.close()


@pytest.fixture
def mock_series_response() -> dict[str, Any]:
    """Mock TMDB series translations API response."""
    return {
        "id": 12345,
        "translations": [
            {
                "iso_3166_1": "CN",
                "iso_639_1": "zh",
                "name": "普通话",
                "english_name": "Mandarin",
                "data": {
                    "name": "测试剧集",
                    "overview": "这是一个测试剧集的描述",
                    "tagline": "命运由你掌握。",
                    "homepage": "",
                },
            },
            {
                "iso_3166_1": "US",
                "iso_639_1": "en",
                "name": "English",
                "english_name": "English",
                "data": {
                    "name": "Test Series",
                    "overview": "This is a test series description",
                    "homepage": "http://example.com",
                },
            },
            {
                "iso_3166_1": "",
                "iso_639_1": "ja",
                "name": "日本語",
                "english_name": "Japanese",
                "data": {
                    "name": "テストシリーズ",
                    "overview": "これはテストシリーズの説明です",
                    "homepage": "",
                },
            },
        ],
    }


@pytest.fixture
def mock_episode_response() -> dict[str, Any]:
    """Mock TMDB episode translations API response."""
    return {
        "id": 67890,
        "translations": [
            {
                "iso_3166_1": "CN",
                "iso_639_1": "zh",
                "name": "普通话",
                "english_name": "Mandarin",
                "data": {"name": "测试剧集", "overview": "这是一个测试剧集的描述"},
            }
        ],
    }


@pytest.fixture
def mock_series_details_response() -> dict[str, Any]:
    """Mock TMDB series details API response."""
    return {
        "id": 68034,
        "name": "Ming Dynasty in 1566",
        "original_name": "大明王朝1566",
        "original_language": "zh",
        "overview": "A series about the Ming Dynasty...",
        "first_air_date": "2007-01-08",
    }


@pytest.fixture
def mock_episode_details_response() -> dict[str, Any]:
    """Mock TMDB episode details API response."""
    return {
        "id": 12345,
        "name": "Episode 1",
        "overview": "First episode overview...",
        "season_number": 1,
        "episode_number": 1,
        # Episodes don't have original_language, they inherit from series
    }


def test_translator_initialization(translator: Translator) -> None:
    """Test translator initialization."""
    assert translator.api_key == "test_key_12345"
    assert isinstance(translator.cache, Cache)
    assert translator.client is not None


def test_tmdb_ids_string_representation() -> None:
    """Test TmdbIds __str__ method."""
    # Series
    series_ids = TmdbIds(tmdb_id=12345, media_type="tv")
    assert str(series_ids) == "tv/12345"

    # Episode
    episode_ids = TmdbIds(tmdb_id=12345, media_type="tv", season=1, episode=2)
    assert str(episode_ids) == "tv/12345/season/1/episode/2"


@patch("httpx.Client.get")
def test_get_translations_series_success(
    mock_get: Mock, translator: Translator, mock_series_response: dict[str, Any]
) -> None:
    """Test successful series translations retrieval."""
    # Mock successful HTTP response
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = mock_series_response
    mock_get.return_value = mock_response

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")
    translations = translator.get_translations(tmdb_ids)

    # Verify API call
    mock_get.assert_called_once_with("/tv/12345/translations", params=None)

    # Verify parsed translations
    assert isinstance(translations, dict)
    assert len(translations) == 3

    # Check Chinese translation
    assert "zh-CN" in translations
    zh_cn = translations["zh-CN"]
    assert zh_cn.title.content == "测试剧集"
    assert zh_cn.description.content == "这是一个测试剧集的描述"
    assert zh_cn.tagline.content == "命运由你掌握。"
    assert zh_cn.title.language == "zh-CN"
    assert zh_cn.description.language == "zh-CN"

    # Check English translation
    assert "en-US" in translations
    en_us = translations["en-US"]
    assert en_us.title.content == "Test Series"
    assert en_us.description.content == "This is a test series description"
    assert en_us.title.language == "en-US"
    assert en_us.description.language == "en-US"

    # Check Japanese translation (no country code)
    assert "ja" in translations
    ja = translations["ja"]
    assert ja.title.content == "テストシリーズ"
    assert ja.description.content == "これはテストシリーズの説明です"
    assert ja.title.language == "ja"
    assert ja.description.language == "ja"


@patch("httpx.Client.get")
def test_get_translations_episode_success(
    mock_get: Mock, translator: Translator, mock_episode_response: dict[str, Any]
) -> None:
    """Test successful episode translations retrieval."""
    # Mock successful HTTP response
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = mock_episode_response
    mock_get.return_value = mock_response

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv", season=1, episode=2)
    translations = translator.get_translations(tmdb_ids)

    # Verify API call with correct endpoint
    mock_get.assert_called_once_with(
        "/tv/12345/season/1/episode/2/translations", params=None
    )

    # Verify parsed translations
    assert isinstance(translations, dict)
    assert len(translations) == 1
    assert "zh-CN" in translations

    zh_cn = translations["zh-CN"]
    assert zh_cn.title.content == "测试剧集"
    assert zh_cn.description.content == "这是一个测试剧集的描述"
    assert zh_cn.title.language == "zh-CN"
    assert zh_cn.description.language == "zh-CN"


@patch("httpx.Client.get")
def test_get_translations_movie_uses_movie_path_and_title(
    mock_get: Mock, translator: Translator
) -> None:
    """Test movie translations use movie endpoint and data.title."""
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "translations": [
            {
                "iso_639_1": "zh",
                "iso_3166_1": "CN",
                "data": {
                    "title": "电影标题",
                    "overview": "电影剧情",
                    "tagline": "电影宣传语",
                },
            }
        ]
    }
    mock_get.return_value = mock_response

    translations = translator.get_translations(TmdbIds(tmdb_id=550, media_type="movie"))

    mock_get.assert_called_once_with("/movie/550/translations", params=None)
    assert translations["zh-CN"].title.content == "电影标题"
    assert translations["zh-CN"].description.content == "电影剧情"
    assert translations["zh-CN"].tagline.content == "电影宣传语"


def test_get_translations_keeps_tagline_only_record(translator: Translator) -> None:
    """Test translations with only a tagline remain available for selection."""
    translations = translator._parse_api_translations(
        {
            "translations": [
                {
                    "iso_639_1": "zh",
                    "iso_3166_1": "CN",
                    "data": {"tagline": "命运由你掌握。"},
                }
            ]
        },
        "movie",
    )

    assert translations["zh-CN"].title.content == ""
    assert translations["zh-CN"].description.content == ""
    assert translations["zh-CN"].tagline.content == "命运由你掌握。"


@patch("httpx.Client.get")
def test_get_translations_http_error(mock_get: Mock, translator: Translator) -> None:
    """Test HTTP error handling."""
    # Mock HTTP error
    mock_get.side_effect = httpx.HTTPError("API error")

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")

    # Should raise the HTTP error (fail-fast)
    with pytest.raises(httpx.HTTPError, match="API error"):
        translator.get_translations(tmdb_ids)


@patch("httpx.Client.get")
def test_get_translations_json_decode_error(
    mock_get: Mock, translator: Translator
) -> None:
    """Test JSON decode error handling."""
    # Mock response with invalid JSON
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "doc", 0)
    mock_get.return_value = mock_response

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")

    # Should raise the JSON decode error (fail-fast)
    with pytest.raises(json.JSONDecodeError, match="Invalid JSON"):
        translator.get_translations(tmdb_ids)


@patch("httpx.Client.get")
def test_get_translations_empty_response(
    mock_get: Mock, translator: Translator
) -> None:
    """Test handling of empty translations response."""
    # Mock response with no translations
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"id": 12345, "translations": []}
    mock_get.return_value = mock_response

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")
    translations = translator.get_translations(tmdb_ids)

    # Should return empty dict when no translations available
    assert isinstance(translations, dict)
    assert len(translations) == 0


@patch("httpx.Client.get")
def test_get_translations_filters_empty_data(
    mock_get: Mock, translator: Translator
) -> None:
    """Test filtering of translations with empty title and description."""
    # Mock response with empty data
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "id": 12345,
        "translations": [
            {
                "iso_639_1": "zh",
                "iso_3166_1": "CN",
                "data": {"name": "", "overview": ""},
            },
            {
                "iso_639_1": "en",
                "iso_3166_1": "US",
                "data": {"name": "Valid Title", "overview": ""},
            },
        ],
    }
    mock_get.return_value = mock_response

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")
    translations = translator.get_translations(tmdb_ids)

    # Should only include translations with content
    assert len(translations) == 1
    assert "en-US" in translations
    assert "zh-CN" not in translations


@patch("httpx.Client.get")
def test_get_translations_skips_entry_without_language_code(
    mock_get: Mock, translator: Translator
) -> None:
    """Test that translation entries with empty language code are skipped (line 150)."""
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "id": 12345,
        "translations": [
            {
                "iso_639_1": "",
                "iso_3166_1": "CN",
                "data": {"name": "Some Title", "overview": "Some overview"},
            },
            {
                "iso_639_1": "en",
                "iso_3166_1": "US",
                "data": {"name": "Valid Title", "overview": "Valid overview"},
            },
        ],
    }
    mock_get.return_value = mock_response

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")
    translations = translator.get_translations(tmdb_ids)

    assert len(translations) == 1
    assert "en-US" in translations


def test_response_cache_key_uses_httpx_serialized_url(translator: Translator) -> None:
    """Test cache keys use the same URL serialization as HTTPX requests."""
    endpoint = "/find/tt0286112"
    params = {"empty": None, "enabled": True, "query": "A+B"}
    request = translator.client.build_request("GET", endpoint, params=params)

    cache_key = translator._response_cache_key(endpoint, params)

    assert cache_key == (
        f"{translator._RESPONSE_CACHE_NAMESPACE}:{request.method}:{request.url}"
    )
    assert translator._response_cache_key(endpoint, {"empty": None}) != (
        translator._response_cache_key(endpoint)
    )
    assert translator._response_cache_key(endpoint, {"enabled": True}) != (
        translator._response_cache_key(endpoint, {"enabled": "True"})
    )


@patch("httpx.Client.get")
def test_caching_integration(
    mock_get: Mock, translator: Translator, mock_series_response: dict[str, Any]
) -> None:
    """Test that caching works with API calls."""
    # Mock successful HTTP response
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = mock_series_response
    mock_get.return_value = mock_response

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")

    # First call should hit API and cache result
    translations1 = translator.get_translations(tmdb_ids)
    assert mock_get.call_count == 1
    assert len(translations1) == 3
    cache_key = translator._response_cache_key("/tv/12345/translations")
    assert translator.cache[cache_key] == {
        "status": 200,
        "body": mock_series_response,
    }

    # Second call should use cache (no additional API calls)
    translations2 = translator.get_translations(tmdb_ids)
    assert mock_get.call_count == 1  # Still only 1 call
    assert len(translations2) == 3
    assert translations1 == translations2


def test_translator_configuration(translator: Translator) -> None:
    """Test translator configuration."""
    assert translator.settings.tmdb_api_key == "test_key_12345"
    assert isinstance(translator.cache, Cache)
    assert str(translator.client.base_url) == "https://api.themoviedb.org/3/"


def test_close_method(test_settings: Settings) -> None:
    """Test translator close method."""
    cache = Cache(str(test_settings.cache_dir))
    translator = Translator(test_settings, cache)
    assert translator.client is not None
    assert isinstance(translator.cache, Cache)
    translator.close()
    cache.close()
    # Client should be closed after calling close()


@patch("httpx.Client.get")
def test_get_original_details_series_success(
    mock_get: Mock, translator: Translator, mock_series_details_response: dict[str, Any]
) -> None:
    """Test successful series original details retrieval."""
    # Mock successful HTTP response
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = mock_series_details_response
    mock_get.return_value = mock_response

    tmdb_ids = TmdbIds(tmdb_id=68034, media_type="tv")
    result = translator.get_original_details(tmdb_ids)

    # Verify API call
    mock_get.assert_called_once_with("/tv/68034", params=None)

    # Verify result
    assert result is not None
    original_language, original_title = result
    assert original_language == "zh"
    assert original_title == "大明王朝1566"


@patch("httpx.Client.get")
def test_get_original_details_movie_uses_movie_title_fields(
    mock_get: Mock, translator: Translator
) -> None:
    """Test movie details use movie endpoint and original_title."""
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "original_language": "en",
        "original_title": "Fight Club",
    }
    mock_get.return_value = mock_response

    result = translator.get_original_details(TmdbIds(tmdb_id=550, media_type="movie"))

    mock_get.assert_called_once_with("/movie/550", params=None)
    assert result == ("en", "Fight Club")


@patch("httpx.Client.get")
def test_get_original_details_episode_success(
    mock_get: Mock,
    translator: Translator,
    mock_episode_details_response: dict[str, Any],
    mock_series_details_response: dict[str, Any],
) -> None:
    """Test successful episode original details retrieval."""

    # Mock both episode and series responses (episode needs series for
    # original_language)
    def mock_side_effect(endpoint: str, params: dict[str, Any] | None = None) -> Mock:
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        if "season" in endpoint and "episode" in endpoint:
            mock_response.json.return_value = mock_episode_details_response
        else:
            mock_response.json.return_value = mock_series_details_response
        return mock_response

    mock_get.side_effect = mock_side_effect

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv", season=1, episode=1)
    result = translator.get_original_details(tmdb_ids)

    # Verify both API calls were made
    assert mock_get.call_count == 2
    mock_get.assert_any_call(
        "/tv/12345/season/1/episode/1", params=None
    )  # Episode details
    mock_get.assert_any_call(
        "/tv/12345", params=None
    )  # Series details for original_language

    # Verify result combines episode name with series original language
    assert result is not None
    original_language, original_title = result
    assert original_language == "zh"  # From series
    assert original_title == "Episode 1"  # From episode


@patch("httpx.Client.get")
def test_get_original_details_http_error(
    mock_get: Mock, translator: Translator
) -> None:
    """Test HTTP error handling in get_original_details."""
    # Mock HTTP error
    mock_get.side_effect = httpx.HTTPError("API error")

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")

    # Should raise the HTTP error (fail-fast behavior with new implementation)
    with pytest.raises(httpx.HTTPError, match="API error"):
        translator.get_original_details(tmdb_ids)


@patch("httpx.Client.get")
def test_get_original_details_missing_data(
    mock_get: Mock, translator: Translator
) -> None:
    """Test handling of response with missing original language or title."""
    # Mock response with missing data
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "id": 12345,
        "name": "Some Title",
        # Missing original_language and original_name
    }
    mock_get.return_value = mock_response

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")
    result = translator.get_original_details(tmdb_ids)

    # Should return None when required data is missing
    assert result is None


@patch("httpx.Client.get")
def test_get_original_details_caching(
    mock_get: Mock, translator: Translator, mock_series_details_response: dict[str, Any]
) -> None:
    """Test that original details are cached properly."""
    # Mock successful HTTP response
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = mock_series_details_response
    mock_get.return_value = mock_response

    tmdb_ids = TmdbIds(tmdb_id=68034, media_type="tv")

    # First call should hit API and cache result
    result1 = translator.get_original_details(tmdb_ids)
    assert mock_get.call_count == 1
    assert result1 == ("zh", "大明王朝1566")

    # Second call should use cache (no additional API calls)
    result2 = translator.get_original_details(tmdb_ids)
    assert mock_get.call_count == 1  # Still only 1 call
    assert result2 == ("zh", "大明王朝1566")
    assert result1 == result2


@patch("httpx.Client.get")
@patch("time.sleep")
def test_rate_limit_retry_success(
    mock_sleep: Mock,
    mock_get: Mock,
    translator: Translator,
    mock_series_response: dict[str, Any],
) -> None:
    """Test successful retry after rate limit error."""
    # First call returns 429, second call succeeds
    rate_limit_response = Mock()
    rate_limit_response.status_code = 429
    rate_limit_error = httpx.HTTPStatusError(
        "Too Many Requests", request=Mock(), response=rate_limit_response
    )

    success_response = Mock()
    success_response.raise_for_status.return_value = None
    success_response.json.return_value = mock_series_response

    mock_get.side_effect = [rate_limit_error, success_response]

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")
    translations = translator.get_translations(tmdb_ids)

    # Should have made 2 API calls (1 failed, 1 success)
    assert mock_get.call_count == 2

    # Should have slept once (exponential backoff)
    mock_sleep.assert_called_once_with(1.0)  # Initial delay

    # Should return translations from successful call
    assert len(translations) == 3
    assert "zh-CN" in translations


@patch("httpx.Client.get")
@patch("time.sleep")
def test_rate_limit_max_retries_exceeded(
    mock_sleep: Mock, mock_get: Mock, translator: Translator
) -> None:
    """Test that rate limit retries are exhausted and error is raised."""
    # All calls return 429
    rate_limit_response = Mock()
    rate_limit_response.status_code = 429
    rate_limit_error = httpx.HTTPStatusError(
        "Too Many Requests", request=Mock(), response=rate_limit_response
    )
    mock_get.side_effect = rate_limit_error

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")

    # Should raise the rate limit error after exhausting retries
    with pytest.raises(httpx.HTTPStatusError, match="Too Many Requests"):
        translator.get_translations(tmdb_ids)

    # Should have made max_retries + 1 attempts (default is 3 + 1 = 4)
    assert mock_get.call_count == 4

    # Should have slept 3 times (between retries)
    assert mock_sleep.call_count == 3

    # Check exponential backoff delays: 1.0, 2.0, 4.0
    expected_delays = [1.0, 2.0, 4.0]
    actual_delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert actual_delays == expected_delays


@pytest.mark.parametrize("status_code", [400, 401, 403, 500])
@patch("httpx.Client.get")
def test_non_cacheable_http_error_is_not_retried_or_cached(
    mock_get: Mock, translator: Translator, status_code: int
) -> None:
    """Test non-404 HTTP errors are neither retried nor cached."""
    error_response = Mock(status_code=status_code)
    error = httpx.HTTPStatusError(
        f"HTTP {status_code}", request=Mock(), response=error_response
    )
    mock_get.side_effect = error

    with pytest.raises(httpx.HTTPStatusError, match=f"HTTP {status_code}"):
        translator.get_translations(TmdbIds(tmdb_id=12345, media_type="tv"))

    assert mock_get.call_count == 1
    cache_key = translator._response_cache_key("/tv/12345/translations")
    assert cache_key not in translator.cache


@patch("httpx.Client.get")
@patch("time.sleep")
def test_rate_limit_exponential_backoff_max_delay(
    mock_sleep: Mock, mock_get: Mock, test_settings: Settings
) -> None:
    """Test that exponential backoff respects maximum delay."""
    # Configure low max delay for testing
    test_settings.tmdb_max_retry_delay = 3.0
    test_settings.tmdb_max_retries = 4

    with Cache() as cache:
        translator = Translator(test_settings, cache)

        # All calls return 429
        rate_limit_response = Mock()
        rate_limit_response.status_code = 429
        rate_limit_error = httpx.HTTPStatusError(
            "Too Many Requests", request=Mock(), response=rate_limit_response
        )
        mock_get.side_effect = rate_limit_error

        tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")

        with pytest.raises(httpx.HTTPStatusError):
            translator.get_translations(tmdb_ids)

        # Check that delays are capped at max_delay
        # Expected: 1.0, 2.0, 3.0 (capped), 3.0 (capped)
        expected_delays = [1.0, 2.0, 3.0, 3.0]
        actual_delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays

        translator.close()


@patch("httpx.Client.get")
@patch("time.sleep")
def test_rate_limit_preserves_cache_on_failure(
    mock_sleep: Mock, mock_get: Mock, translator: Translator
) -> None:
    """Test that rate limit failures don't corrupt cache."""
    # Rate limit error for all attempts
    rate_limit_response = Mock()
    rate_limit_response.status_code = 429
    rate_limit_error = httpx.HTTPStatusError(
        "Too Many Requests", request=Mock(), response=rate_limit_response
    )
    mock_get.side_effect = rate_limit_error

    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")
    cache_key = translator._response_cache_key("/tv/12345/translations")

    # Ensure cache is empty initially
    assert cache_key not in translator.cache

    # Attempt to get translations (should fail)
    with pytest.raises(httpx.HTTPStatusError):
        translator.get_translations(tmdb_ids)

    # Cache should still be empty (no partial data stored)
    assert cache_key not in translator.cache


@pytest.fixture
def mock_find_tvdb_response() -> dict[str, Any]:
    """Mock TMDB find by TVDB ID API response."""
    return {
        "movie_results": [],
        "person_results": [],
        "tv_results": [
            {
                "id": 1396,
                "name": "Breaking Bad",
                "original_name": "Breaking Bad",
                "overview": "A high school chemistry teacher...",
                "first_air_date": "2008-01-20",
            }
        ],
        "tv_episode_results": [],
        "tv_season_results": [],
    }


@pytest.fixture
def mock_find_imdb_response() -> dict[str, Any]:
    """Mock TMDB find by IMDB ID API response."""
    return {
        "movie_results": [],
        "person_results": [],
        "tv_results": [
            {
                "id": 2316,
                "name": "The Office",
                "original_name": "The Office",
                "overview": "The everyday lives of office employees...",
                "first_air_date": "2005-03-24",
            }
        ],
        "tv_episode_results": [],
        "tv_season_results": [],
    }


def test_find_tmdb_id_by_external_id_tvdb_success(
    translator: Translator, mock_find_tvdb_response: dict[str, Any]
) -> None:
    """Test successful TVDB to TMDB ID lookup."""
    with patch.object(translator.client, "get") as mock_get:
        # Mock successful API response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = mock_find_tvdb_response
        mock_get.return_value = mock_response

        # Call the method
        result = translator.find_tmdb_id_by_external_id("81189", "tvdb_id")

        # Verify result
        assert result == 1396

        # Verify API call
        mock_get.assert_called_once_with(
            "/find/81189", params={"external_source": "tvdb_id"}
        )


def test_find_tmdb_id_by_external_id_tvdb_episode_success(
    translator: Translator,
) -> None:
    """Resolve an episode TVDB ID through its parent TMDB show ID."""
    episode_response: dict[str, Any] = {
        "movie_results": [],
        "person_results": [],
        "tv_results": [],
        "tv_episode_results": [
            {
                "id": 5454819,
                "season_number": 1,
                "episode_number": 8,
                "show_id": 277439,
            }
        ],
        "tv_season_results": [],
    }

    with patch.object(translator.client, "get") as mock_get:
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = episode_response
        mock_get.return_value = mock_response

        result = translator.find_tmdb_id_by_external_id("11593814", "tvdb_id")

        assert result == 277439
        mock_get.assert_called_once_with(
            "/find/11593814", params={"external_source": "tvdb_id"}
        )


def test_find_tmdb_id_by_external_id_imdb_success(
    translator: Translator, mock_find_imdb_response: dict[str, Any]
) -> None:
    """Test successful IMDB to TMDB ID lookup."""
    with patch.object(translator.client, "get") as mock_get:
        # Mock successful API response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = mock_find_imdb_response
        mock_get.return_value = mock_response

        # Call the method
        result = translator.find_tmdb_id_by_external_id("tt0386676", "imdb_id")

        # Verify result
        assert result == 2316

        # Verify API call
        mock_get.assert_called_once_with(
            "/find/tt0386676", params={"external_source": "imdb_id"}
        )


def test_find_tmdb_id_by_external_id_no_results(translator: Translator) -> None:
    """Test external ID lookup with no TV results."""
    empty_response: dict[str, Any] = {
        "movie_results": [],
        "person_results": [],
        "tv_results": [],  # Empty results
        "tv_episode_results": [],
        "tv_season_results": [],
    }

    with patch.object(translator.client, "get") as mock_get:
        # Mock API response with no TV results
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = empty_response
        mock_get.return_value = mock_response

        # Call the method
        result = translator.find_tmdb_id_by_external_id("999999", "tvdb_id")

        # Verify result is None
        assert result is None


def test_find_tmdb_id_by_external_id_api_error(translator: Translator) -> None:
    """Test external ID lookup with API error."""
    with patch.object(translator.client, "get") as mock_get:
        # Mock API error
        mock_get.side_effect = httpx.HTTPError("API Error")

        # Call the method - should raise the HTTP error (fail-fast behavior)
        with pytest.raises(httpx.HTTPError, match="API Error"):
            translator.find_tmdb_id_by_external_id("12345", "tvdb_id")


def test_find_tmdb_id_by_external_id_caching(
    translator: Translator, mock_find_tvdb_response: dict[str, Any]
) -> None:
    """Test external ID lookup caching behavior."""
    with patch.object(translator.client, "get") as mock_get:
        # Mock successful API response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = mock_find_tvdb_response
        mock_get.return_value = mock_response

        # First call
        result1 = translator.find_tmdb_id_by_external_id("81189", "tvdb_id")
        assert result1 == 1396

        # Second call - should use cache
        result2 = translator.find_tmdb_id_by_external_id("81189", "tvdb_id")
        assert result2 == 1396

        # Verify only one API call was made
        mock_get.assert_called_once()


def test_find_tmdb_id_by_external_id_cache_negative_result(
    translator: Translator,
) -> None:
    """Test that negative results are also cached."""
    empty_response: dict[str, Any] = {
        "movie_results": [],
        "person_results": [],
        "tv_results": [],
        "tv_episode_results": [],
        "tv_season_results": [],
    }

    with patch.object(translator.client, "get") as mock_get:
        # Mock API response with no results
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = empty_response
        mock_get.return_value = mock_response

        # First call
        result1 = translator.find_tmdb_id_by_external_id("999999", "tvdb_id")
        assert result1 is None

        # Second call - should use cache
        result2 = translator.find_tmdb_id_by_external_id("999999", "tvdb_id")
        assert result2 is None

        # Verify only one API call was made
        mock_get.assert_called_once()


@patch("httpx.Client.get")
def test_get_translations_ignores_legacy_derived_cache(
    mock_get: Mock, translator: Translator, mock_series_response: dict[str, Any]
) -> None:
    """Test a legacy parsed cache entry cannot hide new TMDB fields."""
    tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv")
    legacy_cache_key = f"translations:{tmdb_ids}"
    translator.cache.set(
        legacy_cache_key,
        {
            "zh-CN": SimpleNamespace(
                title=TranslatedString(content="旧中文标题", language="zh-CN"),
                description=TranslatedString(content="旧中文描述", language="zh-CN"),
            )
        },
    )
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = mock_series_response
    mock_get.return_value = mock_response

    translations = translator.get_translations(tmdb_ids)

    assert mock_get.call_count == 1
    zh_cn = translations["zh-CN"]
    assert zh_cn.tagline.content == "命运由你掌握。"
    response_cache_key = translator._response_cache_key("/tv/12345/translations")
    assert translator.cache[response_cache_key]["body"] == mock_series_response


@patch("httpx.Client.get")
def test_get_cached_json_caches_404_outcome(
    mock_get: Mock, translator: Translator
) -> None:
    """Test the response cache stores a not-found outcome."""
    mock_get.side_effect = mock_not_found_error()
    endpoint = "/test/endpoint"
    cache_key = translator._response_cache_key(endpoint)

    assert translator._get_cached_json(endpoint) is None
    assert mock_get.call_count == 1
    assert cache_key in translator.cache
    assert translator.cache[cache_key] == {"status": 404}

    assert translator._get_cached_json(endpoint) is None
    assert mock_get.call_count == 1


@patch("httpx.Client.get")
def test_get_translations_404_cached(mock_get: Mock, translator: Translator) -> None:
    """Test that get_translations properly caches 404 responses as empty dict."""
    # Mock 404 HTTP error
    mock_get.side_effect = mock_not_found_error()

    tmdb_ids = TmdbIds(tmdb_id=99999, media_type="tv")  # Non-existent series
    cache_key = translator._response_cache_key("/tv/99999/translations")

    # Verify cache starts empty
    assert cache_key not in translator.cache

    # First call should hit API and return empty dict
    translations1 = translator.get_translations(tmdb_ids)
    assert translations1 == {}
    assert mock_get.call_count == 1

    # Verify the not-found outcome was cached
    assert cache_key in translator.cache
    assert translator.cache[cache_key] == {"status": 404}

    # Second call should use cache (no additional API calls)
    translations2 = translator.get_translations(tmdb_ids)
    assert translations2 == {}
    assert mock_get.call_count == 1  # Still only 1 call

    # Results should be identical
    assert translations1 == translations2


@patch("httpx.Client.get")
def test_get_original_details_404_cached(
    mock_get: Mock, translator: Translator
) -> None:
    """Test that get_original_details properly caches 404 responses as None."""
    # Mock 404 HTTP error
    not_found_response = Mock()
    not_found_response.status_code = 404
    not_found_error = httpx.HTTPStatusError(
        "Not Found", request=Mock(), response=not_found_response
    )
    mock_get.side_effect = not_found_error

    tmdb_ids = TmdbIds(tmdb_id=99999, media_type="tv")  # Non-existent series
    cache_key = translator._response_cache_key("/tv/99999")

    # Verify cache starts empty
    assert cache_key not in translator.cache

    # First call should hit API and return None
    details1 = translator.get_original_details(tmdb_ids)
    assert details1 is None
    assert mock_get.call_count == 1

    # Verify the not-found outcome was cached
    assert cache_key in translator.cache
    assert translator.cache[cache_key] == {"status": 404}

    # Second call should use cache (no additional API calls)
    details2 = translator.get_original_details(tmdb_ids)
    assert details2 is None
    assert mock_get.call_count == 1  # Still only 1 call

    # Results should be identical
    assert details1 == details2


@pytest.mark.parametrize(
    ("tmdb_ids", "endpoint"),
    [
        (TmdbIds(tmdb_id=99999, media_type="movie"), "/movie/99999"),
        (
            TmdbIds(tmdb_id=99999, media_type="tv", season=1, episode=1),
            "/tv/99999/season/1/episode/1",
        ),
    ],
)
@patch("httpx.Client.get")
def test_get_original_details_returns_none_when_resource_not_found(
    mock_get: Mock,
    translator: Translator,
    tmdb_ids: TmdbIds,
    endpoint: str,
) -> None:
    """Test movie and episode detail 404 responses return None."""
    mock_get.side_effect = mock_not_found_error()

    assert translator.get_original_details(tmdb_ids) is None
    mock_get.assert_called_once_with(endpoint, params=None)


@patch("httpx.Client.get")
def test_get_original_details_episode_returns_none_when_series_not_found(
    mock_get: Mock,
    translator: Translator,
    mock_episode_details_response: dict[str, Any],
) -> None:
    """Test episode details return None when its series is unavailable."""
    episode_response = Mock()
    episode_response.raise_for_status.return_value = None
    episode_response.json.return_value = mock_episode_details_response
    mock_get.side_effect = [episode_response, mock_not_found_error()]

    tmdb_ids = TmdbIds(tmdb_id=99999, media_type="tv", season=1, episode=1)

    assert translator.get_original_details(tmdb_ids) is None
    assert mock_get.call_args_list == [
        call("/tv/99999/season/1/episode/1", params=None),
        call("/tv/99999", params=None),
    ]


@patch("httpx.Client.get")
def test_find_tmdb_id_404_cached(mock_get: Mock, translator: Translator) -> None:
    """Test that find_tmdb_id_by_external_id properly caches 404 responses as None."""
    # Mock 404 HTTP error
    not_found_response = Mock()
    not_found_response.status_code = 404
    not_found_error = httpx.HTTPStatusError(
        "Not Found", request=Mock(), response=not_found_response
    )
    mock_get.side_effect = not_found_error

    external_id = "99999"
    external_source = "tvdb_id"
    cache_key = translator._response_cache_key(
        "/find/99999", {"external_source": "tvdb_id"}
    )

    # Verify cache starts empty
    assert cache_key not in translator.cache

    # First call should hit API and return None
    result1 = translator.find_tmdb_id_by_external_id(external_id, external_source)
    assert result1 is None
    assert mock_get.call_count == 1

    # Verify the not-found outcome was cached
    assert cache_key in translator.cache
    assert translator.cache[cache_key] == {"status": 404}

    # Second call should use cache (no additional API calls)
    result2 = translator.find_tmdb_id_by_external_id(external_id, external_source)
    assert result2 is None
    assert mock_get.call_count == 1  # Still only 1 call

    # Results should be identical
    assert result1 == result2


class TestSelectBestImage:
    """Tests for Translator.select_best_image() method."""

    @pytest.fixture
    def mock_images_response_posters(self) -> dict[str, Any]:
        """Mock TMDB images API response with posters."""
        return {
            "id": 12345,
            "posters": [
                {
                    "file_path": "/poster_en_us.jpg",
                    "iso_639_1": "en",
                    "iso_3166_1": "US",
                    "vote_average": 5.5,
                },
                {
                    "file_path": "/poster_ja_jp.jpg",
                    "iso_639_1": "ja",
                    "iso_3166_1": "JP",
                    "vote_average": 5.8,
                },
                {
                    "file_path": "/poster_zh_cn.jpg",
                    "iso_639_1": "zh",
                    "iso_3166_1": "CN",
                    "vote_average": 6.0,
                },
            ],
            "logos": [],
        }

    @pytest.fixture
    def mock_images_response_logos(self) -> dict[str, Any]:
        """Mock TMDB images API response with logos."""
        return {
            "id": 67890,
            "posters": [],
            "logos": [
                {
                    "file_path": "/logo_en.jpg",
                    "iso_639_1": "en",
                    "iso_3166_1": "US",
                    "vote_average": 5.0,
                },
                {
                    "file_path": "/logo_ja.jpg",
                    "iso_639_1": "ja",
                    "iso_3166_1": "JP",
                    "vote_average": 5.5,
                },
            ],
        }

    @patch("httpx.Client.get")
    def test_select_best_image_poster_exact_match(
        self,
        mock_get: Mock,
        translator: Translator,
        mock_images_response_posters: dict[str, Any],
    ) -> None:
        """Test selecting poster with exact language-country match."""
        configure_image_response(mock_get, mock_images_response_posters)

        tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv", season=None, episode=None)
        result = translator.select_best_image(tmdb_ids, ["en-US"], kind="poster")

        assert result is not None
        assert result.file_path == "/poster_en_us.jpg"
        assert result.iso_639_1 == "en"
        assert result.iso_3166_1 == "US"

    @patch("httpx.Client.get")
    def test_select_best_image_clearlogo_exact_match(
        self,
        mock_get: Mock,
        translator: Translator,
        mock_images_response_logos: dict[str, Any],
    ) -> None:
        """Test selecting clearlogo with exact language-country match."""
        configure_image_response(mock_get, mock_images_response_logos)

        tmdb_ids = TmdbIds(tmdb_id=67890, media_type="tv", season=None, episode=None)
        result = translator.select_best_image(tmdb_ids, ["ja-JP"], kind="clearlogo")

        assert result is not None
        assert result.file_path == "/logo_ja.jpg"
        assert result.iso_639_1 == "ja"
        assert result.iso_3166_1 == "JP"

    @patch("httpx.Client.get")
    def test_select_best_image_movie_uses_movie_images_path(
        self,
        mock_get: Mock,
        translator: Translator,
        mock_images_response_posters: dict[str, Any],
    ) -> None:
        """Test movie artwork uses movie images endpoint."""
        configure_image_response(mock_get, mock_images_response_posters)

        result = translator.select_best_image(
            TmdbIds(tmdb_id=550, media_type="movie"), ["en-US"], kind="poster"
        )

        mock_get.assert_called_once_with("/movie/550/images", params=None)
        assert result is not None
        assert result.file_path == "/poster_en_us.jpg"

    @patch("httpx.Client.get")
    def test_select_best_image_season_poster(
        self,
        mock_get: Mock,
        translator: Translator,
    ) -> None:
        """Test selecting season poster calls correct endpoint."""
        season_response = {
            "id": 12345,
            "posters": [
                {
                    "file_path": "/season1_poster.jpg",
                    "iso_639_1": "en",
                    "iso_3166_1": "US",
                    "vote_average": 5.5,
                }
            ],
            "logos": [],
        }
        configure_image_response(mock_get, season_response)

        tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv", season=1)
        result = translator.select_best_image(tmdb_ids, ["en-US"], kind="poster")

        # Verify correct endpoint was called
        assert mock_get.called
        call_url = mock_get.call_args[0][0]
        assert "/tv/12345/season/1/images" in call_url

        assert result is not None
        assert result.file_path == "/season1_poster.jpg"

    @patch("httpx.Client.get")
    def test_select_best_image_preference_order(
        self,
        mock_get: Mock,
        translator: Translator,
        mock_images_response_posters: dict[str, Any],
    ) -> None:
        """Test that first preferred language match is returned."""
        configure_image_response(mock_get, mock_images_response_posters)

        tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv", season=None, episode=None)
        # Prefer en-US first, then ja-JP
        result = translator.select_best_image(
            tmdb_ids, ["en-US", "ja-JP", "zh-CN"], kind="poster"
        )

        assert result is not None
        # Should return en-US since it's first in preferences
        assert result.file_path == "/poster_en_us.jpg"
        assert result.iso_639_1 == "en"
        assert result.iso_3166_1 == "US"

    @patch("httpx.Client.get")
    def test_select_best_image_no_match_returns_none(
        self,
        mock_get: Mock,
        translator: Translator,
        mock_images_response_posters: dict[str, Any],
    ) -> None:
        """Test that no match returns None."""
        configure_image_response(mock_get, mock_images_response_posters)

        tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv", season=None, episode=None)
        # Request fr-FR which doesn't exist in response
        result = translator.select_best_image(tmdb_ids, ["fr-FR"], kind="poster")

        assert result is None

    @patch("httpx.Client.get")
    def test_select_best_image_skips_null_language(
        self,
        mock_get: Mock,
        translator: Translator,
    ) -> None:
        """Test that images with null language codes are skipped."""
        response_with_nulls = {
            "id": 12345,
            "posters": [
                {
                    "file_path": "/poster_null.jpg",
                    "iso_639_1": None,
                    "iso_3166_1": None,
                    "vote_average": 6.0,
                },
                {
                    "file_path": "/poster_en.jpg",
                    "iso_639_1": "en",
                    "iso_3166_1": "US",
                    "vote_average": 5.5,
                },
            ],
            "logos": [],
        }
        configure_image_response(mock_get, response_with_nulls)

        tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv", season=None, episode=None)
        result = translator.select_best_image(tmdb_ids, ["en-US"], kind="poster")

        assert result is not None
        # Should skip null and return en-US
        assert result.file_path == "/poster_en.jpg"

    @patch("httpx.Client.get")
    def test_select_best_image_skips_malformed_language_codes(
        self,
        mock_get: Mock,
        translator: Translator,
        mock_images_response_posters: dict[str, Any],
    ) -> None:
        """Test that malformed language codes without hyphen are skipped."""
        configure_image_response(mock_get, mock_images_response_posters)

        tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv", season=None, episode=None)
        # Malformed codes without hyphen should be skipped
        result = translator.select_best_image(
            tmdb_ids, ["en", "US", "en-US"], kind="poster"
        )

        assert result is not None
        # Should skip "en" and "US", use "en-US"
        assert result.iso_639_1 == "en"
        assert result.iso_3166_1 == "US"

    @patch("httpx.Client.get")
    def test_select_best_image_handles_404(
        self,
        mock_get: Mock,
        translator: Translator,
    ) -> None:
        """Test that 404 response returns None."""
        mock_get.side_effect = mock_not_found_error()

        tmdb_ids = TmdbIds(tmdb_id=99999, media_type="tv", season=None, episode=None)
        result = translator.select_best_image(tmdb_ids, ["en-US"], kind="poster")

        assert result is None

    @patch("httpx.Client.get")
    def test_select_best_image_caching(
        self,
        mock_get: Mock,
        translator: Translator,
        mock_images_response_posters: dict[str, Any],
    ) -> None:
        """Test that image selection results are cached."""
        configure_image_response(mock_get, mock_images_response_posters)

        tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv", season=None, episode=None)

        # First call
        result1 = translator.select_best_image(tmdb_ids, ["en-US"], kind="poster")
        assert mock_get.call_count == 1

        # Second call with same parameters should use cache
        result2 = translator.select_best_image(tmdb_ids, ["en-US"], kind="poster")
        assert mock_get.call_count == 1  # No additional API call

        assert result1 == result2

    @patch("httpx.Client.get")
    def test_select_best_image_empty_array(
        self,
        mock_get: Mock,
        translator: Translator,
    ) -> None:
        """Test that empty posters/logos array returns None."""
        empty_response = {"id": 12345, "posters": [], "logos": []}
        configure_image_response(mock_get, empty_response)

        tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv", season=None, episode=None)
        result = translator.select_best_image(tmdb_ids, ["en-US"], kind="poster")

        assert result is None

    @patch("httpx.Client.get")
    def test_select_best_image_different_language_combinations(
        self,
        mock_get: Mock,
        translator: Translator,
    ) -> None:
        """Test various language-country combinations."""
        # Test en-GB
        response_en_gb = {
            "id": 12345,
            "posters": [
                {"file_path": "/path1.jpg", "iso_639_1": "en", "iso_3166_1": "GB"}
            ],
        }
        configure_image_response(mock_get, response_en_gb)

        tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv", season=None, episode=None)
        result = translator.select_best_image(tmdb_ids, ["en-GB"], kind="poster")
        assert result is not None
        assert result.iso_639_1 == "en"
        assert result.iso_3166_1 == "GB"

        # Test pt-BR
        translator.cache.clear()
        response_pt_br = {
            "id": 12345,
            "posters": [
                {"file_path": "/path2.jpg", "iso_639_1": "pt", "iso_3166_1": "BR"}
            ],
        }
        mock_get.return_value.json.return_value = response_pt_br
        result = translator.select_best_image(tmdb_ids, ["pt-BR"], kind="poster")
        assert result is not None
        assert result.iso_639_1 == "pt"
        assert result.iso_3166_1 == "BR"

        # Test zh-CN
        translator.cache.clear()
        response_zh_cn = {
            "id": 12345,
            "logos": [
                {"file_path": "/path3.png", "iso_639_1": "zh", "iso_3166_1": "CN"}
            ],
        }
        mock_get.return_value.json.return_value = response_zh_cn
        result = translator.select_best_image(tmdb_ids, ["zh-CN"], kind="clearlogo")
        assert result is not None
        assert result.iso_639_1 == "zh"
        assert result.iso_3166_1 == "CN"

        # Test es-MX
        translator.cache.clear()
        response_es_mx = {
            "id": 12345,
            "posters": [
                {"file_path": "/path4.jpg", "iso_639_1": "es", "iso_3166_1": "MX"}
            ],
        }
        mock_get.return_value.json.return_value = response_es_mx
        result = translator.select_best_image(tmdb_ids, ["es-MX"], kind="poster")
        assert result is not None
        assert result.iso_639_1 == "es"
        assert result.iso_3166_1 == "MX"

    @patch("httpx.Client.get")
    def test_select_best_image_invalid_kind(
        self,
        mock_get: Mock,
        translator: Translator,
        mock_images_response_posters: dict[str, Any],
    ) -> None:
        """Test that invalid kind returns None."""
        configure_image_response(mock_get, mock_images_response_posters)

        tmdb_ids = TmdbIds(tmdb_id=12345, media_type="tv", season=None, episode=None)
        # "banner" is not a valid kind
        result = translator.select_best_image(
            tmdb_ids,
            ["en-US"],
            kind="banner",
        )

        assert result is None
