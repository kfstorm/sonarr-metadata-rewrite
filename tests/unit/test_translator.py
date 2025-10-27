"""Unit tests for translator."""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import httpx
import pytest
from diskcache import Cache  # type: ignore[import-untyped]

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.models import TmdbIds, TranslatedContent, TranslatedString
from sonarr_metadata_rewrite.translator import Translator


@pytest.fixture
def translator(test_settings: Settings) -> Translator:
    """Create translator instance."""
    cache = Cache(str(test_settings.cache_dir))
    translator = Translator(test_settings, cache)
    # Clear the cache to ensure clean tests
    translator.cache.clear()
    return translator


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
    series_ids = TmdbIds(series_id=12345)
    assert str(series_ids) == "tv/12345"

    # Episode
    episode_ids = TmdbIds(series_id=12345, season=1, episode=2)
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

    tmdb_ids = TmdbIds(series_id=12345)
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

    tmdb_ids = TmdbIds(series_id=12345, season=1, episode=2)
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
def test_get_translations_http_error(mock_get: Mock, translator: Translator) -> None:
    """Test HTTP error handling."""
    # Mock HTTP error
    mock_get.side_effect = httpx.HTTPError("API error")

    tmdb_ids = TmdbIds(series_id=12345)

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

    tmdb_ids = TmdbIds(series_id=12345)

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

    tmdb_ids = TmdbIds(series_id=12345)
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

    tmdb_ids = TmdbIds(series_id=12345)
    translations = translator.get_translations(tmdb_ids)

    # Should only include translations with content
    assert len(translations) == 1
    assert "en-US" in translations
    assert "zh-CN" not in translations


def test_cache_functionality(
    translator: Translator, mock_series_response: dict[str, Any]
) -> None:
    """Test DiskCache functionality."""
    tmdb_ids = TmdbIds(series_id=12345)
    cache_key = f"translations:{tmdb_ids}/translations"

    # Verify cache starts empty
    assert cache_key not in translator.cache

    # Add item to cache
    translations = {"en-US": mock_series_response}
    translator.cache.set(cache_key, translations, expire=3600)

    # Verify cache contains the item
    assert cache_key in translator.cache
    cached_data = translator.cache[cache_key]
    assert cached_data == translations


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

    tmdb_ids = TmdbIds(series_id=12345)

    # First call should hit API and cache result
    translations1 = translator.get_translations(tmdb_ids)
    assert mock_get.call_count == 1
    assert len(translations1) == 3

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

    tmdb_ids = TmdbIds(series_id=68034)
    result = translator.get_original_details(tmdb_ids)

    # Verify API call
    mock_get.assert_called_once_with("/tv/68034", params=None)

    # Verify result
    assert result is not None
    original_language, original_title = result
    assert original_language == "zh"
    assert original_title == "大明王朝1566"


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

    tmdb_ids = TmdbIds(series_id=12345, season=1, episode=1)
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

    tmdb_ids = TmdbIds(series_id=12345)

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

    tmdb_ids = TmdbIds(series_id=12345)
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

    tmdb_ids = TmdbIds(series_id=68034)

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

    tmdb_ids = TmdbIds(series_id=12345)
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

    tmdb_ids = TmdbIds(series_id=12345)

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


@patch("httpx.Client.get")
def test_non_rate_limit_http_error_no_retry(
    mock_get: Mock, translator: Translator
) -> None:
    """Test that non-rate-limit HTTP errors are not retried."""
    # Return 500 error (not rate limit)
    server_error_response = Mock()
    server_error_response.status_code = 500
    server_error = httpx.HTTPStatusError(
        "Internal Server Error", request=Mock(), response=server_error_response
    )
    mock_get.side_effect = server_error

    tmdb_ids = TmdbIds(series_id=12345)

    # Should raise the error immediately without retries
    with pytest.raises(httpx.HTTPStatusError, match="Internal Server Error"):
        translator.get_translations(tmdb_ids)

    # Should have made only 1 attempt (no retries)
    assert mock_get.call_count == 1


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

        tmdb_ids = TmdbIds(series_id=12345)

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

    tmdb_ids = TmdbIds(series_id=12345)
    cache_key = f"translations:{tmdb_ids}"

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


def test_ensure_new_format_backward_compatibility(translator: Translator) -> None:
    """Test backward compatibility with old cached TranslatedContent format."""

    # Create mock old format TranslatedContent objects (pre-model change)
    # These simulate cached data with string fields instead of TranslatedString objects
    old_format_content_1 = SimpleNamespace(
        title="旧格式标题",  # str instead of TranslatedString
        description="旧格式描述",  # str instead of TranslatedString
        language="zh-CN",  # old format had language field
    )

    old_format_content_2 = SimpleNamespace(
        title="Old Format Title", description="Old format description", language="en-US"
    )

    # Create new format TranslatedContent for mixed testing
    new_format_content = TranslatedContent(
        title=TranslatedString(content="新格式标题", language="ja"),
        description=TranslatedString(content="新格式描述", language="ja"),
    )

    # Create cached data with mix of old and new formats
    cached_data = {
        "zh-CN": old_format_content_1,
        "en-US": old_format_content_2,
        "ja": new_format_content,
    }

    # Test the conversion method
    converted_data = translator._ensure_new_format(cached_data)  # type: ignore[arg-type]

    # Verify all data is now in new format
    assert len(converted_data) == 3

    # Check converted old format data
    zh_cn = converted_data["zh-CN"]
    assert isinstance(zh_cn, TranslatedContent)
    assert isinstance(zh_cn.title, TranslatedString)
    assert isinstance(zh_cn.description, TranslatedString)
    assert zh_cn.title.content == "旧格式标题"
    assert zh_cn.title.language == "zh-CN"
    assert zh_cn.description.content == "旧格式描述"
    assert zh_cn.description.language == "zh-CN"

    en_us = converted_data["en-US"]
    assert isinstance(en_us, TranslatedContent)
    assert isinstance(en_us.title, TranslatedString)
    assert isinstance(en_us.description, TranslatedString)
    assert en_us.title.content == "Old Format Title"
    assert en_us.title.language == "en-US"
    assert en_us.description.content == "Old format description"
    assert en_us.description.language == "en-US"

    # Check that already new format data is preserved unchanged
    ja = converted_data["ja"]
    assert isinstance(ja, TranslatedContent)
    assert isinstance(ja.title, TranslatedString)
    assert isinstance(ja.description, TranslatedString)
    assert ja.title.content == "新格式标题"
    assert ja.title.language == "ja"
    assert ja.description.content == "新格式描述"
    assert ja.description.language == "ja"


def test_get_translations_cache_backward_compatibility_integration(
    translator: Translator,
) -> None:
    """Test cache backward compatibility in real get_translations workflow."""

    # Create old format cached data
    old_cached_content = SimpleNamespace(
        title="缓存的旧标题", description="缓存的旧描述", language="zh-CN"
    )

    # Manually set old format data in cache to simulate pre-upgrade cache
    tmdb_ids = TmdbIds(series_id=12345)
    cache_key = f"translations:{tmdb_ids}"
    translator.cache.set(cache_key, {"zh-CN": old_cached_content})

    # Call get_translations - should convert old format to new format
    translations = translator.get_translations(tmdb_ids)

    # Verify the cached data was converted properly
    assert len(translations) == 1
    assert "zh-CN" in translations

    zh_cn = translations["zh-CN"]
    assert isinstance(zh_cn, TranslatedContent)
    assert isinstance(zh_cn.title, TranslatedString)
    assert isinstance(zh_cn.description, TranslatedString)
    assert zh_cn.title.content == "缓存的旧标题"
    assert zh_cn.title.language == "zh-CN"
    assert zh_cn.description.content == "缓存的旧描述"
    assert zh_cn.description.language == "zh-CN"


@patch("httpx.Client.get")
def test_get_with_cache_404_caching(mock_get: Mock, translator: Translator) -> None:
    """Test that _get_with_cache properly caches 404 responses."""
    # Mock 404 HTTP error
    not_found_response = Mock()
    not_found_response.status_code = 404
    not_found_error = httpx.HTTPStatusError(
        "Not Found", request=Mock(), response=not_found_response
    )
    mock_get.side_effect = not_found_error

    # Define a simple fetch function that calls _fetch_with_retry
    def fetch_func() -> dict[str, Any]:
        return translator._fetch_with_retry("/test/endpoint")

    cache_key = "test_404_cache"
    default_value = {"test": "default"}

    # First call should hit API and cache the default value
    result1 = translator._get_with_cache(cache_key, fetch_func, default_value)
    assert result1 == default_value
    assert mock_get.call_count == 1

    # Verify the default value was cached
    assert cache_key in translator.cache
    assert translator.cache[cache_key] == default_value

    # Second call should use cache (no additional API calls)
    result2 = translator._get_with_cache(cache_key, fetch_func, default_value)
    assert result2 == default_value
    assert mock_get.call_count == 1  # Still only 1 call

    # Results should be identical
    assert result1 == result2


@patch("httpx.Client.get")
def test_get_translations_404_cached(mock_get: Mock, translator: Translator) -> None:
    """Test that get_translations properly caches 404 responses as empty dict."""
    # Mock 404 HTTP error
    not_found_response = Mock()
    not_found_response.status_code = 404
    not_found_error = httpx.HTTPStatusError(
        "Not Found", request=Mock(), response=not_found_response
    )
    mock_get.side_effect = not_found_error

    tmdb_ids = TmdbIds(series_id=99999)  # Non-existent series
    cache_key = f"translations:{tmdb_ids}"

    # Verify cache starts empty
    assert cache_key not in translator.cache

    # First call should hit API and return empty dict
    translations1 = translator.get_translations(tmdb_ids)
    assert translations1 == {}
    assert mock_get.call_count == 1

    # Verify empty dict was cached
    assert cache_key in translator.cache
    assert translator.cache[cache_key] == {}

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

    tmdb_ids = TmdbIds(series_id=99999)  # Non-existent series
    cache_key = f"original_details:{tmdb_ids}"

    # Verify cache starts empty
    assert cache_key not in translator.cache

    # First call should hit API and return None
    details1 = translator.get_original_details(tmdb_ids)
    assert details1 is None
    assert mock_get.call_count == 1

    # Verify None was cached
    assert cache_key in translator.cache
    assert translator.cache[cache_key] is None

    # Second call should use cache (no additional API calls)
    details2 = translator.get_original_details(tmdb_ids)
    assert details2 is None
    assert mock_get.call_count == 1  # Still only 1 call

    # Results should be identical
    assert details1 == details2


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
    cache_key = f"external_find:{external_source}:{external_id}"

    # Verify cache starts empty
    assert cache_key not in translator.cache

    # First call should hit API and return None
    result1 = translator.find_tmdb_id_by_external_id(external_id, external_source)
    assert result1 is None
    assert mock_get.call_count == 1

    # Verify None was cached
    assert cache_key in translator.cache
    assert translator.cache[cache_key] is None

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
        mock_get.return_value.json.return_value = mock_images_response_posters
        mock_get.return_value.raise_for_status = Mock()

        tmdb_ids = TmdbIds(series_id=12345, season=None, episode=None)
        result = translator.select_best_image(tmdb_ids, ["en-US"], kind="poster")

        assert result is not None
        assert result.file_path == "/poster_en_us.jpg"
        assert result.iso_639_1 == "en"
        assert result.iso_3166_1 == "US"

    @patch("httpx.Client.get")
    def test_select_best_image_logo_exact_match(
        self,
        mock_get: Mock,
        translator: Translator,
        mock_images_response_logos: dict[str, Any],
    ) -> None:
        """Test selecting logo with exact language-country match."""
        mock_get.return_value.json.return_value = mock_images_response_logos
        mock_get.return_value.raise_for_status = Mock()

        tmdb_ids = TmdbIds(series_id=67890, season=None, episode=None)
        result = translator.select_best_image(tmdb_ids, ["ja-JP"], kind="logo")

        assert result is not None
        assert result.file_path == "/logo_ja.jpg"
        assert result.iso_639_1 == "ja"
        assert result.iso_3166_1 == "JP"

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
        mock_get.return_value.json.return_value = season_response
        mock_get.return_value.raise_for_status = Mock()

        tmdb_ids = TmdbIds(series_id=12345, season=1, episode=None)
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
        mock_get.return_value.json.return_value = mock_images_response_posters
        mock_get.return_value.raise_for_status = Mock()

        tmdb_ids = TmdbIds(series_id=12345, season=None, episode=None)
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
        mock_get.return_value.json.return_value = mock_images_response_posters
        mock_get.return_value.raise_for_status = Mock()

        tmdb_ids = TmdbIds(series_id=12345, season=None, episode=None)
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
        mock_get.return_value.json.return_value = response_with_nulls
        mock_get.return_value.raise_for_status = Mock()

        tmdb_ids = TmdbIds(series_id=12345, season=None, episode=None)
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
        mock_get.return_value.json.return_value = mock_images_response_posters
        mock_get.return_value.raise_for_status = Mock()

        tmdb_ids = TmdbIds(series_id=12345, season=None, episode=None)
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
        not_found_response = Mock()
        not_found_response.status_code = 404
        not_found_error = httpx.HTTPStatusError(
            "Not Found", request=Mock(), response=not_found_response
        )
        mock_get.side_effect = not_found_error

        tmdb_ids = TmdbIds(series_id=99999, season=None, episode=None)
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
        mock_get.return_value.json.return_value = mock_images_response_posters
        mock_get.return_value.raise_for_status = Mock()

        tmdb_ids = TmdbIds(series_id=12345, season=None, episode=None)

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
        mock_get.return_value.json.return_value = empty_response
        mock_get.return_value.raise_for_status = Mock()

        tmdb_ids = TmdbIds(series_id=12345, season=None, episode=None)
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
        mock_get.return_value.json.return_value = response_en_gb
        mock_get.return_value.raise_for_status = Mock()

        tmdb_ids = TmdbIds(series_id=12345, season=None, episode=None)
        result = translator.select_best_image(tmdb_ids, ["en-GB"], kind="poster")
        assert result is not None
        assert result.iso_639_1 == "en"
        assert result.iso_3166_1 == "GB"

        # Test pt-BR
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
        response_zh_cn = {
            "id": 12345,
            "logos": [
                {"file_path": "/path3.png", "iso_639_1": "zh", "iso_3166_1": "CN"}
            ],
        }
        mock_get.return_value.json.return_value = response_zh_cn
        result = translator.select_best_image(tmdb_ids, ["zh-CN"], kind="logo")
        assert result is not None
        assert result.iso_639_1 == "zh"
        assert result.iso_3166_1 == "CN"

        # Test es-MX
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
        mock_get.return_value.json.return_value = mock_images_response_posters
        mock_get.return_value.raise_for_status = Mock()

        tmdb_ids = TmdbIds(series_id=12345, season=None, episode=None)
        # "banner" is not a valid kind
        result = translator.select_best_image(
            tmdb_ids,
            ["en-US"],
            kind="banner",
        )

        assert result is None
