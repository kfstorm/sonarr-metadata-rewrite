"""Integration tests for multiple metadata formats."""

import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Generator
from pathlib import Path

import pytest

from tests.integration.test_helpers import (
    parse_nfo_content,
    run_service_with_config,
)


@pytest.fixture
def temp_format_test_dir() -> Generator[Path, None, None]:
    """Create temporary directory for format testing."""
    with tempfile.TemporaryDirectory(prefix="format_test_") as temp_dir:
        yield Path(temp_dir)


def create_test_nfo_file(
    path: Path, format_type: str, content_type: str = "series"
) -> Path:
    """Create test .nfo file in specified format.

    Args:
        path: Directory to create file in
        format_type: 'kodi' or 'emby'
        content_type: 'series' or 'episode'

    Returns:
        Path to created file
    """
    path.mkdir(parents=True, exist_ok=True)

    if content_type == "series":
        file_path = path / "tvshow.nfo"
        if format_type == "kodi":
            content = """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Test Series (English)</title>
  <plot>This is a test series description in English.</plot>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <uniqueid type="tvdb">81189</uniqueid>
  <genre>Drama</genre>
  <year>2008</year>
</tvshow>"""
        else:  # emby
            content = """<?xml version="1.0" encoding="utf-8"?>
<series>
  <title>Test Series (English)</title>
  <overview>This is a test series description in English.</overview>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <uniqueid type="tvdb">81189</uniqueid>
  <genre>Drama</genre>
  <year>2008</year>
</series>"""
    else:  # episode
        file_path = path / "S01E01 - Test Episode.nfo"
        if format_type == "kodi":
            content = """<?xml version="1.0" encoding="utf-8"?>
<episodedetails>
  <title>Test Episode (English)</title>
  <plot>This is a test episode description in English.</plot>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <season>1</season>
  <episode>1</episode>
  <aired>2008-01-20</aired>
</episodedetails>"""
        else:  # emby
            content = """<?xml version="1.0" encoding="utf-8"?>
<episode>
  <title>Test Episode (English)</title>
  <overview>This is a test episode description in English.</overview>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <season>1</season>
  <episode>1</episode>
  <aired>2008-01-20</aired>
</episode>"""

    file_path.write_text(content, encoding="utf-8")
    return file_path


def create_mixed_format_nfo(path: Path) -> Path:
    """Create mixed format .nfo file (Kodi root with Emby elements).

    Args:
        path: Directory to create file in

    Returns:
        Path to created file
    """
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / "tvshow.nfo"

    content = """<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Mixed Format Series (English)</title>
  <overview>This uses overview instead of plot, but with Kodi tvshow root.</overview>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <uniqueid type="tvdb">81189</uniqueid>
  <genre>Drama</genre>
  <year>2008</year>
</tvshow>"""

    file_path.write_text(content, encoding="utf-8")
    return file_path


@pytest.mark.integration
@pytest.mark.slow
def test_kodi_format_support(temp_format_test_dir: Path) -> None:
    """Test support for Kodi format files."""
    # Create Kodi format files
    series_dir = temp_format_test_dir / "kodi-series"
    series_file = create_test_nfo_file(series_dir, "kodi", "series")
    episode_file = create_test_nfo_file(series_dir, "kodi", "episode")

    nfo_files = [series_file, episode_file]

    # Test with translation service
    service_config = {
        "ENABLE_FILE_MONITOR": "true",
        "ENABLE_FILE_SCANNER": "false",
        "PREFERRED_LANGUAGES": "zh-CN",
    }

    with run_service_with_config(temp_format_test_dir, service_config) as service:
        assert service.is_running(), "Service should be running"

        # Touch files to trigger processing
        for nfo_file in nfo_files:
            nfo_file.touch()

        # Wait for processing
        import time

        time.sleep(5)

        # Verify files were processed and structure preserved
        for nfo_file in nfo_files:
            metadata = parse_nfo_content(nfo_file)

            # Check root tag is preserved
            if "tvshow" in nfo_file.name or nfo_file.name == "tvshow.nfo":
                assert metadata["root_tag"] == "tvshow"
            else:
                assert metadata["root_tag"] == "episodedetails"

            # Check TMDB ID is preserved
            assert metadata["tmdb_id"] == 1396

            # Check content exists (may be translated or original)
            assert metadata["title"], f"Title should exist in {nfo_file.name}"
            assert metadata["plot"], f"Plot should exist in {nfo_file.name}"


@pytest.mark.integration
@pytest.mark.slow
def test_emby_format_support(temp_format_test_dir: Path) -> None:
    """Test support for Emby format files."""
    # Create Emby format files
    series_dir = temp_format_test_dir / "emby-series"
    series_file = create_test_nfo_file(series_dir, "emby", "series")
    episode_file = create_test_nfo_file(series_dir, "emby", "episode")

    nfo_files = [series_file, episode_file]

    # Test with translation service
    service_config = {
        "ENABLE_FILE_MONITOR": "true",
        "ENABLE_FILE_SCANNER": "false",
        "PREFERRED_LANGUAGES": "zh-CN",
    }

    with run_service_with_config(temp_format_test_dir, service_config) as service:
        assert service.is_running(), "Service should be running"

        # Touch files to trigger processing
        for nfo_file in nfo_files:
            nfo_file.touch()

        # Wait for processing
        import time

        time.sleep(5)

        # Verify files were processed and structure preserved
        for nfo_file in nfo_files:
            metadata = parse_nfo_content(nfo_file)

            # Check root tag is preserved
            if "tvshow" in nfo_file.name or nfo_file.name == "tvshow.nfo":
                assert metadata["root_tag"] == "series"
            else:
                assert metadata["root_tag"] == "episode"

            # Check TMDB ID is preserved
            assert metadata["tmdb_id"] == 1396

            # Check content exists (may be translated or original)
            assert metadata["title"], f"Title should exist in {nfo_file.name}"

            # For Emby format, check that overview/plot exists
            tree = ET.parse(nfo_file)
            root = tree.getroot()
            overview_elem = root.find("overview")
            plot_elem = root.find("plot")

            assert (
                overview_elem is not None or plot_elem is not None
            ), f"Either overview or plot should exist in {nfo_file.name}"


@pytest.mark.integration
@pytest.mark.slow
def test_mixed_format_support(temp_format_test_dir: Path) -> None:
    """Test support for mixed format files."""
    # Create mixed format file
    series_dir = temp_format_test_dir / "mixed-series"
    mixed_file = create_mixed_format_nfo(series_dir)

    # Test with translation service
    service_config = {
        "ENABLE_FILE_MONITOR": "true",
        "ENABLE_FILE_SCANNER": "false",
        "PREFERRED_LANGUAGES": "zh-CN",
    }

    with run_service_with_config(temp_format_test_dir, service_config) as service:
        assert service.is_running(), "Service should be running"

        # Touch file to trigger processing
        mixed_file.touch()

        # Wait for processing
        import time

        time.sleep(5)

        # Verify file was processed and structure preserved
        metadata = parse_nfo_content(mixed_file)

        # Check root tag is preserved (Kodi style)
        assert metadata["root_tag"] == "tvshow"

        # Check TMDB ID is preserved
        assert metadata["tmdb_id"] == 1396

        # Check content exists
        assert metadata["title"], "Title should exist"

        # For mixed format, check that overview exists (not plot)
        tree = ET.parse(mixed_file)
        root = tree.getroot()
        overview_elem = root.find("overview")

        assert overview_elem is not None, "Overview should exist in mixed format"


@pytest.mark.integration
@pytest.mark.slow
def test_simultaneous_format_support(temp_format_test_dir: Path) -> None:
    """Test that all formats are supported simultaneously."""
    # Create files in all supported formats
    series_dirs = {}
    all_nfo_files = []

    # Create Kodi format
    series_dirs["kodi"] = temp_format_test_dir / "kodi-series"
    kodi_series = create_test_nfo_file(series_dirs["kodi"], "kodi", "series")
    kodi_episode = create_test_nfo_file(series_dirs["kodi"], "kodi", "episode")
    all_nfo_files.extend([kodi_series, kodi_episode])

    # Create Emby format
    series_dirs["emby"] = temp_format_test_dir / "emby-series"
    emby_series = create_test_nfo_file(series_dirs["emby"], "emby", "series")
    emby_episode = create_test_nfo_file(series_dirs["emby"], "emby", "episode")
    all_nfo_files.extend([emby_series, emby_episode])

    # Create mixed format
    series_dirs["mixed"] = temp_format_test_dir / "mixed-series"
    mixed_series = create_mixed_format_nfo(series_dirs["mixed"])
    all_nfo_files.append(mixed_series)

    # Test with translation service
    service_config = {
        "ENABLE_FILE_MONITOR": "true",
        "ENABLE_FILE_SCANNER": "false",
        "PREFERRED_LANGUAGES": "zh-CN",
    }

    with run_service_with_config(temp_format_test_dir, service_config) as service:
        assert service.is_running(), "Service should be running"

        # Touch all files to trigger processing
        for nfo_file in all_nfo_files:
            nfo_file.touch()

        # Wait for processing
        import time

        time.sleep(8)

        # Verify all files were processed correctly
        processed_count = 0

        for nfo_file in all_nfo_files:
            try:
                metadata = parse_nfo_content(nfo_file)

                # Basic checks
                assert (
                    metadata["tmdb_id"] == 1396
                ), f"TMDB ID not preserved in {nfo_file.name}"
                assert metadata["title"], f"Title missing in {nfo_file.name}"

                # Check structure preservation based on file type
                if "kodi" in str(nfo_file.parent):
                    if nfo_file.name == "tvshow.nfo":
                        assert metadata["root_tag"] == "tvshow"
                    else:
                        assert metadata["root_tag"] == "episodedetails"
                elif "emby" in str(nfo_file.parent):
                    if nfo_file.name == "tvshow.nfo":
                        assert metadata["root_tag"] == "series"
                    else:
                        assert metadata["root_tag"] == "episode"
                elif "mixed" in str(nfo_file.parent):
                    assert metadata["root_tag"] == "tvshow"

                processed_count += 1
                print(
                    f"✅ Successfully processed {nfo_file.name} "
                    f"(format: {metadata['root_tag']})"
                )

            except Exception as e:
                print(f"❌ Failed to process {nfo_file.name}: {e}")

        assert processed_count == len(
            all_nfo_files
        ), f"Expected {len(all_nfo_files)} files processed, got {processed_count}"

        print(
            f"Successfully processed all {processed_count} files with different formats"
        )


@pytest.mark.integration
def test_format_detection_without_service() -> None:
    """Test format detection logic without running the full service."""
    from sonarr_metadata_rewrite.metadata_formats import detect_metadata_format

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Test Kodi format detection
        kodi_file = create_test_nfo_file(temp_path / "kodi", "kodi", "series")
        kodi_format = detect_metadata_format(kodi_file)
        assert kodi_format is not None, "Should detect Kodi format"
        assert kodi_format.__class__.__name__ == "KodiMetadataFormat"

        # Test Emby format detection
        emby_file = create_test_nfo_file(temp_path / "emby", "emby", "series")
        emby_format = detect_metadata_format(emby_file)
        assert emby_format is not None, "Should detect Emby format"
        assert emby_format.__class__.__name__ == "EmbyMetadataFormat"

        # Test mixed format detection (should use Emby handler due to overview)
        mixed_file = create_mixed_format_nfo(temp_path / "mixed")
        mixed_format = detect_metadata_format(mixed_file)
        assert mixed_format is not None, "Should detect mixed format"
        # Mixed format (Kodi root + overview) should be handled by EmbyMetadataFormat
        # since it supports both overview and plot elements
        assert mixed_format.__class__.__name__ == "EmbyMetadataFormat"
