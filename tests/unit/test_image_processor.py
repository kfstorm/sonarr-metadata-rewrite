"""Unit tests for ImageProcessor."""

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import httpx
import pytest
from PIL import Image

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.file_utils import parse_image_info
from sonarr_metadata_rewrite.image_processor import ImageProcessor
from sonarr_metadata_rewrite.image_utils import (
    embed_marker_and_atomic_write,
    read_embedded_marker,
)
from sonarr_metadata_rewrite.models import ImageCandidate, TmdbIds
from sonarr_metadata_rewrite.translator import Translator


@contextmanager
def mock_translator_select(
    image_processor: ImageProcessor,
    *,
    return_value: ImageCandidate | None = None,
    side_effect: Any | None = None,
) -> Iterator[Mock]:
    """Context manager to mock translator.select_best_image on this image_processor.

    Usage:
        with mock_translator_select(image_processor, return_value=candidate):
            ...
    """
    with patch.object(
        image_processor.translator,
        "select_best_image",
        return_value=return_value,
        side_effect=side_effect,
    ) as mocked:
        yield mocked


@pytest.fixture
def image_processor(
    test_settings: Settings, translator: Translator, tmp_path: Path
) -> ImageProcessor:
    """Create ImageProcessor instance."""
    # Set rewrite_root_dirs to [tmp_path] so backup paths work correctly
    test_settings.rewrite_root_dirs = [tmp_path]
    return ImageProcessor(test_settings, translator)


def create_test_nfo(path: Path, tmdb_id: int, root_tag: str = "tvshow") -> None:
    """Create a test NFO file with TMDB ID."""
    root = ET.Element(root_tag)
    uniqueid = ET.SubElement(root, "uniqueid", type="tmdb")
    uniqueid.text = str(tmdb_id)
    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def create_test_image(path: Path) -> None:
    """Create a minimal test image file."""
    img = Image.new("RGB", (100, 100), color="red")
    output = BytesIO()
    img.save(output, format="JPEG")
    path.write_bytes(output.getvalue())


def create_marked_jpeg(path: Path) -> None:
    """Create a JPEG marked as a Japanese TMDB image."""
    image = Image.new("RGB", (100, 100), color="red")
    output = BytesIO()
    image.save(output, format="JPEG")
    marker = ImageCandidate(file_path="/ja.jpg", iso_639_1="ja", iso_3166_1="JP")
    embed_marker_and_atomic_write(output.getvalue(), path, marker)


def backup_path_for(image_processor: ImageProcessor, image_path: Path) -> Path:
    """Return backup path for an image using absolute-path layout."""
    backup_root = image_processor.settings.original_files_backup_dir
    assert backup_root is not None
    return backup_root / image_path.relative_to("/")


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
        image_processor.translator.select_best_image = Mock(return_value=candidate)  # type: ignore[method-assign]

        # Mock HTTP download with real image data

        img = Image.new("RGB", (100, 100), color="blue")
        output = BytesIO()
        img.save(output, format="JPEG")
        real_image_bytes = output.getvalue()

        mock_response = Mock()
        mock_response.content = real_image_bytes
        image_processor.http_client.get = Mock(return_value=mock_response)  # type: ignore[method-assign]

        # Process
        result = image_processor.process(poster_path)

        # Verify
        assert result.success is True, f"Processing failed: {result.message}"
        assert result.file_modified is True
        assert result.kind == "poster"
        assert result.selected_language == "en-US"

    def test_process_clearlogo_success(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test successful clearlogo processing."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        clearlogo_path = series_dir / "clearlogo.png"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(clearlogo_path)
        create_test_nfo(nfo_path, 67890)

        candidate = ImageCandidate(
            file_path="/test_clearlogo.png", iso_639_1="ja", iso_3166_1="JP"
        )
        image_processor.translator.select_best_image = Mock(return_value=candidate)  # type: ignore[method-assign]

        # Mock HTTP download with real PNG data

        img = Image.new("RGB", (100, 100), color="red")
        output = BytesIO()
        img.save(output, format="PNG")
        real_png_bytes = output.getvalue()

        mock_response = Mock()
        mock_response.content = real_png_bytes
        image_processor.http_client.get = Mock(return_value=mock_response)  # type: ignore[method-assign]

        result = image_processor.process(clearlogo_path)

        assert result.success is True, f"Processing failed: {result.message}"
        assert result.kind == "clearlogo"
        assert result.selected_language == "ja-JP"

    def test_process_movie_clearlogo_success(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test movie clearlogos use the shared image rewrite flow."""
        movie_dir = tmp_path / "Movie"
        movie_dir.mkdir()
        clearlogo_path = movie_dir / "clearlogo.png"
        create_test_image(clearlogo_path)
        create_test_nfo(movie_dir / "movie.nfo", 550, root_tag="movie")

        candidate = ImageCandidate(
            file_path="/movie_clearlogo.png", iso_639_1="zh", iso_3166_1="CN"
        )
        image = Image.new("RGB", (100, 100), color="red")
        output = BytesIO()
        image.save(output, format="PNG")
        response = Mock(content=output.getvalue())
        image_processor.http_client.get = Mock(return_value=response)  # type: ignore[method-assign]

        with mock_translator_select(image_processor, return_value=candidate) as select:
            result = image_processor.process(clearlogo_path)

        assert result.success is True, result.message
        assert result.kind == "clearlogo"
        select.assert_called_once_with(
            TmdbIds(tmdb_id=550, media_type="movie"),
            image_processor.settings.preferred_languages,
            "clearlogo",
        )

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

        img = Image.new("RGB", (100, 100), color="blue")
        output = BytesIO()
        img.save(output, format="JPEG")

        candidate = ImageCandidate(
            file_path="/same_poster.jpg", iso_639_1="en", iso_3166_1="US"
        )
        embed_marker_and_atomic_write(output.getvalue(), poster_path, candidate)

        image_processor.translator.select_best_image = Mock(return_value=candidate)  # type: ignore[method-assign]

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

        with mock_translator_select(image_processor, return_value=None):
            result = image_processor.process(poster_path)

        assert result.success is False
        assert "No poster available" in result.message

    def test_process_revert_to_backup_when_no_candidate(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test reverting to backup when no preferred language available."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()

        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        backup_path = backup_path_for(image_processor, poster_path)
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        # Create original backup (no marker)
        original_img = Image.new("RGB", (100, 100), color="white")
        original_img.save(backup_path, format="JPEG")

        create_marked_jpeg(poster_path)

        create_test_nfo(nfo_path, 12345)

        # No candidate available
        with mock_translator_select(image_processor, return_value=None):
            result = image_processor.process(poster_path)

        # Should revert to backup
        assert result.success is True
        assert result.file_modified is True
        assert "Reverted poster to original" in result.message

        # Verify poster reverted to backup content
        restored_marker = read_embedded_marker(poster_path)
        assert restored_marker is None

    def test_process_already_original_when_no_candidate(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test when current file is already original and no candidate available."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()

        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        backup_path = backup_path_for(image_processor, poster_path)
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        # Create current file without marker (original)
        create_test_image(poster_path)

        # Create backup
        create_test_image(backup_path)

        create_test_nfo(nfo_path, 12345)

        # No candidate available
        with mock_translator_select(image_processor, return_value=None):
            result = image_processor.process(poster_path)

        # Should report already original
        assert result.success is False
        assert "already original" in result.message
        assert result.file_modified is False

    def test_process_no_backup_when_no_candidate(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test when no candidate and no backup available."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()

        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_marked_jpeg(poster_path)

        create_test_nfo(nfo_path, 12345)

        # No candidate available
        with mock_translator_select(image_processor, return_value=None):
            result = image_processor.process(poster_path)

        # Should report no image available
        assert result.success is False
        assert "No poster available" in result.message
        assert result.file_modified is False

    def test_process_revert_with_stem_matching(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test reverting to backup with different extension (stem matching)."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()

        # Current file is poster.jpg with marker
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        backup_parent = backup_path_for(image_processor, poster_path).parent
        backup_parent.mkdir(parents=True, exist_ok=True)
        # Backup is poster.png (different extension)
        backup_path = backup_parent / "poster.png"

        # Create original backup as PNG (no marker)
        original_img = Image.new("RGB", (100, 100), color="white")
        original_img.save(backup_path, format="PNG")

        create_marked_jpeg(poster_path)

        create_test_nfo(nfo_path, 12345)

        # No candidate available
        with mock_translator_select(image_processor, return_value=None):
            result = image_processor.process(poster_path)

        # Should revert to backup even with different extension
        assert result.success is True
        assert result.file_modified is True
        assert "Reverted poster to original" in result.message

        # Verify poster reverted (should still be JPEG since we copy over it)
        assert poster_path.exists()
        restored_marker = read_embedded_marker(poster_path)
        # Backup was PNG without marker, copied to JPEG location
        # The file will have PNG content but .jpg extension
        assert restored_marker is None

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

        # Mock HTTP error
        with mock_translator_select(image_processor, return_value=candidate):
            with patch.object(
                image_processor.http_client,
                "get",
                side_effect=httpx.RequestError("Network error"),
            ):
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

        # Create real image bytes for successful download

        img = Image.new("RGB", (100, 100), color="purple")
        output = BytesIO()
        img.save(output, format="JPEG")
        real_image_bytes = output.getvalue()

        mock_response = Mock()
        mock_response.content = real_image_bytes

        # Mock backup failure
        with mock_translator_select(image_processor, return_value=candidate):
            with patch.object(
                image_processor.http_client, "get", return_value=mock_response
            ):
                with patch(
                    "shutil.copy2", side_effect=PermissionError("No permission")
                ):
                    result = image_processor.process(poster_path)

        # Backup failure causes overall failure in current implementation
        assert result.success is False
        assert result.exception is not None
        assert isinstance(result.exception, PermissionError)


class TestParseImageInfo:
    """Tests for _parse_image_info method."""

    def test_parse_image_info_poster(self) -> None:
        """Test parsing poster basename."""
        kind, season = parse_image_info("poster.jpg")
        assert kind == "poster"
        assert season is None

    def test_parse_image_info_season_poster(self) -> None:
        """Test parsing season poster basenames."""
        kind, season = parse_image_info("season01-poster.jpg")
        assert kind == "poster"
        assert season == 1

        kind, season = parse_image_info("season10-poster.png")
        assert kind == "poster"
        assert season == 10

    def test_parse_image_info_clearlogo(self) -> None:
        """Test parsing clearlogo basename."""
        kind, season = parse_image_info("clearlogo.png")
        assert kind == "clearlogo"
        assert season is None

    def test_parse_image_info_specials(self) -> None:
        """Test parsing specials poster basename."""
        kind, season = parse_image_info("season-specials-poster.jpg")
        assert kind == "poster"
        assert season == 0

    def test_parse_image_info_invalid(self) -> None:
        """Test parsing invalid basename."""
        kind, season = parse_image_info("banner.jpg")
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
        assert result.tmdb_id == 99999
        assert result.season is None

    def test_resolve_movie_ids_from_video_named_nfo(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test movie root NFO names do not need to be movie.nfo."""
        movie_dir = tmp_path / "Movie"
        movie_dir.mkdir()
        poster_path = movie_dir / "poster.jpg"
        create_test_image(poster_path)
        create_test_nfo(movie_dir / "Movie.2024.nfo", 550, root_tag="movie")

        result = image_processor._resolve_tmdb_ids(poster_path, None)

        assert result == TmdbIds(tmdb_id=550, media_type="movie")

    def test_resolve_ignores_episode_nfo_next_to_tvshow(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test episode NFOs do not make TV artwork root selection ambiguous."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        create_test_image(poster_path)
        create_test_nfo(series_dir / "tvshow.nfo", 99999)
        create_test_nfo(series_dir / "episode.nfo", 99999, root_tag="episodedetails")

        result = image_processor._resolve_tmdb_ids(poster_path, None)

        assert result is not None
        assert result.tmdb_id == 99999
        assert result.media_type == "tv"

    def test_resolve_ignores_malformed_nfo_next_to_movie(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test malformed NFO files do not prevent movie artwork resolution."""
        movie_dir = tmp_path / "Movie"
        movie_dir.mkdir()
        poster_path = movie_dir / "poster.jpg"
        create_test_image(poster_path)
        (movie_dir / "broken.nfo").write_text("<movie>", encoding="utf-8")
        create_test_nfo(movie_dir / "movie.nfo", 550, root_tag="movie")

        assert image_processor._resolve_tmdb_ids(poster_path, None) == TmdbIds(
            tmdb_id=550, media_type="movie"
        )

    @pytest.mark.parametrize("root_count", [0, 2])
    def test_resolve_rejects_missing_or_ambiguous_roots(
        self, tmp_path: Path, image_processor: ImageProcessor, root_count: int
    ) -> None:
        """Test image ownership needs exactly one same-directory root NFO."""
        image_dir = tmp_path / "Media"
        image_dir.mkdir()
        poster_path = image_dir / "poster.jpg"
        create_test_image(poster_path)
        for index in range(root_count):
            create_test_nfo(
                image_dir / f"root-{index}.nfo",
                550 + index,
                root_tag="movie" if index else "tvshow",
            )

        assert image_processor._resolve_tmdb_ids(poster_path, None) is None

    def test_resolve_rejects_movie_season_poster(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test movie roots cannot select season artwork."""
        movie_dir = tmp_path / "Movie"
        movie_dir.mkdir()
        poster_path = movie_dir / "season01-poster.jpg"
        create_test_image(poster_path)
        create_test_nfo(movie_dir / "movie.nfo", 550, root_tag="movie")

        assert image_processor._resolve_tmdb_ids(poster_path, 1) is None


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

        img = Image.new("RGB", (50, 50), color="green")
        output = BytesIO()
        img.save(output, format="PNG")
        png_bytes = output.getvalue()

        mock_response = Mock()
        mock_response.content = png_bytes
        image_processor.http_client.get = Mock(return_value=mock_response)  # type: ignore[method-assign]

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

        img = Image.new("RGB", (50, 50), color="yellow")
        output = BytesIO()
        img.save(output, format="JPEG")
        real_image_bytes = output.getvalue()

        mock_response = Mock()
        mock_response.content = real_image_bytes
        image_processor.http_client.get = Mock(return_value=mock_response)  # type: ignore[method-assign]

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

        # Mock network error
        with mock_translator_select(image_processor, return_value=candidate):
            with patch.object(
                image_processor.http_client,
                "get",
                side_effect=httpx.NetworkError("Connection failed"),
            ):
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

        # Mock corrupted response - invalid image data
        mock_response = Mock()
        mock_response.content = b"not a valid image"
        with mock_translator_select(image_processor, return_value=candidate):
            with patch.object(
                image_processor.http_client, "get", return_value=mock_response
            ):
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

        # Create real image bytes

        img = Image.new("RGB", (100, 100), color="orange")
        output = BytesIO()
        img.save(output, format="JPEG")
        real_image_bytes = output.getvalue()

        mock_response = Mock()
        mock_response.content = real_image_bytes
        # http client mocked inside the context below

        with mock_translator_select(image_processor, return_value=candidate):
            with patch.object(
                image_processor.http_client, "get", return_value=mock_response
            ):
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
        mock_response = Mock()
        mock_response.content = b"image data"

        with mock_translator_select(image_processor, return_value=candidate):
            with patch.object(
                image_processor.http_client, "get", return_value=mock_response
            ):
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
        def side_effect_delete(*args: object, **kwargs: object) -> None:
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


class TestAdditionalCoverageScenarios:
    """Additional tests for coverage improvement."""

    def test_process_unrecognized_image_filename(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test unrecognized image filename."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()

        unrecognized_path = series_dir / "banner.jpg"
        create_test_image(unrecognized_path)

        result = image_processor.process(unrecognized_path)

        assert result.success is False
        assert "Unrecognized image file" in result.message
        assert result.kind == ""

    def test_process_image_nfo_not_found(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test NFO not found."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()

        poster_path = series_dir / "poster.jpg"
        create_test_image(poster_path)

        result = image_processor.process(poster_path)

        assert result.success is False
        assert "Could not resolve TMDB ID from NFO" in result.message

    def test_process_no_backup_when_backup_dir_none(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test no backup when backup_dir is None."""
        image_processor.settings.original_files_backup_dir = None

        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 12345)

        candidate = ImageCandidate(
            file_path="/new.jpg", iso_639_1="en", iso_3166_1="US"
        )
        image_processor.translator.select_best_image = Mock(return_value=candidate)  # type: ignore[method-assign]

        img = Image.new("RGB", (100, 100), color="green")
        output = BytesIO()
        img.save(output, format="JPEG")
        mock_response = Mock(content=output.getvalue())
        image_processor.http_client.get = Mock(return_value=mock_response)  # type: ignore[method-assign]

        result = image_processor.process(poster_path)

        assert result.success is True
        assert result.backup_created is False

    def test_process_extension_change_removes_old_file(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test old file removed when extension changes."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()

        old_poster = series_dir / "poster.png"
        nfo_path = series_dir / "tvshow.nfo"
        create_test_image(old_poster)
        create_test_nfo(nfo_path, 12345)

        # TMDB returns .jpg
        candidate = ImageCandidate(
            file_path="/test.jpg", iso_639_1="en", iso_3166_1="US"
        )
        image_processor.translator.select_best_image = Mock(return_value=candidate)  # type: ignore[method-assign]

        img = Image.new("RGB", (100, 100), color="blue")
        output = BytesIO()
        img.save(output, format="JPEG")
        mock_response = Mock(content=output.getvalue())
        image_processor.http_client.get = Mock(return_value=mock_response)  # type: ignore[method-assign]

        result = image_processor.process(old_poster)

        assert result.success is True
        assert not old_poster.exists()
        assert (series_dir / "poster.jpg").exists()

    def test_process_unsupported_tmdb_format(
        self, tmp_path: Path, image_processor: ImageProcessor
    ) -> None:
        """Test error when TMDB returns unsupported format."""
        series_dir = tmp_path / "Series"
        series_dir.mkdir()
        poster_path = series_dir / "poster.jpg"
        nfo_path = series_dir / "tvshow.nfo"

        create_test_image(poster_path)
        create_test_nfo(nfo_path, 12345)

        candidate = ImageCandidate(
            file_path="/test.webp", iso_639_1="en", iso_3166_1="US"
        )
        image_processor.translator.select_best_image = Mock(return_value=candidate)  # type: ignore[method-assign]

        mock_response = Mock(content=b"fake webp data")
        image_processor.http_client.get = Mock(return_value=mock_response)  # type: ignore[method-assign]

        result = image_processor.process(poster_path)

        assert result.success is False
        assert "Unsupported image format" in result.message

    def test_close_http_client(self, image_processor: ImageProcessor) -> None:
        """Test closing HTTP client."""
        image_processor.close()

        # Verify client closed
        with pytest.raises(RuntimeError, match="client has been closed"):
            image_processor.http_client.get("http://example.com")
