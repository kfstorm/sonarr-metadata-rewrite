"""Unit test specific configuration and fixtures."""

import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from diskcache import Cache  # type: ignore[import-untyped]

import sonarr_metadata_rewrite.image_processor
import sonarr_metadata_rewrite.metadata_processor
from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.retry_utils import retry
from sonarr_metadata_rewrite.translator import Translator

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
            return ET.parse(nfo_path)

        return parse_file()

    with patch.object(
        sonarr_metadata_rewrite.metadata_processor.MetadataProcessor,
        "_parse_nfo_with_retry",
        fast_parse_nfo_with_retry,
    ):
        yield


@pytest.fixture(autouse=True)
def patch_image_download_retry() -> Generator[None, None, None]:
    """Patch retry decorator in image processor to use minimal timeout for tests."""
    original_retry = sonarr_metadata_rewrite.image_processor.retry

    def fast_retry(
        timeout: float = 15.0,
        interval: float = 0.5,
        log_interval: float = 2.0,
        exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
        """Fast retry for tests with minimal timeout."""
        return original_retry(
            timeout=0.1,  # Very short timeout for unit tests
            interval=0.01,  # Very short interval
            log_interval=0.05,
            exceptions=exceptions,
        )

    with patch.object(
        sonarr_metadata_rewrite.image_processor,
        "retry",
        fast_retry,
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
        Translator,
        "_fetch_with_retry",
        mock_fetch_with_retry,
    ):
        yield


@pytest.fixture
def translator(test_settings: Settings, tmp_path: Path) -> Translator:
    """Create a Translator instance with a temporary cache for testing."""
    cache = Cache(tmp_path / "cache")
    return Translator(test_settings, cache)
