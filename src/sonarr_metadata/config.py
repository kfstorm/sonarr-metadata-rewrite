"""Basic configuration for sonarr-metadata-rewrite."""

import os


def get_tmdb_api_key() -> str:
    """Get TMDB API key from environment."""
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        raise ValueError("TMDB_API_KEY environment variable is required")
    return api_key
