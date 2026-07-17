"""Sonarr and Radarr Metadata Rewrite.

A compatibility layer that monitors Sonarr TV and Radarr movie metadata files
and localizes them with TMDB translations in desired languages.
"""

try:
    from ._version import __version__
except ImportError:
    # Fallback for development installations without version file
    __version__ = "0.0.0+unknown"
