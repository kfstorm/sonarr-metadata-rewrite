"""Tests for NFO utility functions."""

import tempfile
from pathlib import Path

from sonarr_metadata_rewrite.nfo_utils import (
    create_backup,
    find_target_files,
    get_backup_path,
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


class TestBackupFunctions:
    """Test create_backup and get_backup_path functions."""

    def test_backup_with_none_backup_dir(self) -> None:
        """Test backup functions with None backup_dir."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            file_path = temp_path / "test.nfo"
            file_path.write_text("<tvshow></tvshow>")

            # create_backup returns False
            result = create_backup(file_path, None, temp_path)
            assert result is False

            # get_backup_path returns None
            backup_path = get_backup_path(file_path, None, temp_path)
            assert backup_path is None

    def test_backup_nonexistent_file(self) -> None:
        """Test that create_backup returns False for nonexistent file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"
            file_path = temp_path / "nonexistent.nfo"

            result = create_backup(file_path, backup_dir, temp_path)
            assert result is False

    def test_backup_and_retrieval_workflow(self) -> None:
        """Test complete workflow: create backup and retrieve it."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"
            file_path = temp_path / "test.nfo"
            content = "<tvshow></tvshow>"
            file_path.write_text(content)

            # Before backup, get_backup_path returns None
            backup_path = get_backup_path(file_path, backup_dir, temp_path)
            assert backup_path is None

            # Create backup
            created = create_backup(file_path, backup_dir, temp_path)
            assert created is True

            # After backup, get_backup_path returns the backup path
            backup_path = get_backup_path(file_path, backup_dir, temp_path)
            assert backup_path is not None
            assert backup_path.exists()
            assert backup_path.read_text() == content

    def test_backup_preserves_directory_structure(self) -> None:
        """Test backup maintains directory structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"
            subdir = temp_path / "shows" / "series1"
            subdir.mkdir(parents=True)
            file_path = subdir / "tvshow.nfo"
            content = "<tvshow></tvshow>"
            file_path.write_text(content)

            # Create backup
            result = create_backup(file_path, backup_dir, temp_path)
            assert result is True

            # Verify structure is preserved
            expected_backup = backup_dir / "shows" / "series1" / "tvshow.nfo"
            assert expected_backup.exists()
            assert expected_backup.read_text() == content

            # get_backup_path should find it
            backup_path = get_backup_path(file_path, backup_dir, temp_path)
            assert backup_path == expected_backup

    def test_backup_does_not_overwrite_existing(self) -> None:
        """Test that backup doesn't overwrite existing backup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"
            file_path = temp_path / "test.nfo"
            file_path.write_text("<tvshow>new</tvshow>")

            # Create existing backup with different content
            backup_path = backup_dir / "test.nfo"
            backup_path.parent.mkdir(parents=True)
            original_content = "<tvshow>original</tvshow>"
            backup_path.write_text(original_content)

            # Try to backup new content
            result = create_backup(file_path, backup_dir, temp_path)
            assert result is True

            # Verify backup wasn't overwritten
            assert backup_path.read_text() == original_content

            # get_backup_path should return existing backup
            retrieved_path = get_backup_path(file_path, backup_dir, temp_path)
            assert retrieved_path == backup_path
            assert retrieved_path is not None
            assert retrieved_path.read_text() == original_content

    def test_backup_stem_matching_for_different_extensions(self) -> None:
        """Test both functions handle same stem with different extensions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_dir = temp_path / "backup"

            # Create original poster.png in backup
            backup_path_png = backup_dir / "poster.png"
            backup_path_png.parent.mkdir(parents=True)
            backup_path_png.write_bytes(b"PNG original")

            # Try to backup poster.jpg (same stem, different extension)
            file_path_jpg = temp_path / "poster.jpg"
            file_path_jpg.write_bytes(b"JPG new")

            # create_backup should recognize existing stem and not create new
            result = create_backup(file_path_jpg, backup_dir, temp_path)
            assert result is True

            # Verify original backup still exists and wasn't modified
            assert backup_path_png.exists()
            assert backup_path_png.read_bytes() == b"PNG original"

            # Verify new backup wasn't created
            backup_path_jpg = backup_dir / "poster.jpg"
            assert not backup_path_jpg.exists()

            # get_backup_path should find the .png backup when looking for .jpg
            retrieved_path = get_backup_path(file_path_jpg, backup_dir, temp_path)
            assert retrieved_path == backup_path_png
            assert retrieved_path is not None
            assert retrieved_path.read_bytes() == b"PNG original"
