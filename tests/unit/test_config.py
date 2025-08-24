"""Unit tests for configuration module."""

import os
from unittest.mock import patch

import pytest

from sonarr_metadata.config import get_tmdb_api_key


class TestGetTmdbApiKey:
    """Test TMDB API key retrieval."""

    def test_get_tmdb_api_key_success(self) -> None:
        """Test successful API key retrieval."""
        test_key = "test_api_key_1234567890abcdef"

        with patch.dict(os.environ, {"TMDB_API_KEY": test_key}):
            result = get_tmdb_api_key()
            assert result == test_key

    def test_get_tmdb_api_key_missing(self) -> None:
        """Test error when API key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(
                ValueError, match="TMDB_API_KEY environment variable is required"
            ):
                get_tmdb_api_key()

    def test_get_tmdb_api_key_empty(self) -> None:
        """Test error when API key is empty."""
        with patch.dict(os.environ, {"TMDB_API_KEY": ""}):
            with pytest.raises(
                ValueError, match="TMDB_API_KEY environment variable is required"
            ):
                get_tmdb_api_key()
