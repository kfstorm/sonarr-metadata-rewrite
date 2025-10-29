"""Helper functions for integration tests."""

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from fast_langdetect import (  # type: ignore[import-untyped]
    DetectError,
    detect_multilingual,
)

from sonarr_metadata_rewrite.file_utils import find_target_files, is_nfo_file
from sonarr_metadata_rewrite.image_utils import read_embedded_marker
from sonarr_metadata_rewrite.models import ImageCandidate
from sonarr_metadata_rewrite.retry_utils import retry
from tests.integration.fixtures.series_manager import SeriesManager
from tests.integration.fixtures.sonarr_client import SonarrClient
from tests.integration.fixtures.subprocess_service_manager import (
    SubprocessServiceManager,
)

# Language detection confidence threshold
LANGUAGE_DETECTION_THRESHOLD = 0.7

# Some translations that are correct but not correctly detected
DETECTION_EXCEPTIONS_BY_LANGUAGE = {
    "fr": ["Godolkin University"],  # English: "God U."
}


def create_fake_episode_file(
    media_root: Path,
    series_slug: str,
    season: int,
    episode: int,
    title: str = "Episode",
) -> Path:
    """Create a fake episode video file to trigger Sonarr processing.

    Uses a pre-generated minimal valid MKV file to ensure Sonarr's FFprobe
    can successfully parse media information.

    Args:
        media_root: Root media directory
        series_slug: Series directory name (e.g., "breaking-bad")
        season: Season number
        episode: Episode number
        title: Episode title

    Returns:
        Path to created file
    """
    series_dir = media_root / series_slug
    season_dir = series_dir / f"Season {season:02d}"
    season_dir.mkdir(parents=True, exist_ok=True)

    # Convert series slug to title for proper Sonarr naming
    series_title = series_slug.replace("-", " ").title()
    filename = f"{series_title} - S{season:02d}E{episode:02d} - {title}.mkv"
    episode_file = season_dir / filename

    # Copy valid sample MKV file to avoid FFprobe "EBML header parsing failed" errors
    # Sample generated with: ffmpeg -f lavfi -i color=black:size=64x64:duration=1 \
    #   -f lavfi -i sine=frequency=1000:duration=1 -c:v libx264 -c:a aac \
    #   -preset ultrafast -y sample_episode.mkv
    sample_file = Path(__file__).parent / "fixtures" / "sample_episode.mkv"
    shutil.copy2(sample_file, episode_file)
    return episode_file


def wait_for_nfo_files(
    series_path: Path, expected_count: int, timeout: float = 5.0
) -> list[Path]:
    """Wait for .nfo files to be generated in series directory.

    Args:
        series_path: Path to series directory
        expected_count: Expected number of .nfo files
        timeout: Maximum time to wait in seconds

    Returns:
        List of .nfo files found

    Raises:
        AssertionError: If expected number of .nfo files not found within timeout
    """
    print(
        f"Waiting for {expected_count} .nfo files in {series_path} "
        f"(timeout: {timeout}s)"
    )

    @retry(timeout=timeout, interval=0.5, log_interval=1.0)
    def check_nfo_files() -> list[Path]:
        nfo_files = [
            p for p in find_target_files(series_path, recursive=True) if is_nfo_file(p)
        ]
        assert len(nfo_files) == expected_count, (
            f"Expected exactly {expected_count} .nfo files, but found "
            f"{len(nfo_files)} in {series_path}. Files found: {nfo_files}"
        )
        print(f"Found {len(nfo_files)} .nfo files: {nfo_files}")
        return sorted(nfo_files)

    return check_nfo_files()


def parse_nfo_content(nfo_path: Path) -> dict[str, Any]:
    """Parse .nfo file and extract key metadata.

    Args:
        nfo_path: Path to .nfo file

    Returns:
        Dictionary with parsed metadata
    """
    tree = ET.parse(nfo_path)
    root = tree.getroot()

    metadata: dict[str, Any] = {
        "root_tag": root.tag,
        "title": "",
        "plot": "",
        "tmdb_id": None,
        "tvdb_id": None,
    }

    # Extract title
    title_elem = root.find("title")
    if title_elem is not None and title_elem.text:
        metadata["title"] = title_elem.text.strip()

    # Extract plot/overview
    plot_elem = root.find("plot")
    if plot_elem is not None and plot_elem.text:
        metadata["plot"] = plot_elem.text.strip()

    # Extract IDs
    for uniqueid in root.findall(".//uniqueid"):
        id_type = uniqueid.get("type")
        id_value = uniqueid.text

        if id_type == "tmdb" and id_value:
            try:
                metadata["tmdb_id"] = int(id_value.strip())
            except ValueError:
                pass
        elif id_type == "tvdb" and id_value:
            try:
                metadata["tvdb_id"] = int(id_value.strip())
            except ValueError:
                pass

    return metadata


class SeriesWithNfos:
    """Context manager for setting up series with NFO files."""

    def __init__(
        self,
        configured_sonarr_container: SonarrClient,
        temp_media_root: Path,
        tvdb_id: int,
        expected_image_filenames: list[str],
        episodes: list[tuple[str, int, int]] | None = None,
    ):
        """Initialize the context manager.

        Args:
            configured_sonarr_container: Configured Sonarr client
            temp_media_root: Temporary media root directory
            tvdb_id: TVDB ID of the series to set up
            expected_image_filenames: List of expected image file names
            episodes: List of (title, season, episode) tuples, defaults to 2 episodes
        """
        self.sonarr = configured_sonarr_container
        self.media_root = temp_media_root
        self.tvdb_id = tvdb_id
        self.expected_image_filenames = expected_image_filenames
        self.episodes = episodes or [("Episode 1", 1, 1), ("Episode 2", 1, 2)]
        self.series: SeriesManager | None = None

    def __enter__(self) -> tuple[list[Path], list[Path]]:
        """Set up series and return series info.

        Returns:
            Tuple of (nfo_files, image_files)
        """
        self.series = SeriesManager(self.sonarr, self.tvdb_id, "/tv", self.media_root)
        self.series.__enter__()

        # Create fake episode files to trigger Sonarr processing
        episode_files = []
        for title, season, episode in self.episodes:
            episode_file = create_fake_episode_file(
                self.media_root, self.series.slug, season, episode, title
            )
            episode_files.append(episode_file)

        # Trigger disk scan to detect episode files
        series_path = self.media_root / self.series.slug
        scan_success = self.sonarr.trigger_disk_scan(self.series.id)
        if not scan_success:
            raise RuntimeError("Failed to trigger disk scan")

        # Wait for disk scan to complete and import files
        @retry(timeout=15.0, interval=1.0, log_interval=2.0)
        def check_disk_scan_complete() -> None:
            assert self.series is not None
            imported_files = self.sonarr.get_episode_files(self.series.id)
            assert len(imported_files) >= len(episode_files), (
                f"Disk scan still in progress: expected {len(episode_files)} "
                f"episode files, but only {len(imported_files)} imported so far"
            )

        check_disk_scan_complete()

        # NFO files are generated automatically during series/episode import

        # Wait for .nfo files to be generated
        expected_nfo_count = len(episode_files) + 1  # episodes + series
        series_path = self.media_root / self.series.slug
        nfo_files = wait_for_nfo_files(series_path, expected_nfo_count, timeout=30.0)

        return nfo_files, [series_path / f for f in self.expected_image_filenames]

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Clean up series."""
        if self.series:
            self.series.__exit__(exc_type, exc_val, exc_tb)


class ServiceRunner:
    """Context manager for running service with given configuration."""

    def __init__(
        self,
        temp_media_root: Path,
        service_config: dict[str, str],
        startup_pattern: str | None = None,
    ):
        # Base configuration
        env_overrides = {
            "REWRITE_ROOT_DIR": str(temp_media_root),
            "ENABLE_FILE_MONITOR": "true",
            "ENABLE_FILE_SCANNER": "true",
            "PREFERRED_LANGUAGES": "zh-CN",
        }

        # Apply service-specific configuration overrides
        env_overrides.update(service_config)

        self.service = SubprocessServiceManager(
            env_overrides=env_overrides, startup_pattern=startup_pattern
        )

    def __enter__(self) -> SubprocessServiceManager:
        self.service.start()
        return self.service

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.service.stop()


def verify_translations(
    nfo_files: list[Path],
    expected_language: str,
    possible_languages: list[str],
) -> None:
    """Wait for and verify translation results.

    Args:
        nfo_files: List of .nfo files to check
        expected_language: Expected language code (e.g., "zh", "fr", "en")
        possible_languages: List of possible language codes for post-filtering.
                           Must include "en" since Sonarr only generates English
                           metadata files initially, and English text remains if
                           translation fails.

    Raises:
        AssertionError: If files don't match expected state
        ValueError: If "en" is not included in possible_languages
    """
    # Remove duplicates
    possible_langs = set(possible_languages)

    # Validate that "en" is included in possible languages
    if "en" not in possible_languages:
        raise ValueError(
            "possible_languages must include 'en' since Sonarr generates English "
            "metadata files initially and English text remains if translation fails"
        )

    print(f"Waiting for {expected_language} translations in {len(nfo_files)} files...")

    @retry(timeout=15.0, interval=0.5, log_interval=2.0)
    def check_translation_state() -> None:
        for nfo_file in nfo_files:
            metadata = parse_nfo_content(nfo_file)
            title = metadata.get("title", "").strip()
            plot = metadata.get("plot", "").strip()

            # Ensure we have content to detect
            assert title, f"NFO file {nfo_file} has no title"
            assert plot, f"NFO file {nfo_file} has no plot"

            # Helper function to check if content has exceptions
            def has_exception(content: str) -> bool:
                if not DETECTION_EXCEPTIONS_BY_LANGUAGE.get(expected_language):
                    return False
                return any(
                    exception.lower() in content.lower()
                    for exception in DETECTION_EXCEPTIONS_BY_LANGUAGE[expected_language]
                )

            # Helper function to detect and validate language
            def check_language(
                content: str,
            ) -> tuple[bool, list[dict[str, str]] | None]:
                if has_exception(content):
                    return True, None  # Skip detection, treat as matching

                detected_langs = detect_multilingual(content)

                # Post-filter to only include possible languages
                detected_langs = [
                    lang for lang in detected_langs if lang["lang"] in possible_langs
                ]

                # Check if expected language meets threshold
                threshold_match = any(
                    lang["lang"] == expected_language
                    and lang["score"] > LANGUAGE_DETECTION_THRESHOLD
                    for lang in detected_langs
                )

                # If threshold not met, check if expected language has highest score
                if not threshold_match and detected_langs:
                    highest_score_lang = max(detected_langs, key=lambda x: x["score"])
                    highest_score_match = (
                        highest_score_lang["lang"] == expected_language
                    )
                    return highest_score_match, detected_langs

                return threshold_match, detected_langs

            # Detect language in title and plot
            try:
                title_matches, title_langs = check_language(title)
                plot_matches, plot_langs = check_language(plot)

                # Both title and plot must match
                if not (title_matches and plot_matches):
                    # Show detection results (only for fields that were detected)
                    error_parts = [
                        f"Language mismatch in {nfo_file.name}. "
                        f"Expected {expected_language}"
                    ]

                    if not title_matches and title_langs is not None:
                        error_parts.append(f"title_langs={title_langs}")
                    if not plot_matches and plot_langs is not None:
                        error_parts.append(f"plot_langs={plot_langs}")

                    error_parts.extend([f"Title: '{title}'", f"Plot: '{plot}'"])

                    raise AssertionError(". ".join(error_parts))

            except DetectError as e:
                raise AssertionError(
                    f"Language detection failed for {nfo_file}: {e}. "
                    f"Title: '{title}', Plot: '{plot}'"
                ) from e

    check_translation_state()
    print(
        f"✅ All {len(nfo_files)} files verified to contain "
        f"{expected_language} translations"
    )


def verify_images(
    image_paths: list[Path],
    expected_language: str | None,
) -> None:
    """Verify images have been processed.

    Args:
        image_paths: List of image file paths to verify
        expected_language: Expected language/country code (e.g., "zh-CN"),
                          or None to verify original images without markers

    Raises:
        AssertionError: If images don't match expected state
    """

    def get_marker_language(marker: ImageCandidate | None) -> str:
        """Extract language code from marker (e.g., 'zh-CN')."""
        if not marker:
            return ""
        iso_639_1 = marker.iso_639_1 or ""
        iso_3166_1 = marker.iso_3166_1 or ""
        language_parts = [p for p in [iso_639_1, iso_3166_1] if p]
        return "-".join(language_parts) if language_parts else ""

    if expected_language is None:
        print(f"Verifying {len(image_paths)} images are original (no markers)")
    else:
        print(
            f"Verifying {len(image_paths)} images with expected language: "
            f"{expected_language}"
        )

    @retry(timeout=15.0, interval=0.5, log_interval=2.0)
    def check_images_processed() -> None:
        for image_path in image_paths:
            # Check image exists
            assert image_path.exists(), f"Image file not found: {image_path}"

            marker = read_embedded_marker(image_path)

            if expected_language is None:
                # Verify no marker exists (original image)
                assert marker is None, (
                    f"Unexpected marker found in {image_path.name}. "
                    f"Expected original image without marker."
                )
            else:
                # Verify marker exists with expected language
                assert marker is not None, (
                    f"No embedded marker found in {image_path.name}. "
                    f"Expected marker with language info."
                )

                marker_lang = get_marker_language(marker)
                assert marker_lang == expected_language, (
                    f"Language mismatch in {image_path.name}. "
                    f"Expected '{expected_language}', got '{marker_lang}'"
                )

    check_images_processed()

    # Print success messages after all checks pass
    for image_path in image_paths:
        marker = read_embedded_marker(image_path)
        if marker:
            marker_lang = get_marker_language(marker)
            print(f"✅ {image_path.name}: marker verified with language {marker_lang}")
        else:
            print(f"✅ {image_path.name}: verified original image (no marker)")

    print(f"✅ All {len(image_paths)} images verified")
