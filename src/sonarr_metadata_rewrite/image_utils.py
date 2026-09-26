"""Image utility functions for embedding and reading metadata markers."""

import contextlib
import json
from dataclasses import asdict
from io import BytesIO
from pathlib import Path

import piexif  # type: ignore[import-untyped]
from PIL import Image, PngImagePlugin

from sonarr_metadata_rewrite.models import ImageCandidate


def read_embedded_marker(path: Path) -> ImageCandidate | None:
    """Read embedded marker from image metadata.

    Args:
        path: Path to image file

    Returns:
        ImageCandidate if marker is present, None otherwise
    """
    if not path.exists():
        return None

    try:
        with Image.open(path) as img:
            if img.format == "PNG":
                # Check for tEXt or iTXt chunks
                marker_text = img.info.get("sonarr_metadata_marker")
                if marker_text:
                    return ImageCandidate(**json.loads(marker_text))

            elif img.format == "JPEG":
                # Check EXIF UserComment
                if "exif" in img.info:
                    exif_dict = piexif.load(img.info["exif"])
                    user_comment = exif_dict.get("Exif", {}).get(
                        piexif.ExifIFD.UserComment
                    )
                    if user_comment and isinstance(user_comment, bytes):
                        # UserComment is encoded, decode it.
                        if user_comment.startswith(
                            (b"ASCII\x00\x00\x00", b"UNICODE\x00")
                        ):
                            user_comment = user_comment[8:]
                        with contextlib.suppress(
                            UnicodeDecodeError, json.JSONDecodeError
                        ):
                            marker_text = user_comment.decode("utf-8")
                            return ImageCandidate(**json.loads(marker_text))
    except Exception:
        # Image may be corrupted or format not supported
        pass

    return None


def embed_marker(raw_bytes: bytes, marker: ImageCandidate) -> bytes:
    """Embed a marker into image bytes.

    Args:
        raw_bytes: Raw image bytes to process
        marker: ImageCandidate to embed as JSON

    Returns:
        Encoded image bytes with the marker
    """
    marker_json = json.dumps(asdict(marker), separators=(",", ":"))

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

    return output.getvalue()
