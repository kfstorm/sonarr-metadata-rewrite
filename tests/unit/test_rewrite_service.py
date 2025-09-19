"""Unit tests for rewrite service."""

from collections.abc import Callable, Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.models import TranslatedContent, TranslatedString
from sonarr_metadata_rewrite.rewrite_service import RewriteService


@pytest.fixture
def rewrite_service(test_settings: Settings) -> RewriteService:
    """Create rewrite service instance."""
    return RewriteService(test_settings)


def test_rewrite_service_initialization(rewrite_service: RewriteService) -> None:
    """Test rewrite service initialization."""
    assert rewrite_service.settings is not None
    assert rewrite_service.cache is not None
    assert rewrite_service.translator is not None
    assert rewrite_service.metadata_processor is not None
    assert rewrite_service.file_monitor is not None
    assert rewrite_service.file_scanner is not None


@patch("sonarr_metadata_rewrite.rewrite_service.logger")
def test_service_start_stop(mock_logger: Mock, rewrite_service: RewriteService) -> None:
    """Test service start/stop functionality."""
    with (
        patch.object(rewrite_service.file_monitor, "start") as mock_monitor_start,
        patch.object(rewrite_service.file_scanner, "start") as mock_scanner_start,
        patch.object(rewrite_service.file_monitor, "stop") as mock_monitor_stop,
        patch.object(rewrite_service.file_scanner, "stop") as mock_scanner_stop,
        patch.object(rewrite_service.translator, "close") as mock_translator_close,
        patch.object(rewrite_service.cache, "close") as mock_cache_close,
    ):

        # Test start
        rewrite_service.start()
        mock_monitor_start.assert_called_once()
        mock_scanner_start.assert_called_once()

        # Test stop
        rewrite_service.stop()
        mock_monitor_stop.assert_called_once()
        mock_scanner_stop.assert_called_once()
        mock_translator_close.assert_called_once()
        mock_cache_close.assert_called_once()


def test_is_running(rewrite_service: RewriteService) -> None:
    """Test is_running status check."""
    with (
        patch.object(rewrite_service.file_monitor, "is_running", return_value=True),
        patch.object(rewrite_service.file_scanner, "is_running", return_value=False),
    ):
        assert rewrite_service.is_running() is True

    with (
        patch.object(rewrite_service.file_monitor, "is_running", return_value=False),
        patch.object(rewrite_service.file_scanner, "is_running", return_value=True),
    ):
        assert rewrite_service.is_running() is True

    with (
        patch.object(rewrite_service.file_monitor, "is_running", return_value=False),
        patch.object(rewrite_service.file_scanner, "is_running", return_value=False),
    ):
        assert rewrite_service.is_running() is False


@patch("sonarr_metadata_rewrite.rewrite_service.logger")
def test_service_integration_successful_processing(
    mock_logger: Mock,
    rewrite_service: RewriteService,
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test integration: service processes files successfully through callback."""
    test_path = create_test_files("tvshow.nfo", test_data_dir / "integration_test.nfo")

    # Mock translator to return successful translation
    with patch.object(
        rewrite_service.metadata_processor.translator, "get_translations"
    ) as mock_get_translations:
        mock_get_translations.return_value = {
            "zh-CN": TranslatedContent(
                title=TranslatedString(content="中文标题", language="zh-CN"),
                description=TranslatedString(content="中文描述", language="zh-CN"),
            )
        }

        # Directly call the callback (simulating file monitor/scanner trigger)
        rewrite_service._process_file(test_path)

        # Verify successful processing was logged
        mock_logger.info.assert_called()
        log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        assert any("✅" in call for call in log_calls)


@patch("sonarr_metadata_rewrite.rewrite_service.logger")
def test_service_integration_processing_failure(
    mock_logger: Mock,
    rewrite_service: RewriteService,
    test_data_dir: Path,
    create_test_files: Callable[[str, Path], Path],
    patch_fetch_with_retry: Generator[None, None, None],
) -> None:
    """Test integration: service handles processing failures through callback."""
    # patch_fetch_with_retry fixture is used to mock HTTP requests
    test_path = create_test_files("no_tmdb_id.nfo", test_data_dir / "failure_test.nfo")

    # Directly call the callback (simulating file monitor/scanner trigger)
    rewrite_service._process_file(test_path)

    # Verify failure was logged with warning
    mock_logger.warning.assert_called()
    log_calls = [call[0][0] for call in mock_logger.warning.call_args_list]
    assert any("⚠️" in call for call in log_calls)


@patch("sonarr_metadata_rewrite.rewrite_service.logger")
def test_service_integration_processing_exception(
    mock_logger: Mock, rewrite_service: RewriteService, test_data_dir: Path
) -> None:
    """Test integration: service handles processing exceptions through callback."""
    test_path = test_data_dir / "tvshow.nfo"
    test_path.write_text("dummy content")

    with patch.object(
        rewrite_service.metadata_processor,
        "process_file",
        side_effect=Exception("Test error"),
    ):
        rewrite_service._process_file(test_path)

        mock_logger.exception.assert_called()
