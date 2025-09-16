"""Unit test specific configuration and fixtures."""

import time
import xml.etree.ElementTree as ET
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

import sonarr_metadata_rewrite.metadata_processor
import sonarr_metadata_rewrite.translator
from sonarr_metadata_rewrite.retry_utils import retry

if TYPE_CHECKING:
    from xml.etree.ElementTree import ElementTree


@pytest.fixture(autouse=True)
def patch_time_sleep() -> Generator[None, None, None]:
    """Patch time.sleep to be instant for retry logic, but preserve test timing.

    This speeds up retry logic while allowing tests that need real timing to work.
    """
    original_sleep = time.sleep

    def selective_sleep(duration: float) -> None:
        # Allow short sleeps used in test timing logic
        if duration >= 0.05:  # 50ms or more, likely test timing
            return original_sleep(duration)
        # Make very short sleeps (retry intervals) instant
        return None

    with patch.object(time, "sleep", side_effect=selective_sleep):
        yield


@pytest.fixture(autouse=True)
def patch_retry_timeout() -> Generator[None, None, None]:
    """Reduce retry timeout for unit tests to speed up failure cases."""

    def fast_parse_nfo_with_retry(
        self: object, nfo_path: Path
    ) -> "ElementTree[ET.Element]":
        @retry(
            timeout=0.1,  # Very short timeout for unit tests
            interval=0.01,  # Very short interval
            log_interval=0.05,
            exceptions=(ET.ParseError, OSError),
        )
        def parse_file() -> "ElementTree[ET.Element]":
            try:
                return ET.parse(nfo_path)
            except ET.ParseError as e:
                # Handle multi-episode files like the real implementation
                if "junk after document element" in str(e):
                    return parse_multi_episode_file(nfo_path)
                raise

        def parse_multi_episode_file(nfo_path: Path) -> "ElementTree[ET.Element]":
            """Parse NFO file with multiple <episodedetails> root elements."""
            try:
                # Read the file content
                with open(nfo_path, encoding="utf-8") as f:
                    content = f.read()

                # Wrap multiple root elements in a container for parsing
                wrapped_content = f"<episodes>{content}</episodes>"

                # Parse the wrapped content
                root = ET.fromstring(wrapped_content)
                if root is None:
                    raise ET.ParseError("Failed to parse wrapped multi-episode content")

                # Find all episodedetails elements
                episode_elements = root.findall("episodedetails")

                if not episode_elements:
                    raise ET.ParseError(
                        "No episodedetails elements found in multi-episode file"
                    )

                # Use the first episode as the primary element
                first_episode = episode_elements[0]

                # Create a new tree with just the first episode
                tree: ElementTree[ET.Element] = ET.ElementTree(first_episode)

                return tree

            except Exception as e:
                # If multi-episode parsing fails, re-raise as ParseError with context
                raise ET.ParseError(f"Failed to parse multi-episode file: {e}") from e

        return parse_file()

    with patch.object(
        sonarr_metadata_rewrite.metadata_processor.MetadataProcessor,
        "_parse_nfo_with_retry",
        fast_parse_nfo_with_retry,
    ):
        yield


@pytest.fixture
def patch_fetch_with_retry() -> Generator[None, None, None]:
    """Mock _fetch_with_retry to avoid real HTTP requests in integration tests.

    This is not autouse=True because translator unit tests need to test
    the real HTTP behavior. Use this fixture explicitly in tests that
    need fast execution without HTTP calls.
    """

    def mock_fetch_with_retry(
        self: object, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Mock fetch that returns empty results to simulate API failures/no results."""
        # Return empty results for external ID lookups (find endpoint)
        if endpoint.startswith("/find/"):
            return {"tv_results": [], "movie_results": [], "person_results": []}

        # Return empty translations for translation endpoints
        if endpoint.endswith("/translations"):
            return {"translations": []}

        # Return empty results for any other endpoint
        return {}

    with patch.object(
        sonarr_metadata_rewrite.translator.Translator,
        "_fetch_with_retry",
        mock_fetch_with_retry,
    ):
        yield
