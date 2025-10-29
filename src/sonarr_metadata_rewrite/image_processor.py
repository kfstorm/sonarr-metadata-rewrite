"""Image processor for rewriting poster and clearlogo images."""

import logging
from pathlib import Path

import httpx

from sonarr_metadata_rewrite.backup_utils import (
    create_backup,
    get_backup_path,
    restore_from_backup,
)
from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.file_utils import (
    IMAGE_EXTENSIONS,
    extract_metadata_info,
    parse_image_info,
)
from sonarr_metadata_rewrite.image_utils import (
    embed_marker_and_atomic_write,
    read_embedded_marker,
)
from sonarr_metadata_rewrite.models import ImageCandidate, ImageProcessResult, TmdbIds
from sonarr_metadata_rewrite.retry_utils import retry
from sonarr_metadata_rewrite.translator import Translator

logger = logging.getLogger(__name__)

# TMDB image base URL
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"


class ImageProcessor:
    """Processor for poster and clearlogo image files."""

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
            kind, season_num = parse_image_info(basename)

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
                # No preferred language available - try to revert to original backup
                backup_path = get_backup_path(
                    image_path,
                    self.settings.original_files_backup_dir,
                    self.settings.rewrite_root_dir,
                )
                if backup_path and image_path.exists():
                    # Check if current image is different from backup
                    current_marker = read_embedded_marker(image_path)
                    backup_marker = read_embedded_marker(backup_path)

                    # If current has a marker but backup doesn't, or they differ
                    # it means current is rewritten and should be reverted
                    if current_marker and not backup_marker:
                        # Revert to original backup
                        restore_from_backup(
                            image_path,
                            self.settings.original_files_backup_dir,
                            self.settings.rewrite_root_dir,
                        )
                        preferred_langs = ", ".join(self.settings.preferred_languages)
                        return ImageProcessResult(
                            success=True,
                            file_path=image_path,
                            message=(
                                f"Reverted {kind} to original - no image available "
                                f"in preferred languages [{preferred_langs}]"
                            ),
                            kind=kind,
                            file_modified=True,
                        )
                    elif not current_marker:
                        # Already showing original
                        preferred_langs = ", ".join(self.settings.preferred_languages)
                        return ImageProcessResult(
                            success=False,
                            file_path=image_path,
                            message=(
                                f"File unchanged - already original and no {kind} "
                                f"available in preferred languages [{preferred_langs}]"
                            ),
                            kind=kind,
                        )

                # No backup or can't revert
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
                if current_marker and current_marker.file_path == candidate.file_path:
                    lang_str = f"{candidate.iso_639_1}-{candidate.iso_3166_1}"
                    return ImageProcessResult(
                        success=True,
                        file_path=image_path,
                        message=(
                            f"{kind.capitalize()} already matches"
                            f" selected candidate ({lang_str})"
                        ),
                        kind=kind,
                        selected_language=lang_str,
                        selected_file_path=candidate.file_path,
                    )

            # Create backup if file exists
            backup_created = create_backup(
                image_path,
                self.settings.original_files_backup_dir,
                self.settings.rewrite_root_dir,
            )

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

        @retry(timeout=5.0, interval=1.0, exceptions=(FileNotFoundError,))
        def _find_and_extract_tmdb_id() -> TmdbIds:
            """
            Find and extract TMDB ID from tvshow.nfo file.
            This function locates the tvshow.nfo file that is always
            placed next to the image file
            (as per Kodi's NFO file structure: https://kodi.wiki/view/NFO_files/TV_shows),
            extracts the TMDB ID from it, and returns a TmdbIds object
            containing the series ID and season number.

            Returns:
                TmdbIds: An object containing the TMDB series ID and season number.

            Raises:
                FileNotFoundError: If tvshow.nfo is not found next to the image file.
                ValueError: If TMDB ID could not be extracted from the tvshow.nfo file.
            """
            # tvshow.nfo is always next to the image file
            nfo_path = image_path.parent / "tvshow.nfo"
            if not nfo_path.exists():
                raise FileNotFoundError(
                    f"Could not find tvshow.nfo for image: {image_path}"
                )

            metadata_info = extract_metadata_info(nfo_path)
            if not metadata_info.tmdb_id:
                raise ValueError(f"Could not extract TMDB ID from {nfo_path}")

            return TmdbIds(series_id=metadata_info.tmdb_id, season=season_num)

        try:
            return _find_and_extract_tmdb_id()
        except FileNotFoundError:
            return None

    def _download_and_write_image(
        self, dst_path: Path, candidate: ImageCandidate
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
        marker = candidate

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
