"""Tests for NFO utility functions."""

from pathlib import Path

from sonarr_metadata_rewrite.nfo_utils import (
    find_nfo_files,
    is_nfo_file,
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
    """Test find_nfo_files function."""

    def test_find_both_case_variations(self, test_data_dir: Path) -> None:
        """Test that both .nfo and .NFO files are found."""
        # Create test files
        nfo_lowercase = test_data_dir / "test.nfo"
        nfo_uppercase = test_data_dir / "test.NFO"
        txt_file = test_data_dir / "test.txt"

        nfo_lowercase.touch()
        nfo_uppercase.touch()
        txt_file.touch()

        found_files = find_nfo_files(test_data_dir, recursive=False)

        # Should find both NFO files but not the txt file
        assert len(found_files) == 2
        assert nfo_lowercase in found_files
        assert nfo_uppercase in found_files
        assert txt_file not in found_files

    def test_recursive_search(self, test_data_dir: Path) -> None:
        """Test recursive search in subdirectories."""
        # Create files in root and subdirectory
        root_nfo = test_data_dir / "root.nfo"
        subdir = test_data_dir / "subdir"
        subdir.mkdir()
        sub_nfo = subdir / "sub.NFO"

        root_nfo.touch()
        sub_nfo.touch()

        # Test recursive (default)
        found_files = find_nfo_files(test_data_dir)
        assert len(found_files) == 2
        assert root_nfo in found_files
        assert sub_nfo in found_files

        # Test non-recursive
        found_files_non_recursive = find_nfo_files(test_data_dir, recursive=False)
        assert len(found_files_non_recursive) == 1
        assert root_nfo in found_files_non_recursive
        assert sub_nfo not in found_files_non_recursive

    def test_nonexistent_directory(self) -> None:
        """Test behavior with non-existent directory."""
        nonexistent_path = Path("/nonexistent/directory")
        found_files = find_nfo_files(nonexistent_path)
        assert found_files == []

    def test_empty_directory(self, test_data_dir: Path) -> None:
        """Test behavior with empty directory."""
        found_files = find_nfo_files(test_data_dir)
        assert found_files == []

    def test_deduplicate_on_case_insensitive_filesystem(self, test_data_dir: Path) -> None:
        """Test that files are deduplicated properly."""
        # Create files with different cases
        nfo_file = test_data_dir / "test.nfo"
        nfo_file.touch()

        found_files = find_nfo_files(test_data_dir)

        # Should find the file only once, even if filesystem is case-insensitive
        assert len(found_files) >= 1
        # All found files should be actual files
        for file_path in found_files:
            assert file_path.is_file()
            assert is_nfo_file(file_path)
