"""Unit tests for ImageProcessor."""

import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.image_processor import ImageProcessor
from sonarr_metadata_rewrite.image_utils import embed_marker_and_atomic_write
from sonarr_metadata_rewrite.models import ImageCandidate
from sonarr_metadata_rewrite.translator import Translator


@pytest.fixture
def image_processor(
    test_settings: Settings, translator: Translator, tmp_path: Path
) -> ImageProcessor:
    """Create ImageProcessor instance."""
    # Set rewrite_root_dir to tmp_path so backup paths work correctly
    test_settings.rewrite_root_dir = tmp_path
    return ImageProcessor(test_settings, translator)


def create_test_nfo(path: Path, tmdb_id: int) -> None:
    """Create a test NFO file with TMDB ID."""
    root = ET.Element("tvshow")
    uniqueid = ET.SubElement(root, "uniqueid", type="tmdb")
    uniqueid.text = str(tmdb_id)
    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def create_test_image(path: Path) -> None:
    """Create a minimal test image file."""
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGB", (100, 100), color="red")
    output = BytesIO()
    img.save(output, format="JPEG")
    path.write_bytes(output.getvalue())


class TestProcessSuccessScenarios:
    """Tests for successful image processing scenarios."""

    def test_process_poster_success(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test successful poster processing."""
        # Setup
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 12345)

        # Mock translator response
        candidate = ImageCandidate(
            file_path="/test_poster.jpg", iso_639_1="en", iso_3166_1="US"
        )
        image_processor.translator.select_best_image = Mock(return_value=candidate)

        # Mock HTTP download with real image data
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="blue")
        output = BytesIO()
        img.save(output, format="JPEG")
        real_image_bytes = output.getvalue()

        mock_response = Mock()
        mock_response.content = real_image_bytes
        image_processor.http_client.get = Mock(return_value=mock_response)

        # Process
        result = image_processor.process(poster_path)

        # Verify
        assert result.success is True, f"Processing failed: {result.message}"
        assert result.file_modified is True
        assert result.kind == "poster"
        assert result.selected_language == "en-US"

    def test_process_logo_success(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test successful logo processing."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        logo_path = series_dir / "logo.png"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(logo_path)
        create_test_nfo(nfo_path, 67890)

        candidate = ImageCandidate(
            file_path="/test_logo.png", iso_639_1="ja", iso_3166_1="JP"
        )
        image_processor.translator.select_best_image = Mock(return_value=candidate)

        # Mock HTTP download with real PNG data
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="red")
        output = BytesIO()
        img.save(output, format="PNG")
        real_png_bytes = output.getvalue()

        mock_response = Mock()
        mock_response.content = real_png_bytes
        image_processor.http_client.get = Mock(return_value=mock_response)

        result = image_processor.process(logo_path)

        assert result.success is True, f"Processing failed: {result.message}"
        assert result.kind == "logo"
        assert result.selected_language == "ja-JP"

    def test_process_season_poster_success(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test successful season poster processing."""
        series_dir = tmp_path / "Series"
        season_dir = series_dir / "Season 01"
        season_dir.mkdir(parents=True)

        poster_path = season_dir / "season01-poster.jpg"
        nfo_path = season_dir / "season.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 11111)

        candidate = ImageCandidate(
            file_path="/season1.jpg", iso_639_1="zh", iso_3166_1="CN"
        )
        image_processor.translator.select_best_image = Mock(return_value=candidate)

        # Mock HTTP download with real image
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="green")
        output = BytesIO()
        img.save(output, format="JPEG")
        real_image_bytes = output.getvalue()

        mock_response = Mock()
        mock_response.content = real_image_bytes
        image_processor.http_client.get = Mock(return_value=mock_response)

        result = image_processor.process(poster_path)

        assert result.success is True, f"Processing failed: {result.message}"
        assert result.kind == "poster"
        # Verify season number was passed to translator
        call_args = image_processor.translator.select_best_image.call_args
        assert call_args[0][0].season == 1

    def test_process_image_already_has_marker(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test processing image that already has the correct marker."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_nfo(nfo_path, 12345)

        # Create image with marker
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="blue")
        output = BytesIO()
        img.save(output, format="JPEG")

        candidate = ImageCandidate(
            file_path="/same_poster.jpg", iso_639_1="en", iso_3166_1="US"
        )
        marker = {"file_path": "/same_poster.jpg"}
        embed_marker_and_atomic_write(output.getvalue(), poster_path, marker)

        image_processor.translator.select_best_image = Mock(return_value=candidate)

        result = image_processor.process(poster_path)

        assert result.success is True
        assert result.file_modified is False
        assert "already matches" in result.message

    def test_process_no_nfo_found(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test processing when no NFO file exists."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"

        create_test_image(poster_path)

        result = image_processor.process(poster_path)

        assert result.success is False
        assert "TMDB ID" in result.message

    def test_process_nfo_has_no_tmdb_id(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test processing when NFO lacks TMDB ID."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)

        # Create NFO without TMDB ID
        root = ET.Element("tvshow")
        title = ET.SubElement(root, "title")
        title.text = "Test Series"
        tree = ET.ElementTree(root)
        tree.write(nfo_path, encoding="utf-8", xml_declaration=True)

        result = image_processor.process(poster_path)

        assert result.success is False
        assert "TMDB ID" in result.message

    def test_process_no_image_candidate_selected(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test when translator returns no suitable image."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 12345)

        image_processor.translator.select_best_image = Mock(return_value=None)

        result = image_processor.process(poster_path)

        assert result.success is False
        assert "No poster available" in result.message

    def test_process_tmdb_download_fails(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test handling of download failures."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 12345)

        candidate = ImageCandidate(
            file_path="/test.jpg", iso_639_1="en", iso_3166_1="US"
        )
        image_processor.translator.select_best_image = Mock(return_value=candidate)

        # Mock HTTP error
        image_processor.http_client.get = Mock(
            side_effect=httpx.RequestError("Network error")
        )

        result = image_processor.process(poster_path)

        assert result.success is False
        assert result.exception is not None

    def test_process_backup_creation_fails(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test when backup creation fails."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 12345)

        candidate = ImageCandidate(
            file_path="/test.jpg", iso_639_1="en", iso_3166_1="US"
        )
        image_processor.translator.select_best_image = Mock(return_value=candidate)

        # Create real image bytes for successful download
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="purple")
        output = BytesIO()
        img.save(output, format="JPEG")
        real_image_bytes = output.getvalue()

        mock_response = Mock()
        mock_response.content = real_image_bytes
        image_processor.http_client.get = Mock(return_value=mock_response)

        # Mock backup failure
        with patch("shutil.copy2", side_effect=PermissionError("No permission")):
            result = image_processor.process(poster_path)

        # Backup failure causes overall failure in current implementation
        assert result.success is False
        assert result.exception is not None
        assert isinstance(result.exception, PermissionError)


class TestParseImageInfo:
    """Tests for _parse_image_info method."""

    def test_parse_image_info_poster(self, image_processor: ImageProcessor) -> None:
        """Test parsing poster basename."""
        kind, season = image_processor._parse_image_info("poster.jpg")
        assert kind == "poster"
        assert season is None

    def test_parse_image_info_season_poster(
        self, image_processor: ImageProcessor
    ) -> None:
        """Test parsing season poster basenames."""
        kind, season = image_processor._parse_image_info("season01-poster.jpg")
        assert kind == "poster"
        assert season == 1

        kind, season = image_processor._parse_image_info("season10-poster.png")
        assert kind == "poster"
        assert season == 10

    def test_parse_image_info_logo(self, image_processor: ImageProcessor) -> None:
        """Test parsing logo basename."""
        kind, season = image_processor._parse_image_info("logo.png")
        assert kind == "logo"
        assert season is None

    def test_parse_image_info_invalid(self, image_processor: ImageProcessor) -> None:
        """Test parsing invalid basename."""
        kind, season = image_processor._parse_image_info("banner.jpg")
        assert kind == ""
        assert season is None


class TestResolveTmdbIds:
    """Tests for _resolve_tmdb_ids method."""

    def test_resolve_tmdb_ids_same_directory(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test resolving TMDB ID from NFO in same directory."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()

        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 99999)

        result = image_processor._resolve_tmdb_ids(poster_path, None)

        assert result is not None
        assert result.series_id == 99999
        assert result.season is None

    def test_resolve_tmdb_ids_parent_directory(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test resolving TMDB ID from NFO in parent directory."""
        series_dir = tmp_path / "Series"
        season_dir = series_dir / "Season 01"
        season_dir.mkdir(parents=True)

        poster_path = season_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 88888)

        result = image_processor._resolve_tmdb_ids(poster_path, None)

        assert result is not None
        assert result.series_id == 88888

    def test_resolve_tmdb_ids_season_nfo_priority(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test that season.nfo is preferred for season posters."""
        series_dir = tmp_path / "Series"
        season_dir = series_dir / "Season 01"
        season_dir.mkdir(parents=True)

        poster_path = season_dir / "season01-poster.jpg"
        season_nfo = season_dir / "season.nfo"
        series_nfo = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(season_nfo, 55555)
        create_test_nfo(series_nfo, 66666)

        result = image_processor._resolve_tmdb_ids(poster_path, 1)

        assert result is not None
        assert result.series_id == 55555
        assert result.season == 1


class TestCreateBackup:
    """Tests for _create_backup method."""

    def test_create_backup_creates_proper_structure(
        self, tmp_path: Path, test_settings: Settings, translator: Translator
    ) -> None:
        """Test backup creates proper directory structure."""
        # Set backup directory and rewrite root
        backup_dir = tmp_path / "backups"
        media_root = tmp_path / "media"
        test_settings.original_files_backup_dir = backup_dir
        test_settings.rewrite_root_dir = media_root

        processor = ImageProcessor(test_settings, translator)

        # Create source file
        series_dir = media_root / "Series" / "Season 1"
        series_dir.mkdir(parents=True)
        poster_path = series_dir / "poster.jpg"
        create_test_image(poster_path)

        # Create backup
        result = processor._create_backup(poster_path)

        assert result is True
        # Backup should preserve directory structure relative to media root
        expected_backup = backup_dir / "Series" / "Season 1" / "poster.jpg"
        assert expected_backup.exists()


class TestDownloadAndWriteImage:
    """Tests for _download_and_write_image method."""

    def test_download_and_write_image_extension_change(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test that extension changes are handled (jpg -> png)."""
        poster_path = tmp_path / "poster.jpg"
        create_test_image(poster_path)

        candidate = ImageCandidate(
            file_path="/test.png", iso_639_1="en", iso_3166_1="US"
        )

        # Mock HTTP response with PNG data
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (50, 50), color="green")
        output = BytesIO()
        img.save(output, format="PNG")
        png_bytes = output.getvalue()

        mock_response = Mock()
        mock_response.content = png_bytes
        image_processor.http_client.get = Mock(return_value=mock_response)

        image_processor._download_and_write_image(poster_path, candidate)

        # Original .jpg should be removed, .png should exist
        assert not poster_path.exists()
        assert (tmp_path / "poster.png").exists()

    def test_download_and_write_image_atomic_write(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test atomic write is used."""
        poster_path = tmp_path / "poster.jpg"

        candidate = ImageCandidate(
            file_path="/test.jpg", iso_639_1="en", iso_3166_1="US"
        )

        # Create real image bytes
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (50, 50), color="yellow")
        output = BytesIO()
        img.save(output, format="JPEG")
        real_image_bytes = output.getvalue()

        mock_response = Mock()
        mock_response.content = real_image_bytes
        image_processor.http_client.get = Mock(return_value=mock_response)

        with patch("os.replace") as mock_replace:
            image_processor._download_and_write_image(poster_path, candidate)
            # Verify atomic operation was used
            assert mock_replace.called


class TestErrorScenarios:
    """Tests for error handling scenarios."""

    def test_process_network_failure_during_tmdb_download(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test network error during download."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 12345)

        candidate = ImageCandidate(
            file_path="/test.jpg", iso_639_1="en", iso_3166_1="US"
        )
        image_processor.translator.select_best_image = Mock(return_value=candidate)

        # Mock network error
        image_processor.http_client.get = Mock(
            side_effect=httpx.NetworkError("Connection failed")
        )

        result = image_processor.process(poster_path)

        assert result.success is False
        assert result.exception is not None
        # Original file should still exist
        assert poster_path.exists()

    def test_process_corrupted_image_response(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test handling of corrupted image data."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 12345)

        candidate = ImageCandidate(
            file_path="/test.jpg", iso_639_1="en", iso_3166_1="US"
        )
        image_processor.translator.select_best_image = Mock(return_value=candidate)

        # Mock corrupted response - invalid image data
        mock_response = Mock()
        mock_response.content = b"not a valid image"
        image_processor.http_client.get = Mock(return_value=mock_response)

        result = image_processor.process(poster_path)

        assert result.success is False
        # Original file should still exist
        assert poster_path.exists()

    def test_process_permission_error_on_backup(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test permission error during backup creation."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 12345)

        candidate = ImageCandidate(
            file_path="/test.jpg", iso_639_1="en", iso_3166_1="US"
        )
        image_processor.translator.select_best_image = Mock(return_value=candidate)

        # Create real image bytes
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="orange")
        output = BytesIO()
        img.save(output, format="JPEG")
        real_image_bytes = output.getvalue()

        mock_response = Mock()
        mock_response.content = real_image_bytes
        image_processor.http_client.get = Mock(return_value=mock_response)

        with patch("shutil.copy2", side_effect=PermissionError("Denied")):
            result = image_processor.process(poster_path)

        # Permission error on backup causes overall failure
        assert result.success is False
        assert result.exception is not None

    def test_process_disk_full_during_write(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test disk full error during image write."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 12345)

        candidate = ImageCandidate(
            file_path="/test.jpg", iso_639_1="en", iso_3166_1="US"
        )
        image_processor.translator.select_best_image = Mock(return_value=candidate)

        mock_response = Mock()
        mock_response.content = b"image data"
        image_processor.http_client.get = Mock(return_value=mock_response)

        with patch("os.write", side_effect=OSError("Disk full")):
            result = image_processor.process(poster_path)

        assert result.success is False
        assert result.exception is not None

    def test_process_file_deleted_during_processing(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test graceful handling when file is deleted mid-processing."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 12345)

        # Delete NFO after initial check
        def side_effect_delete(*args, **kwargs):
            nfo_path.unlink()
            return None

        with patch.object(
            image_processor.translator,
            "select_best_image",
            side_effect=side_effect_delete,
        ):
            result = image_processor.process(poster_path)

        # Should handle gracefully
        assert result.success is False
