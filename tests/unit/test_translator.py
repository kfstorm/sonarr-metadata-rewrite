"""Unit tests for translator."""

import json
from typing import Any
from unittest.mock import Mock, patch

import httpx
import pytest
from diskcache import Cache  # type: ignore[import-untyped]

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.models import TmdbIds
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
    mock_get.assert_called_once_with("/tv/12345/translations")

    # Verify parsed translations
    assert isinstance(translations, dict)
    assert len(translations) == 3

    # Check Chinese translation
    assert "zh-CN" in translations
    zh_cn = translations["zh-CN"]
    assert zh_cn.title == "测试剧集"
    assert zh_cn.description == "这是一个测试剧集的描述"
    assert zh_cn.language == "zh-CN"

    # Check English translation
    assert "en-US" in translations
    en_us = translations["en-US"]
    assert en_us.title == "Test Series"
    assert en_us.description == "This is a test series description"
    assert en_us.language == "en-US"

    # Check Japanese translation (no country code)
    assert "ja" in translations
    ja = translations["ja"]
    assert ja.title == "テストシリーズ"
    assert ja.description == "これはテストシリーズの説明です"
    assert ja.language == "ja"


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
    mock_get.assert_called_once_with("/tv/12345/season/1/episode/2/translations")

    # Verify parsed translations
    assert isinstance(translations, dict)
    assert len(translations) == 1
    assert "zh-CN" in translations

    zh_cn = translations["zh-CN"]
    assert zh_cn.title == "测试剧集"
    assert zh_cn.description == "这是一个测试剧集的描述"
    assert zh_cn.language == "zh-CN"


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
def test_rate_limit_preserves_cache_on_failure(
    mock_get: Mock, translator: Translator
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
