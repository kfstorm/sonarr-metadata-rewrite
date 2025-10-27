"""Image utility functions for embedding and reading metadata markers."""

import json
import os
import tempfile
from io import BytesIO
from pathlib import Path

import piexif  # type: ignore[import-untyped]
from PIL import Image, PngImagePlugin


def read_embedded_marker(path: Path) -> dict[str, str] | None:
    """Read embedded marker from image metadata.

    Args:
        path: Path to image file

    Returns:
        Parsed JSON marker dict if present, None otherwise
    """
    if not path.exists():
        return None

    try:
        with Image.open(path) as img:
            if img.format == "PNG":
                # Check for tEXt or iTXt chunks
                marker_text = img.info.get("sonarr_metadata_marker")
                if marker_text:
                    return json.loads(marker_text)

            elif img.format == "JPEG":
                # Check EXIF UserComment
                if "exif" in img.info:
                    exif_dict = piexif.load(img.info["exif"])
                    user_comment = exif_dict.get("Exif", {}).get(
                        piexif.ExifIFD.UserComment
                    )
                    if user_comment:
                        # UserComment is encoded, decode it
                        if isinstance(user_comment, bytes):
                            # Skip encoding prefix if present
                            if user_comment.startswith(b"ASCII\x00\x00\x00"):
                                user_comment = user_comment[8:]
                            elif user_comment.startswith(b"UNICODE\x00"):
                                user_comment = user_comment[8:]
                            try:
                                marker_text = user_comment.decode("utf-8")
                                return json.loads(marker_text)
                            except (UnicodeDecodeError, json.JSONDecodeError):
                                pass
    except Exception:
        # Image may be corrupted or format not supported
        pass

    return None


def embed_marker_and_atomic_write(
    raw_bytes: bytes, dst: Path, marker: dict[str, str]
) -> None:
    """Embed marker into image and write atomically.

    Args:
        raw_bytes: Raw image bytes to process
        dst: Destination path for final image
        marker: Marker dictionary to embed as JSON (values must be JSON-serializable)
    """
    marker_json = json.dumps(marker, separators=(",", ":"))

    # Load image from bytes
    img = Image.open(BytesIO(raw_bytes))

    # Create output buffer
    output = BytesIO()

    if img.format == "PNG":
        # Add PNG tEXt chunk
        meta = PngImagePlugin.PngInfo()
        meta.add_text("sonarr_metadata_marker", marker_json)
        img.save(output, format="PNG", pnginfo=meta)

    elif img.format in ("JPEG", "JPG"):
        # Add EXIF UserComment
        # Create or update EXIF data
        exif_dict = {"Exif": {piexif.ExifIFD.UserComment: marker_json.encode()}}
        exif_bytes = piexif.dump(exif_dict)
        img.save(output, format="JPEG", exif=exif_bytes, quality=95)
    else:
        # Unsupported format, save as-is
        img.save(output, format=img.format)

    # Write atomically using temp file
    final_bytes = output.getvalue()
    dst.parent.mkdir(parents=True, exist_ok=True)

    # Create temp file in same directory for atomic replace
    fd, temp_path = tempfile.mkstemp(dir=dst.parent, prefix=".tmp_", suffix=dst.suffix)
    try:
        os.write(fd, final_bytes)
        os.close(fd)
        # Atomic replace
        os.replace(temp_path, dst)
    except Exception:
        # Clean up temp file on error
        try:
            os.close(fd)
        except Exception:
            pass
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        raise
