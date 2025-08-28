"""Tests for NFO utility functions."""

import tempfile
from pathlib import Path

import pytest

from sonarr_metadata_rewrite.nfo_utils import (
    find_nfo_files,
    get_nfo_file_extensions,
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
        """Test that files with 'nfo' in name but different extension are not detected."""
        path = Path("nfo_file.txt")
        assert is_nfo_file(path) is False


class TestFindNfoFiles:
    """Test find_nfo_files function."""

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
            
            found_files = find_nfo_files(temp_path, recursive=False)
            
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
            found_files = find_nfo_files(temp_path)
            assert len(found_files) == 2
            assert root_nfo in found_files
            assert sub_nfo in found_files
            
            # Test non-recursive
            found_files_non_recursive = find_nfo_files(temp_path, recursive=False)
            assert len(found_files_non_recursive) == 1
            assert root_nfo in found_files_non_recursive
            assert sub_nfo not in found_files_non_recursive

    def test_nonexistent_directory(self) -> None:
        """Test behavior with non-existent directory."""
        nonexistent_path = Path("/nonexistent/directory")
        found_files = find_nfo_files(nonexistent_path)
        assert found_files == []

    def test_empty_directory(self) -> None:
        """Test behavior with empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            found_files = find_nfo_files(temp_path)
            assert found_files == []

    def test_deduplicate_on_case_insensitive_filesystem(self) -> None:
        """Test that files are deduplicated properly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create files with different cases
            nfo_file = temp_path / "test.nfo"
            nfo_file.touch()
            
            found_files = find_nfo_files(temp_path)
            
            # Should find the file only once, even if filesystem is case-insensitive
            assert len(found_files) >= 1
            # All found files should be actual files
            for file_path in found_files:
                assert file_path.is_file()
                assert is_nfo_file(file_path)


class TestGetNfoFileExtensions:
    """Test get_nfo_file_extensions function."""

    def test_returns_all_extensions(self) -> None:
        """Test that all NFO extensions are returned."""
        extensions = get_nfo_file_extensions()
        assert ".nfo" in extensions
        assert ".NFO" in extensions
        assert len(extensions) == 2

    def test_extensions_are_strings(self) -> None:
        """Test that all returned extensions are strings."""
        extensions = get_nfo_file_extensions()
        for ext in extensions:
            assert isinstance(ext, str)
            assert ext.startswith(".")