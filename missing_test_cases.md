# Missing Test Cases for Image Rewriting Feature

This document lists all missing test cases identified from the git diff analysis. These tests are needed to achieve comprehensive coverage (~85-90%) of the image rewriting functionality.

## Summary

- **Current Status**: 147 passing tests (67% coverage)
- **Missing Tests**: ~68 test cases
- **Priority Areas**: ImageProcessor (with error scenarios), image_utils, Translator.select_best_image()
- **Integration Tests**: Extend existing 3 tests instead of creating 11 new ones

## Key Changes from Original Plan

1. **Integration Tests Simplified**: Instead of creating 11 new integration tests, extend 3 existing tests to verify image processing
2. **Error Scenarios Moved to Unit Tests**: 5 error scenarios moved from integration to ImageProcessor unit tests
3. **Total Test Count**: Reduced from ~76 to ~68 tests
4. **Implementation Time**: Reduced from ~10-13 hours to ~9-12 hours
5. **Language Verification**: `verify_images()` will check language/country info in embedded markers (e.g., zh-CN)

---

## 1. Translator.select_best_image() - 12 Tests

**File**: `tests/unit/test_translator.py`

**Status**: ❌ NO TESTS EXIST

### Test Cases

1. **test_select_best_image_poster_exact_match**
   - Setup: Mock TMDB API to return posters with "en-US" and "ja-JP" images
   - Input: tmdb_ids, preferred_languages=["en-US"], kind="poster"
   - Expected: Returns ImageCandidate with en-US poster

2. **test_select_best_image_clearlogo_exact_match**
   - Setup: Mock TMDB API to return clearlogos with language tags
   - Input: tmdb_ids, preferred_languages=["ja-JP"], kind="clearlogo"
   - Expected: Returns ImageCandidate with ja-JP clearlogo

3. **test_select_best_image_season_poster**
   - Setup: Mock TMDB API season endpoint
   - Input: tmdb_ids with season=1, preferred_languages=["en-US"], kind="poster"
   - Expected: Calls correct endpoint `/tv/{id}/season/1/images` and returns match

4. **test_select_best_image_preference_order**
   - Setup: Mock TMDB API with "ja-JP", "en-US", "zh-CN" posters
   - Input: preferred_languages=["en-US", "ja-JP", "zh-CN"]
   - Expected: Returns en-US poster (first preference match)

5. **test_select_best_image_no_match_returns_none**
   - Setup: Mock TMDB API with only "fr-FR" posters
   - Input: preferred_languages=["en-US", "ja-JP"]
   - Expected: Returns None

6. **test_select_best_image_skips_null_language**
   - Setup: Mock TMDB API with candidates having null iso_639_1 or iso_3166_1
   - Input: preferred_languages=["en-US"]
   - Expected: Skips null candidates, returns valid match or None

7. **test_select_best_image_skips_malformed_language_codes**
   - Setup: Valid API response
   - Input: preferred_languages=["en", "US", "en-US"] (malformed without hyphen)
   - Expected: Skips "en" and "US", uses "en-US"

8. **test_select_best_image_handles_404**
   - Setup: Mock TMDB API to return 404
   - Input: tmdb_ids, preferred_languages=["en-US"], kind="poster"
   - Expected: Returns None (no exception thrown)

9. **test_select_best_image_caching**
   - Setup: Mock TMDB API call
   - Action: Call select_best_image() twice with same parameters
   - Expected: API called only once (second call uses cache)

10. **test_select_best_image_different_language_combinations**
    - Setup: Mock TMDB API with various language-country combinations
    - Input: Test "en-GB", "pt-BR", "zh-CN", "es-MX"
    - Expected: Each returns correct match based on exact lang-country pair

11. **test_select_best_image_empty_array**
   - Setup: Mock TMDB API returns empty posters/clearlogos array
    - Input: preferred_languages=["en-US"], kind="poster"
    - Expected: Returns None

12. **test_select_best_image_invalid_kind**
    - Setup: Valid TMDB response
    - Input: kind="banner" (invalid)
    - Expected: Returns None

---

## 2. ImageProcessor - 23 Tests

**File**: `tests/unit/test_image_processor.py` (NEW FILE)

**Status**: ❌ NO TESTS EXIST

### Test Cases

#### Success Scenarios (18 tests)

1. **test_process_poster_success**
   - Setup: Create poster.jpg, mock NFO with TMDB ID, mock translator.select_best_image()
   - Action: Call process(poster.jpg)
   - Expected: ImageProcessResult with success=True, file_modified=True, backup_created=True

2. **test_process_clearlogo_success**
   - Setup: Create clearlogo.png, mock NFO, mock translator
   - Action: Call process(clearlogo.png)
   - Expected: Success with correct kind="clearlogo"

3. **test_process_season_poster_success**
   - Setup: Create season01-poster.jpg, mock season.nfo with TMDB ID
   - Action: Call process(season01-poster.jpg)
   - Expected: Success with season number in marker

4. **test_process_image_already_has_marker**
   - Setup: Create poster.jpg with embedded marker
   - Action: Call process(poster.jpg)
   - Expected: ImageProcessResult with success=True, file_modified=False, message contains "already processed"

5. **test_process_no_nfo_found**
   - Setup: Create poster.jpg without any NFO file
   - Action: Call process(poster.jpg)
   - Expected: ImageProcessResult with success=False, message contains "No NFO file found"

6. **test_process_nfo_has_no_tmdb_id**
   - Setup: Create poster.jpg and NFO without TMDB ID
   - Action: Call process(poster.jpg)
   - Expected: ImageProcessResult with success=False, message contains "No TMDB ID"

7. **test_process_no_image_candidate_selected**
   - Setup: Mock translator.select_best_image() returns None
   - Action: Call process(poster.jpg)
   - Expected: ImageProcessResult with success=False, message contains "No suitable image"

8. **test_process_tmdb_download_fails**
   - Setup: Mock HTTP client to raise exception on image download
   - Action: Call process(poster.jpg)
   - Expected: ImageProcessResult with success=False, exception set

9. **test_process_backup_creation_fails**
   - Setup: Mock backup directory to be read-only
   - Action: Call process(poster.jpg)
   - Expected: ImageProcessResult with success=False, backup_created=False

10. **test_parse_image_info_poster**
    - Input: basename="poster.jpg"
    - Expected: ("poster", None)

11. **test_parse_image_info_season_poster**
    - Input: basename="season01-poster.jpg", "season10-poster.png"
    - Expected: ("poster", 1), ("poster", 10)

12. **test_parse_image_info_clearlogo**
   - Input: basename="clearlogo.png"
   - Expected: ("clearlogo", None)

13. **test_resolve_tmdb_ids_same_directory**
    - Setup: Create Season 1/poster.jpg and Season 1/tvshow.nfo
    - Action: Call _resolve_tmdb_ids(poster.jpg)
    - Expected: Returns TmdbIds from tvshow.nfo

14. **test_resolve_tmdb_ids_parent_directory**
    - Setup: Create Season 1/poster.jpg and tvshow.nfo in parent
    - Action: Call _resolve_tmdb_ids(poster.jpg)
    - Expected: Returns TmdbIds from parent tvshow.nfo

15. **test_resolve_tmdb_ids_season_nfo_priority**
    - Setup: Create both season.nfo and tvshow.nfo
    - Action: Call _resolve_tmdb_ids(season01-poster.jpg)
    - Expected: Prefers season.nfo over tvshow.nfo for season posters

16. **test_create_backup_creates_proper_structure**
    - Setup: Create poster.jpg in /path/to/show/Season 1/
    - Action: Call _create_backup(poster.jpg)
    - Expected: Backup created at backup_dir/show/Season 1/poster.jpg

17. **test_download_and_write_image_extension_change**
    - Setup: poster.jpg exists, TMDB returns PNG image
    - Action: Call _download_and_write_image()
    - Expected: poster.png created, poster.jpg removed

18. **test_download_and_write_image_atomic_write**
    - Setup: Mock file system to verify atomic write pattern
    - Action: Call _download_and_write_image()
    - Expected: Writes to temp file first, then os.replace()

#### Error Scenarios (5 tests)

1. **test_process_network_failure_during_tmdb_download**
   - Setup: Mock HTTP client to raise httpx.NetworkError on image download
   - Action: Call process(poster.jpg)
   - Expected: ImageProcessResult with success=False, exception set, no partial files

2. **test_process_corrupted_image_response**
   - Setup: Mock TMDB API to return invalid image bytes
   - Action: Call process(poster.jpg)
   - Expected: ImageProcessResult with success=False, original file intact

3. **test_process_permission_error_on_backup**
   - Setup: Mock backup directory to raise PermissionError
   - Action: Call process(poster.jpg)
   - Expected: ImageProcessResult with success=False, backup_created=False

4. **test_process_disk_full_during_write**
   - Setup: Mock file write to raise OSError (disk full)
   - Action: Call process(poster.jpg)
   - Expected: ImageProcessResult with success=False, original file intact

5. **test_process_file_deleted_during_processing**
   - Setup: Mock NFO file to exist initially, then be deleted
   - Action: Call process(poster.jpg)
   - Expected: ImageProcessResult with success=False, graceful handling

---

## 3. image_utils - 10 Tests

**File**: `tests/unit/test_image_utils.py` (NEW FILE)

**Status**: ❌ NO TESTS EXIST

### Test Cases

1. **test_read_embedded_marker_png_with_text_chunk**
   - Setup: Create PNG with tEXt chunk containing JSON marker
   - Action: Call read_embedded_marker(png_path)
   - Expected: Returns dict with marker data

2. **test_read_embedded_marker_jpeg_with_exif**
   - Setup: Create JPEG with EXIF UserComment containing JSON marker
   - Action: Call read_embedded_marker(jpeg_path)
   - Expected: Returns dict with marker data

3. **test_read_embedded_marker_no_marker_returns_none**
   - Setup: Create clean PNG/JPEG without marker
   - Action: Call read_embedded_marker(image_path)
   - Expected: Returns None

4. **test_read_embedded_marker_malformed_json**
   - Setup: Create PNG with tEXt chunk containing invalid JSON
   - Action: Call read_embedded_marker(png_path)
   - Expected: Returns None (handles exception gracefully)

5. **test_read_embedded_marker_unsupported_format**
   - Setup: Create GIF or BMP file
   - Action: Call read_embedded_marker(gif_path)
   - Expected: Returns None or raises appropriate exception

6. **test_embed_marker_and_atomic_write_png**
   - Setup: Create PNG image bytes and marker dict
   - Action: Call embed_marker_and_atomic_write(bytes, dst, marker)
   - Expected: PNG written with tEXt chunk, read back successfully

7. **test_embed_marker_and_atomic_write_jpeg_with_piexif**
   - Setup: Create JPEG bytes and marker dict, piexif available
   - Action: Call embed_marker_and_atomic_write(bytes, dst, marker)
   - Expected: JPEG written with EXIF UserComment

8. **test_embed_marker_and_atomic_write_jpeg_without_piexif**
   - Setup: Mock piexif as unavailable
   - Action: Call embed_marker_and_atomic_write(jpeg_bytes, dst, marker)
   - Expected: Falls back to writing without marker (or appropriate behavior)

9. **test_embed_marker_and_atomic_write_atomic_operation**
   - Setup: Mock file system
   - Action: Call embed_marker_and_atomic_write()
   - Expected: Verifies temp file created, then os.replace() called

10. **test_embed_marker_and_atomic_write_invalid_image_data**
    - Setup: Provide corrupted image bytes
    - Action: Call embed_marker_and_atomic_write()
    - Expected: Raises appropriate exception

---

## 4. RollbackService - 5 Tests

**File**: `tests/unit/test_rollback_service.py`

**Status**: ⚠️ PARTIAL COVERAGE (needs image-specific tests)

### Test Cases

1. **test_restore_image_with_extension_change**
   - Setup: Backup has poster.png, current directory has poster.jpg
   - Action: Call execute_rollback()
   - Expected: poster.jpg removed, poster.png restored

2. **test_restore_removes_all_extension_variants**
   - Setup: Backup has clearlogo.png, current has clearlogo.jpg and clearlogo.jpeg
   - Action: Call execute_rollback()
   - Expected: Both clearlogo.jpg and clearlogo.jpeg removed, clearlogo.png restored

3. **test_restore_both_nfo_and_images**
   - Setup: Backup contains tvshow.nfo and poster.jpg
   - Action: Call execute_rollback()
   - Expected: Both files restored successfully

4. **test_restore_mixed_backup_directory**
   - Setup: Backup has NFO files, posters, and clearlogos
   - Action: Call execute_rollback()
   - Expected: All files restored, correct counts logged

5. **test_restore_case_insensitive_extensions**
   - Setup: Backup has poster.png, current has poster.JPG (uppercase)
   - Action: Call execute_rollback()
   - Expected: poster.JPG removed, poster.png restored

---

## 5. RewriteService - 5 Tests

**File**: `tests/unit/test_rewrite_service.py`

**Status**: ⚠️ PARTIAL COVERAGE (needs image routing tests)

### Test Cases

1. **test_process_file_routes_image_to_image_processor**
   - Setup: Mock ImageProcessor
   - Action: Call _process_file(poster.jpg)
   - Expected: ImageProcessor.process() called, not MetadataProcessor

2. **test_process_file_routes_nfo_to_metadata_processor**
   - Setup: Mock MetadataProcessor
   - Action: Call _process_file(tvshow.nfo)
   - Expected: MetadataProcessor.process_file() called, not ImageProcessor

3. **test_process_file_callback_logs_image_success**
   - Setup: Mock ImageProcessor to return success result
   - Action: Call _process_file_callback(poster.jpg)
   - Expected: Logger.info called with "✅" message

4. **test_process_file_callback_logs_image_failure**
   - Setup: Mock ImageProcessor to return failure result
   - Action: Call _process_file_callback(poster.jpg)
   - Expected: Logger.warning called with "⚠️" message

5. **test_integration_both_processors_working**
   - Setup: Create NFO and poster in test directory
   - Action: Process both files through service
   - Expected: Both processed correctly with appropriate results

---

## 6. FileMonitor (MediaFileHandler) - 3 Tests

**File**: `tests/unit/test_file_monitor.py`

**Status**: ✅ BASIC COVERAGE (tests added, could use more scenarios)

### Additional Test Cases

1. **test_media_file_handler_detects_poster_creation**
   - Setup: Mock file system event for poster.jpg creation
   - Action: Trigger on_created event
   - Expected: Callback invoked with poster.jpg path

2. **test_media_file_handler_detects_clearlogo_modification**
   - Setup: Mock file system event for clearlogo.png modification
   - Action: Trigger on_modified event
   - Expected: Callback invoked with clearlogo.png path

3. **test_media_file_handler_ignores_banner**
   - Setup: Mock file system event for banner.jpg
   - Action: Trigger on_created event
   - Expected: Callback NOT invoked

---

## 7. FileScanner - 3 Tests

**File**: `tests/unit/test_file_scanner.py`

**Status**: ⚠️ PARTIAL COVERAGE (needs image scanning tests)

### Test Cases

1. **test_scanner_finds_both_nfo_and_images**
   - Setup: Directory with tvshow.nfo, poster.jpg, clearlogo.png, banner.jpg
   - Action: Call _perform_scan()
   - Expected: Processes tvshow.nfo, poster.jpg, clearlogo.png (not banner.jpg)

2. **test_scanner_processes_images_after_nfo**
   - Setup: Directory with files, mock callback to track order
   - Action: Call _perform_scan()
   - Expected: NFO files processed first, then images

3. **test_scanner_image_only_directory**
   - Setup: Directory with only poster.jpg and clearlogo.png
   - Action: Call _perform_scan()
   - Expected: Both images processed successfully

---

## 8. Models - 4 Tests

**File**: `tests/unit/test_models.py`

**Status**: ⚠️ PARTIAL COVERAGE (needs new model tests)

### Test Cases

1. **test_image_candidate_initialization**
   - Action: Create ImageCandidate with file_path, iso_639_1, iso_3166_1
   - Expected: All fields set correctly

2. **test_image_process_result_initialization**
   - Action: Create ImageProcessResult with all fields
   - Expected: Inherits from ProcessResult, has image-specific fields

3. **test_process_result_base_class**
   - Action: Create base ProcessResult
   - Expected: Has common fields, no metadata/image specific fields

4. **test_metadata_process_result_backward_compatibility**
   - Action: Create MetadataProcessResult
   - Expected: Has all ProcessResult fields plus tmdb_ids and translated_content

---

## 9. Integration Tests - Extend Existing Tests - 3 Tests

**File**: `tests/integration/test_sonarr_integration.py`

**Status**: ⚠️ EXTEND EXISTING (add image verification to current tests)

### Strategy

Instead of creating new integration tests, extend existing ones to verify image processing:

- Modify `SeriesWithNfos` to also create placeholder images (poster.jpg, clearlogo.png)
- Add helper function `verify_images()` to verify image processing and language/country in markers
- Update existing tests to verify both NFO and image processing
- **Note**: `test_advanced_translation_scenarios` is for complicated translation tests only, skip image verification there

### Integration Test Cases

1. **test_file_monitor_workflow (EXTEND)**
   - **Current**: Tests NFO file monitoring and translation
   - **Add**: Create poster.jpg and clearlogo.png alongside NFO files
   - **Verify**: Images rewritten with TMDB images, markers embedded with correct language/country info (zh-CN)
   - **Expected**: Both NFO and images processed in real-time

2. **test_file_scanner_workflow (EXTEND)**
   - **Current**: Tests NFO file scanning and translation
   - **Add**: Create season01-poster.jpg in season directory
   - **Verify**: Season poster rewritten with correct TMDB season poster, marker contains zh-CN language info
   - **Expected**: Scanner processes both NFO and images

3. **test_rollback_service_mode (EXTEND)**
   - **Current**: Tests NFO rollback functionality
   - **Add**: Include images in initial setup (poster.jpg, clearlogo.png)
   - **Verify**: Both NFO and images restored, extension changes handled (.jpg ↔ .png)
   - **Expected**: Complete rollback of both file types

### Helper Updates Needed

**File**: `tests/integration/test_helpers.py`

1. **Add `create_placeholder_images()` function**

   ```python
   def create_placeholder_images(series_path: Path, season: int | None = None) -> list[Path]:
       """Create minimal valid JPEG/PNG images as placeholders."""
   ```

2. **Add `verify_images()` function**

   ```python
   def verify_images(
       image_paths: list[Path],
       expected_language: str,
       expect_marker: bool = True,
       expect_backup: bool = False,
   ) -> None:
       """Verify images have been processed.

       Checks:
       - Marker embedded with correct language/country info (e.g., zh-CN)
       - Backups created if expect_backup=True
       - Language and country code in marker match expected_language
       """
   ```

3. **Update `SeriesWithNfos` class**

   - Add `create_images: bool = False` parameter
   - If True, create placeholder images alongside NFO files
   - Return tuple of (nfo_files, image_files) instead of just nfo_files

---
---

## Expected Outcome

After implementing all missing tests:

- **Total Tests**: ~215 tests (up from 147)
- **Confidence Level**: High for production deployment
- **Areas Fully Covered**:
  - Image processing workflow
  - TMDB image selection with language/country matching
  - Marker embedding/reading with language verification
  - Rollback with extension handling
  - File routing and monitoring
  - Error scenarios (network, disk, permissions, corruption)

---
---

## Notes

- All tests should follow existing test patterns in the repository
- Use pytest fixtures from `tests/conftest.py` where applicable
- Integration tests should skip if `TMDB_API_KEY` not set
- Mock external HTTP calls in unit tests
- Use temporary directories for file system tests
- Follow Black (line-length: 88) and Ruff linting rules
- Ensure MyPy type checking passes

---

**Document Created**: 2025-10-27
**Last Updated**: 2025-10-27
**Status**: Initial draft based on git diff analysis
