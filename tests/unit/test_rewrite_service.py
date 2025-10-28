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
async def test_service_start_stop(
    mock_logger: Mock, rewrite_service: RewriteService
) -> None:
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
        await rewrite_service.start()
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
        rewrite_service._process_file_callback(test_path)

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
    rewrite_service._process_file_callback(test_path)

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
        rewrite_service._process_file_callback(test_path)

        mock_logger.exception.assert_called()


@patch("sonarr_metadata_rewrite.rewrite_service.logger")
def test_service_integration_processing_error_with_exception(
    mock_logger: Mock,
    rewrite_service: RewriteService,
    test_data_dir: Path,
) -> None:
    """Test integration: service logs error when ProcessResult contains exception."""
    # Create a corrupted NFO file that will cause an exception during processing
    corrupted_nfo = test_data_dir / "corrupted.nfo"
    corrupted_nfo.write_text("CORRUPTED CONTENT")

    rewrite_service._process_file_callback(corrupted_nfo)

    # Verify error was logged with stack trace when exception occurs in processing
    mock_logger.error.assert_called()
    # Verify the call includes exc_info parameter
    call_args = mock_logger.error.call_args
    assert "exc_info" in call_args[1]
    assert call_args[1]["exc_info"] is not None
    # Verify the message format
    assert "❌" in call_args[0][0]
    assert "Processing error:" in call_args[0][0]


# Image-specific RewriteService tests


def test_process_file_routes_image_to_image_processor(
    rewrite_service: RewriteService, tmp_path: Path
) -> None:
    """Test that image files are routed to ImageProcessor."""
    poster_path = tmp_path / "poster.jpg"
    poster_path.write_bytes(b"fake image")

    with (
        patch.object(rewrite_service.image_processor, "process") as mock_image_process,
        patch.object(
            rewrite_service.metadata_processor, "process_file"
        ) as mock_metadata_process,
    ):
        rewrite_service._process_file(poster_path)

        # ImageProcessor should be called
        mock_image_process.assert_called_once_with(poster_path)
        # MetadataProcessor should NOT be called
        mock_metadata_process.assert_not_called()


def test_process_file_routes_nfo_to_metadata_processor(
    rewrite_service: RewriteService, tmp_path: Path
) -> None:
    """Test that NFO files are routed to MetadataProcessor."""
    nfo_path = tmp_path / "tvshow.nfo"
    nfo_path.write_text("<tvshow><title>Test</title></tvshow>")

    with (
        patch.object(rewrite_service.image_processor, "process") as mock_image_process,
        patch.object(
            rewrite_service.metadata_processor, "process_file"
        ) as mock_metadata_process,
    ):
        rewrite_service._process_file(nfo_path)

        # MetadataProcessor should be called
        mock_metadata_process.assert_called_once_with(nfo_path)
        # ImageProcessor should NOT be called
        mock_image_process.assert_not_called()


@patch("sonarr_metadata_rewrite.rewrite_service.logger")
def test_process_file_callback_logs_image_success(
    mock_logger: Mock, rewrite_service: RewriteService, tmp_path: Path
) -> None:
    """Test callback logs success for image processing."""
    poster_path = tmp_path / "poster.jpg"
    poster_path.write_bytes(b"fake image")

    with patch.object(rewrite_service.image_processor, "process") as mock_image_process:
        from sonarr_metadata_rewrite.models import ImageProcessResult

        # Mock successful image processing
        mock_image_process.return_value = ImageProcessResult(
            success=True,
            file_path=poster_path,
            message="Poster rewritten successfully",
            kind="poster",
            file_modified=True,
        )

        rewrite_service._process_file_callback(poster_path)

        # Verify success was logged
        mock_logger.info.assert_called()
        log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        assert any("✅" in call for call in log_calls)


@patch("sonarr_metadata_rewrite.rewrite_service.logger")
def test_process_file_callback_logs_image_failure(
    mock_logger: Mock, rewrite_service: RewriteService, tmp_path: Path
) -> None:
    """Test callback logs failure for image processing."""
    logo_path = tmp_path / "clearlogo.png"
    logo_path.write_bytes(b"fake image")

    with patch.object(rewrite_service.image_processor, "process") as mock_image_process:
        from sonarr_metadata_rewrite.models import ImageProcessResult

        # Mock failed image processing
        mock_image_process.return_value = ImageProcessResult(
            success=False,
            file_path=logo_path,
            message="No logo available in preferred languages",
            kind="clearlogo",
        )

        rewrite_service._process_file_callback(logo_path)

        # Verify warning was logged
        mock_logger.warning.assert_called()
        log_calls = [call[0][0] for call in mock_logger.warning.call_args_list]
        assert any("⚠️" in call for call in log_calls)


def test_integration_both_processors_working(
    rewrite_service: RewriteService,
    tmp_path: Path,
    create_test_files: Callable[[str, Path], Path],
) -> None:
    """Test both MetadataProcessor and ImageProcessor work together."""
    # Create NFO file
    nfo_path = create_test_files("tvshow.nfo", tmp_path / "tvshow.nfo")

    # Create poster file
    poster_path = tmp_path / "poster.jpg"
    poster_path.write_bytes(b"fake image")

    with (
        patch.object(
            rewrite_service.metadata_processor, "process_file"
        ) as mock_metadata,
        patch.object(rewrite_service.image_processor, "process") as mock_image,
    ):
        from sonarr_metadata_rewrite.models import ImageProcessResult, ProcessResult

        # Mock successful NFO processing
        mock_metadata.return_value = ProcessResult(
            success=True, file_path=nfo_path, message="NFO processed"
        )

        # Mock successful image processing
        mock_image.return_value = ImageProcessResult(
            success=True,
            file_path=poster_path,
            message="Poster processed",
            kind="poster",
            file_modified=True,
        )

        # Process both files
        result_nfo = rewrite_service._process_file(nfo_path)
        result_image = rewrite_service._process_file(poster_path)

        # Verify both processors were called appropriately
        mock_metadata.assert_called_once_with(nfo_path)
        mock_image.assert_called_once_with(poster_path)

        # Verify results
        assert result_nfo.success is True
        assert result_image.success is True


def test_image_processing_skipped_when_disabled(
    rewrite_service: RewriteService, tmp_path: Path
) -> None:
    """When enable_image_rewrite is False, image files should be skipped."""
    # Disable image rewriting
    rewrite_service.settings.enable_image_rewrite = False

    # Create a rewritable image file (poster)
    poster_path = tmp_path / "poster.jpg"
    poster_path.write_bytes(b"fake image")

    with (
        patch.object(rewrite_service.image_processor, "process") as mock_image_process,
        patch.object(
            rewrite_service.metadata_processor, "process_file"
        ) as mock_metadata_process,
    ):
        result = rewrite_service._process_file(poster_path)

        # Image processor should not be called when disabled
        mock_image_process.assert_not_called()
        mock_metadata_process.assert_not_called()

        # Should return a success skip result
        assert result.success is True
        assert result.file_modified is False
        assert "disabled" in result.message
