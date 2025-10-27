"""Unit tests for image_utils module."""

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image, PngImagePlugin

from sonarr_metadata_rewrite.image_utils import (
    PIEXIF_AVAILABLE,
    embed_marker_and_atomic_write,
    read_embedded_marker,
)


def _create_image_bytes(size: tuple[int, int], color: str, fmt: str) -> bytes:
    """Helper to create image bytes in specified format."""
    img = Image.new("RGB", size, color=color)
    output = BytesIO()
    img.save(output, format=fmt)
    return output.getvalue()


class TestReadEmbeddedMarker:
    """Tests for read_embedded_marker() function."""

    def test_read_png_with_text_chunk(self, tmp_path: Path) -> None:
        """Test reading marker from PNG with tEXt chunk."""
        # Create PNG with tEXt chunk containing JSON marker
        marker_data = {
            "rewritten_by": "test",
            "tmdb_id": 12345,
            "language": "en-US",
        }
        png_path = tmp_path / "test.png"

        img = Image.new("RGB", (100, 100), color="red")
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("sonarr_metadata_marker", json.dumps(marker_data))
        img.save(png_path, "PNG", pnginfo=pnginfo)

        # Read marker
        result = read_embedded_marker(png_path)

        assert result == marker_data

    @pytest.mark.skipif(not PIEXIF_AVAILABLE, reason="piexif not available")
    def test_read_jpeg_with_exif(self, tmp_path: Path) -> None:
        """Test reading marker from JPEG with EXIF UserComment."""
        import piexif

        marker_data = {
            "rewritten_by": "test",
            "tmdb_id": 67890,
            "language": "ja-JP",
        }
        jpeg_path = tmp_path / "test.jpg"

        # Create JPEG with EXIF UserComment
        img = Image.new("RGB", (100, 100), color="blue")

        user_comment = json.dumps(marker_data).encode("utf-8")
        exif_dict = {"Exif": {piexif.ExifIFD.UserComment: user_comment}}
        exif_bytes = piexif.dump(exif_dict)

        img.save(jpeg_path, "JPEG", exif=exif_bytes)

        # Read marker
        result = read_embedded_marker(jpeg_path)

        assert result == marker_data

    def test_read_no_marker_returns_none(self, tmp_path: Path) -> None:
        """Test reading from image without marker returns None."""
        png_path = tmp_path / "clean.png"
        img = Image.new("RGB", (100, 100), color="green")
        img.save(png_path, "PNG")

        result = read_embedded_marker(png_path)

        assert result is None

    def test_read_malformed_json_returns_none(self, tmp_path: Path) -> None:
        """Test reading image with malformed JSON returns None."""
        png_path = tmp_path / "bad.png"
        img = Image.new("RGB", (100, 100), color="yellow")
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("sonarr-metadata-rewrite", "not valid json{")
        img.save(png_path, "PNG", pnginfo=pnginfo)

        result = read_embedded_marker(png_path)

        assert result is None

    def test_read_unsupported_format(self, tmp_path: Path) -> None:
        """Test reading unsupported image format returns None."""
        # Create a GIF file
        gif_path = tmp_path / "test.gif"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(gif_path, "GIF")

        result = read_embedded_marker(gif_path)

        assert result is None


class TestEmbedMarkerAndAtomicWrite:
    """Tests for embed_marker_and_atomic_write() function."""

    def test_embed_png_with_marker(self, tmp_path: Path) -> None:
        """Test embedding marker in PNG and writing atomically."""
        marker_data = {
            "rewritten_by": "test",
            "tmdb_id": 11111,
            "language": "zh-CN",
        }
        dst = tmp_path / "output.png"

        # Create PNG bytes
        raw_bytes = _create_image_bytes((50, 50), "purple", "PNG")

        embed_marker_and_atomic_write(raw_bytes, dst, marker_data)

        # Verify file exists
        assert dst.exists()

        # Verify marker can be read back
        result = read_embedded_marker(dst)
        assert result == marker_data

    @pytest.mark.skipif(not PIEXIF_AVAILABLE, reason="piexif not available")
    def test_embed_jpeg_with_exif(self, tmp_path: Path) -> None:
        """Test embedding marker in JPEG via EXIF UserComment."""
        marker_data = {
            "rewritten_by": "test",
            "tmdb_id": 22222,
            "language": "fr-FR",
        }
        dst = tmp_path / "output.jpg"

        # Create JPEG bytes
        raw_bytes = _create_image_bytes((60, 60), "orange", "JPEG")

        embed_marker_and_atomic_write(raw_bytes, dst, marker_data)

        # Verify file exists
        assert dst.exists()

        # Verify marker can be read back
        result = read_embedded_marker(dst)
        assert result == marker_data

    @pytest.mark.skipif(PIEXIF_AVAILABLE, reason="piexif is available")
    def test_embed_jpeg_without_piexif(self, tmp_path: Path) -> None:
        """Test JPEG embedding when piexif is not available."""
        marker_data = {"rewritten_by": "test", "tmdb_id": 33333}
        dst = tmp_path / "output.jpg"

        raw_bytes = _create_image_bytes((40, 40), "cyan", "JPEG")

        # Should write JPEG without EXIF marker
        embed_marker_and_atomic_write(raw_bytes, dst, marker_data)

        assert dst.exists()
        # Marker won't be present since piexif is not available
        result = read_embedded_marker(dst)
        assert result is None

    def test_atomic_write_uses_temp_file(self, tmp_path: Path) -> None:
        """Test that atomic write uses temporary file and os.replace()."""
        marker_data = {"rewritten_by": "test"}
        dst = tmp_path / "atomic.png"

        raw_bytes = _create_image_bytes((30, 30), "white", "PNG")

        with patch("os.replace") as mock_replace:
            embed_marker_and_atomic_write(raw_bytes, dst, marker_data)

            # Verify os.replace was called (atomic operation)
            assert mock_replace.called
            args = mock_replace.call_args[0]
            # First arg should be temp file, second should be destination
            assert str(args[1]) == str(dst)
            assert args[0] != str(dst)  # Temp file is different

    def test_invalid_image_data_raises_error(self, tmp_path: Path) -> None:
        """Test that invalid image data raises appropriate exception."""
        marker_data = {"rewritten_by": "test"}
        dst = tmp_path / "invalid.png"

        # Provide corrupted/invalid image bytes
        invalid_bytes = b"not valid image data"

        with pytest.raises((OSError, ValueError)):
            embed_marker_and_atomic_write(invalid_bytes, dst, marker_data)
