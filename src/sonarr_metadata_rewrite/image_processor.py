"""Image processor for rewriting poster and logo images."""

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.image_utils import (
    embed_marker_and_atomic_write,
    read_embedded_marker,
)
from sonarr_metadata_rewrite.models import ImageProcessResult, TmdbIds
from sonarr_metadata_rewrite.nfo_utils import (
    IMAGE_EXTENSIONS,
    extract_tmdb_id,
)
from sonarr_metadata_rewrite.nfo_utils import (
    parse_image_info as util_parse_image_info,
)
from sonarr_metadata_rewrite.retry_utils import retry
from sonarr_metadata_rewrite.translator import Translator

if TYPE_CHECKING:
    from sonarr_metadata_rewrite.models import ImageCandidate

logger = logging.getLogger(__name__)

# TMDB image base URL
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"


class ImageProcessor:
    """Processor for poster and logo image files."""

    def __init__(self, settings: Settings, translator: Translator):
        self.settings = settings
        self.translator = translator
        self.http_client = httpx.Client(timeout=30.0)

    def process(self, image_path: Path) -> ImageProcessResult:
        """Process a single image file.

        Args:
            image_path: Path to image file to process

        Returns:
            ImageProcessResult with processing details
        """
        try:
            # Determine image kind and scope
            basename = image_path.name
            kind, season_num = util_parse_image_info(basename)

            if not kind:
                return ImageProcessResult(
                    success=False,
                    file_path=image_path,
                    message=f"Unrecognized image file: {basename}",
                    kind="",
                )

            # Resolve TMDB IDs from NFO
            tmdb_ids = self._resolve_tmdb_ids(image_path, season_num)
            if not tmdb_ids:
                return ImageProcessResult(
                    success=False,
                    file_path=image_path,
                    message="Could not resolve TMDB ID from NFO",
                    kind=kind,
                )

            # Select best image candidate
            candidate = self.translator.select_best_image(
                tmdb_ids, self.settings.preferred_languages, kind
            )

            if not candidate:
                preferred_langs = ", ".join(self.settings.preferred_languages)
                return ImageProcessResult(
                    success=False,
                    file_path=image_path,
                    message=(
                        f"No {kind} available in preferred languages "
                        f"[{preferred_langs}]"
                    ),
                    kind=kind,
                )

            # Check if current file matches candidate
            if image_path.exists():
                current_marker = read_embedded_marker(image_path)
                if (
                    current_marker
                    and current_marker.get("file_path") == candidate.file_path
                ):
                    lang_str = f"{candidate.iso_639_1}-{candidate.iso_3166_1}"
                    return ImageProcessResult(
                        success=True,
                        file_path=image_path,
                        message=(
                            f"{kind.capitalize()} already matches selected candidate"
                        ),
                        kind=kind,
                        selected_language=lang_str,
                        selected_file_path=candidate.file_path,
                    )

            # Create backup if file exists
            backup_created = self._create_backup(image_path)

            # Download and write image
            self._download_and_write_image(image_path, candidate)

            lang_str = f"{candidate.iso_639_1}-{candidate.iso_3166_1}"
            return ImageProcessResult(
                success=True,
                file_path=image_path,
                message=f"{kind.capitalize()} rewritten with {lang_str} version",
                kind=kind,
                backup_created=backup_created,
                file_modified=True,
                selected_language=lang_str,
                selected_file_path=candidate.file_path,
            )

        except Exception as e:
            return ImageProcessResult(
                success=False,
                file_path=image_path,
                message=f"Processing error: {e}",
                exception=e,
                kind="",
            )

    def _resolve_tmdb_ids(
        self, image_path: Path, season_num: int | None
    ) -> TmdbIds | None:
        """Resolve TMDB IDs from associated NFO file.

        Args:
            image_path: Path to image file
            season_num: Season number if season-level image, None for series-level

        Returns:
            TmdbIds if resolved, None otherwise
        """
        # For series-level images, look for tvshow.nfo
        if season_num is None:
            # Search up to 3 levels for tvshow.nfo
            current_dir = image_path.parent
            for _ in range(3):
                nfo_path = current_dir / "tvshow.nfo"
                if nfo_path.exists():
                    tmdb_id = extract_tmdb_id(nfo_path)
                    if tmdb_id:
                        return TmdbIds(series_id=tmdb_id)
                parent = current_dir.parent
                if parent == current_dir:
                    break
                current_dir = parent
        else:
            # For season-level images, look for season.nfo in same directory
            nfo_path = image_path.parent / "season.nfo"
            if nfo_path.exists():
                tmdb_id = extract_tmdb_id(nfo_path)
                if tmdb_id:
                    return TmdbIds(series_id=tmdb_id, season=season_num)

            # Fallback: look for tvshow.nfo upward
            current_dir = image_path.parent
            for _ in range(3):
                nfo_path = current_dir / "tvshow.nfo"
                if nfo_path.exists():
                    tmdb_id = extract_tmdb_id(nfo_path)
                    if tmdb_id:
                        return TmdbIds(series_id=tmdb_id, season=season_num)
                parent = current_dir.parent
                if parent == current_dir:
                    break
                current_dir = parent

        return None

    def _create_backup(self, image_path: Path) -> bool:
        """Create backup of existing image file.

        Args:
            image_path: Path to image file

        Returns:
            True if backup was created, False otherwise
        """
        if not image_path.exists() or self.settings.original_files_backup_dir is None:
            return False

        backup_dir = self.settings.original_files_backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create backup path maintaining structure
        rel_path = image_path.relative_to(self.settings.rewrite_root_dir)
        backup_path = backup_dir / rel_path

        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, backup_path)
        return True

    def _download_and_write_image(
        self, dst_path: Path, candidate: "ImageCandidate"
    ) -> None:
        """Download image from TMDB and write with embedded marker.

        Args:
            dst_path: Destination path for image
            candidate: ImageCandidate with file_path and language info
        """

        # Build full URL
        url = f"{TMDB_IMAGE_BASE_URL}{candidate.file_path}"

        # Download with retry
        @retry(timeout=30.0, interval=1.0, exceptions=(httpx.HTTPError,))
        def download() -> bytes:
            response = self.http_client.get(url)
            response.raise_for_status()
            return response.content

        raw_bytes = download()

        # Build marker
        marker = {
            "file_path": candidate.file_path,
            "iso_639_1": candidate.iso_639_1 or "",
            "iso_3166_1": candidate.iso_3166_1 or "",
        }

        # Compute destination path with correct extension
        # Extract extension from candidate.file_path
        candidate_ext = Path(candidate.file_path).suffix.lower()
        if candidate_ext not in IMAGE_EXTENSIONS:
            raise ValueError(
                f"Unsupported image format from TMDB: {candidate_ext}. "
                f"Supported formats: {', '.join(sorted(IMAGE_EXTENSIONS))}"
            )

        # Use original filename stem with TMDB extension
        original_stem = dst_path.stem
        normalized_name = f"{original_stem}{candidate_ext}"

        final_dst = dst_path.parent / normalized_name

        # Embed marker and write atomically
        embed_marker_and_atomic_write(raw_bytes, final_dst, marker)

        # Remove old file if extension changed
        if final_dst != dst_path and dst_path.exists():
            dst_path.unlink()

    def close(self) -> None:
        """Close HTTP client."""
        self.http_client.close()
