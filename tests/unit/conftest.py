"""Unit test specific configuration and fixtures."""

import time
import xml.etree.ElementTree as ET
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

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
    import sonarr_metadata_rewrite.metadata_processor

    def fast_parse_nfo_with_retry(
        self: object, nfo_path: Path
    ) -> "ElementTree[ET.Element]":
        from sonarr_metadata_rewrite.retry_utils import retry

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
