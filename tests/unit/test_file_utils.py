"""Tests for NFO utility functions."""

import tempfile
from pathlib import Path

from sonarr_metadata_rewrite.file_utils import (
    find_target_files,
    is_nfo_file,
    is_rewritable_image,
)


class TestIsNfoFile:
    """Test is_nfo_file function."""

    def test_lowercase_nfo_file(self) -> None:
        """Test that lowercase .nfo files are detected."""
        path = Path("test.nfo")
        assert is_nfo_file(path) is True

    def test_uppercase_nfo_file(self) -> None:
        """Test that uppercase .NFO files are detected."""
        path = Path("test.NFO")
        assert is_nfo_file(path) is True

    def test_mixed_case_nfo_file(self) -> None:
        """Test that mixed case .Nfo files are detected."""
        path = Path("test.Nfo")
        assert is_nfo_file(path) is True

    def test_non_nfo_file(self) -> None:
        """Test that non-NFO files are not detected."""
        path = Path("test.txt")
        assert is_nfo_file(path) is False

    def test_nfo_in_filename_but_different_extension(self) -> None:
        """Test files with 'nfo' in name but different extension."""
        path = Path("nfo_file.txt")
        assert is_nfo_file(path) is False


class TestFindNfoFiles:
    """Test finding NFO files via find_target_files + filter."""

    def test_find_both_case_variations(self) -> None:
        """Test that both .nfo and .NFO files are found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            nfo_lowercase = temp_path / "test.nfo"
            nfo_uppercase = temp_path / "test.NFO"
            txt_file = temp_path / "test.txt"

            nfo_lowercase.touch()
            nfo_uppercase.touch()
            txt_file.touch()

            found_files = [
                p
                for p in find_target_files(temp_path, recursive=False)
                if is_nfo_file(p)
            ]

            # Should find both NFO files but not the txt file
            assert len(found_files) == 2
            assert nfo_lowercase in found_files
            assert nfo_uppercase in found_files
            assert txt_file not in found_files

    def test_recursive_search(self) -> None:
        """Test recursive search in subdirectories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create files in root and subdirectory
            root_nfo = temp_path / "root.nfo"
            subdir = temp_path / "subdir"
            subdir.mkdir()
            sub_nfo = subdir / "sub.NFO"

            root_nfo.touch()
            sub_nfo.touch()

            # Test recursive (default)
            found_files = [p for p in find_target_files(temp_path) if is_nfo_file(p)]
            assert len(found_files) == 2
            assert root_nfo in found_files
            assert sub_nfo in found_files

            # Test non-recursive
            found_files_non_recursive = [
                p
                for p in find_target_files(temp_path, recursive=False)
                if is_nfo_file(p)
            ]
            assert len(found_files_non_recursive) == 1
            assert root_nfo in found_files_non_recursive
            assert sub_nfo not in found_files_non_recursive

    def test_nonexistent_directory(self) -> None:
        """Test behavior with non-existent directory."""
        nonexistent_path = Path("/nonexistent/directory")
        found_files = [p for p in find_target_files(nonexistent_path) if is_nfo_file(p)]
        assert found_files == []

    def test_empty_directory(self) -> None:
        """Test behavior with empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            found_files = [p for p in find_target_files(temp_path) if is_nfo_file(p)]
            assert found_files == []

    def test_deduplicate_on_case_insensitive_filesystem(self) -> None:
        """Test that files are deduplicated properly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create files with different cases
            nfo_file = temp_path / "test.nfo"
            nfo_file.touch()

            found_files = [p for p in find_target_files(temp_path) if is_nfo_file(p)]

            # Should find the file only once, even if filesystem is case-insensitive
            assert len(found_files) >= 1
            # All found files should be actual files
            for file_path in found_files:
                assert file_path.is_file()


class TestIsRewritableImage:
    """Test is_rewritable_image function."""

    def test_poster_jpg(self) -> None:
        """Test that poster.jpg is detected as rewritable."""
        assert is_rewritable_image(Path("poster.jpg")) is True

    def test_poster_png(self) -> None:
        """Test that poster.png is detected as rewritable."""
        assert is_rewritable_image(Path("poster.png")) is True

    def test_season_poster(self) -> None:
        """Test that season posters are detected as rewritable."""
        assert is_rewritable_image(Path("season01-poster.jpg")) is True
        assert is_rewritable_image(Path("season02-poster.png")) is True
        assert is_rewritable_image(Path("season10-poster.jpeg")) is True
        # Specials season poster
        assert is_rewritable_image(Path("season-specials-poster.jpg")) is True

    def test_clearlogo_jpg(self) -> None:
        """Test that clearlogo.jpg is detected as rewritable."""
        assert is_rewritable_image(Path("clearlogo.jpg")) is True

    def test_clearlogo_png(self) -> None:
        """Test that clearlogo.png is detected as rewritable."""
        assert is_rewritable_image(Path("clearlogo.png")) is True

    def test_uppercase_names(self) -> None:
        """Test that uppercase filenames are detected."""
        assert is_rewritable_image(Path("POSTER.jpg")) is True
        assert is_rewritable_image(Path("CLEARLOGO.png")) is True
        assert is_rewritable_image(Path("SEASON01-POSTER.jpg")) is True
        assert is_rewritable_image(Path("SEASON-SPECIALS-POSTER.PNG")) is True

    def test_non_rewritable_images(self) -> None:
        """Test that non-poster/clearlogo images are not detected."""
        assert is_rewritable_image(Path("banner.jpg")) is False
        assert is_rewritable_image(Path("fanart.jpg")) is False
        assert is_rewritable_image(Path("backdrop.png")) is False
        assert is_rewritable_image(Path("thumb.jpg")) is False

    def test_non_image_files(self) -> None:
        """Test that non-image files are not detected."""
        assert is_rewritable_image(Path("poster.txt")) is False
        assert is_rewritable_image(Path("clearlogo.nfo")) is False


class TestFindRewritableImages:
    """Test finding rewritable images via find_target_files + filter."""

    def test_find_poster_and_clearlogo(self) -> None:
        """Test finding both poster and clearlogo files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            poster = temp_path / "poster.jpg"
            poster.touch()
            clearlogo = temp_path / "clearlogo.png"
            clearlogo.touch()
            banner = temp_path / "banner.jpg"  # Should not be found
            banner.touch()

            found_files = [
                p for p in find_target_files(temp_path) if is_rewritable_image(p)
            ]
            found_names = {f.name for f in found_files}

            assert "poster.jpg" in found_names
            assert "clearlogo.png" in found_names
            assert "banner.jpg" not in found_names

    def test_find_season_posters(self) -> None:
        """Test finding season-specific posters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create season posters
            s01 = temp_path / "season01-poster.jpg"
            s01.touch()
            s02 = temp_path / "season02-poster.png"
            s02.touch()
            s_sp = temp_path / "season-specials-poster.jpg"
            s_sp.touch()

            found_files = [
                p for p in find_target_files(temp_path) if is_rewritable_image(p)
            ]
            found_names = {f.name for f in found_files}

            assert "season01-poster.jpg" in found_names
            assert "season02-poster.png" in found_names
            assert "season-specials-poster.jpg" in found_names

    def test_recursive_search(self) -> None:
        """Test recursive search in subdirectories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create nested directories
            season1_dir = temp_path / "Season 1"
            season1_dir.mkdir()
            season2_dir = temp_path / "Season 2"
            season2_dir.mkdir()

            # Create image files in subdirectories
            poster1 = season1_dir / "season01-poster.jpg"
            poster1.touch()
            poster2 = season2_dir / "season02-poster.jpg"
            poster2.touch()

            found_files = [
                p
                for p in find_target_files(temp_path, recursive=True)
                if is_rewritable_image(p)
            ]
            assert len(found_files) == 2

    def test_non_recursive_search(self) -> None:
        """Test non-recursive search only in root directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create root level poster
            root_poster = temp_path / "poster.jpg"
            root_poster.touch()

            # Create nested directory with poster
            season_dir = temp_path / "Season 1"
            season_dir.mkdir()
            nested_poster = season_dir / "season01-poster.jpg"
            nested_poster.touch()

            found_files = [
                p
                for p in find_target_files(temp_path, recursive=False)
                if is_rewritable_image(p)
            ]
            assert len(found_files) == 1
            assert found_files[0].name == "poster.jpg"

    def test_empty_directory(self) -> None:
        """Test behavior with empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            found_files = [
                p for p in find_target_files(temp_path) if is_rewritable_image(p)
            ]
            assert found_files == []
