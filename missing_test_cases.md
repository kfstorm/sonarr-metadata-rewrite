# Missing Unit Test Cases for Coverage Improvement# Missing Test Cases for Coverage Improvement

Based on coverage report analysis (current: 91%, target: 95%+), this document identifies specific missing test cases organized by module with their actual uncovered line numbers.Based on coverage report analysis (current: 91%, target: 95%+), this document identifies missing test cases organized by module and missing coverage lines.

## Coverage Summary## Coverage Summary

- **Current Overall**: 91% (1057 statements, 73 missed, 50 partial branches)- **Current Overall**: 91% (1057 statements, 73 missed)

- **Target**: 95%+- **Target**: 95%+

- **Total New Tests Needed**: ~25 tests- **Total New Tests Needed**: ~25 tests

- **Priority Modules**:- **Priority Modules**:

  1. `image_utils.py` (73% → 95%+, gap: 22%)  1. `image_utils.py` (73% → 95%+, gap: 22%)

  2. `file_scanner.py` (80% → 95%+, gap: 15%)  2. `file_scanner.py` (80% → 95%+, gap: 15%)

  3. `image_processor.py` (86% → 95%+, gap: 9%)  3. `image_processor.py` (86% → 95%+, gap: 9%)

  4. `rollback_service.py` (93% → 100%, gap: 7%)  4. `rollback_service.py` (93% → 100%, gap: 7%)

------

## 1. image_utils.py (Current: 73%, Target: 95%+)## 1. Translator.select_best_image() - 12 Tests

**Missing lines**: 23, 42→57, 45, 47, 51-55, 92, 105-115**File**: `tests/unit/test_translator.py`

### Tests to Add to `tests/unit/test_image_utils.py`**Status**: ❌ NO TESTS EXIST

#### 1. test_read_marker_from_nonexistent_file### Test Cases

```python1. **test_select_best_image_poster_exact_match**

def test_read_marker_from_nonexistent_file(tmp_path: Path) -> None:   - Setup: Mock TMDB API to return posters with "en-US" and "ja-JP" images

    """Test reading marker from non-existent file returns None (line 23)."""   - Input: tmdb_ids, preferred_languages=["en-US"], kind="poster"

    nonexistent = tmp_path / "does_not_exist.jpg"   - Expected: Returns ImageCandidate with en-US poster

    result = read_embedded_marker(nonexistent)

    assert result is None2. **test_select_best_image_clearlogo_exact_match**

```   - Setup: Mock TMDB API to return clearlogos with language tags

   - Input: tmdb_ids, preferred_languages=["ja-JP"], kind="clearlogo"

#### 2. test_read_jpeg_with_unicode_encoded_user_comment   - Expected: Returns ImageCandidate with ja-JP clearlogo



```python3. **test_select_best_image_season_poster**

def test_read_jpeg_with_unicode_encoded_user_comment(tmp_path: Path) -> None:   - Setup: Mock TMDB API season endpoint

    """Test reading JPEG with UNICODE-prefixed UserComment (lines 47, 51-55)."""   - Input: tmdb_ids with season=1, preferred_languages=["en-US"], kind="poster"

    marker_data = {"test": "unicode"}   - Expected: Calls correct endpoint `/tv/{id}/season/1/images` and returns match

    jpeg_path = tmp_path / "unicode.jpg"

    4. **test_select_best_image_preference_order**

    img = Image.new("RGB", (100, 100), color="blue")   - Setup: Mock TMDB API with "ja-JP", "en-US", "zh-CN" posters

       - Input: preferred_languages=["en-US", "ja-JP", "zh-CN"]

    # Create UserComment with UNICODE\x00 prefix   - Expected: Returns en-US poster (first preference match)

    marker_json = json.dumps(marker_data)

    user_comment = b"UNICODE\x00" + marker_json.encode("utf-8")5. **test_select_best_image_no_match_returns_none**

    exif_dict = {"Exif": {piexif.ExifIFD.UserComment: user_comment}}   - Setup: Mock TMDB API with only "fr-FR" posters

    exif_bytes = piexif.dump(exif_dict)   - Input: preferred_languages=["en-US", "ja-JP"]

       - Expected: Returns None

    img.save(jpeg_path, "JPEG", exif=exif_bytes)

    6. **test_select_best_image_skips_null_language**

    result = read_embedded_marker(jpeg_path)   - Setup: Mock TMDB API with candidates having null iso_639_1 or iso_3166_1

    assert result == marker_data   - Input: preferred_languages=["en-US"]

```   - Expected: Skips null candidates, returns valid match or None



#### 3. test_read_jpeg_with_ascii_encoded_user_comment7. **test_select_best_image_skips_malformed_language_codes**

   - Setup: Valid API response

```python   - Input: preferred_languages=["en", "US", "en-US"] (malformed without hyphen)

def test_read_jpeg_with_ascii_encoded_user_comment(tmp_path: Path) -> None:   - Expected: Skips "en" and "US", uses "en-US"

    """Test reading JPEG with ASCII prefix (lines 45, 47)."""

    marker_data = {"test": "ascii"}8. **test_select_best_image_handles_404**

    jpeg_path = tmp_path / "ascii.jpg"   - Setup: Mock TMDB API to return 404

       - Input: tmdb_ids, preferred_languages=["en-US"], kind="poster"

    img = Image.new("RGB", (100, 100), color="green")   - Expected: Returns None (no exception thrown)



    # Create UserComment with ASCII\x00\x00\x00 prefix9. **test_select_best_image_caching**

    marker_json = json.dumps(marker_data)   - Setup: Mock TMDB API call

    user_comment = b"ASCII\x00\x00\x00" + marker_json.encode("utf-8")   - Action: Call select_best_image() twice with same parameters

    exif_dict = {"Exif": {piexif.ExifIFD.UserComment: user_comment}}   - Expected: API called only once (second call uses cache)

    exif_bytes = piexif.dump(exif_dict)

    10. **test_select_best_image_different_language_combinations**

    img.save(jpeg_path, "JPEG", exif=exif_bytes)    - Setup: Mock TMDB API with various language-country combinations

        - Input: Test "en-GB", "pt-BR", "zh-CN", "es-MX"

    result = read_embedded_marker(jpeg_path)    - Expected: Each returns correct match based on exact lang-country pair

    assert result == marker_data

```11. **test_select_best_image_empty_array**

   - Setup: Mock TMDB API returns empty posters/clearlogos array

#### 4. test_embed_marker_in_unsupported_format    - Input: preferred_languages=["en-US"], kind="poster"

    - Expected: Returns None

```python

def test_embed_marker_in_unsupported_format(tmp_path: Path) -> None:12. **test_select_best_image_invalid_kind**

    """Test embedding marker in unsupported format (lines 92, 105-115)."""    - Setup: Valid TMDB response

    marker_data = {"test": "unsupported"}    - Input: kind="banner" (invalid)

    dst = tmp_path / "output.bmp"    - Expected: Returns None



    # Create BMP image bytes---

    img = Image.new("RGB", (50, 50), color="yellow")

    output = BytesIO()## 2. ImageProcessor - 23 Tests

    img.save(output, format="BMP")

    raw_bytes = output.getvalue()**File**: `tests/unit/test_image_processor.py` (NEW FILE)



    # Should not raise**Status**: ❌ NO TESTS EXIST

    embed_marker_and_atomic_write(raw_bytes, dst, marker_data)

    ### Test Cases

    assert dst.exists()

    # Marker won't be readable from BMP#### Success Scenarios (18 tests)

    result = read_embedded_marker(dst)

    assert result is None1. **test_process_poster_success**

```   - Setup: Create poster.jpg, mock NFO with TMDB ID, mock translator.select_best_image()

   - Action: Call process(poster.jpg)

#### 5. test_atomic_write_cleanup_on_error   - Expected: ImageProcessResult with success=True, file_modified=True, backup_created=True



```python2. **test_process_clearlogo_success**

def test_atomic_write_cleanup_on_error(tmp_path: Path) -> None:   - Setup: Create clearlogo.png, mock NFO, mock translator

    """Test temp file cleanup on write error (lines 105-115)."""   - Action: Call process(clearlogo.png)

    marker_data = {"test": "cleanup"}   - Expected: Success with correct kind="clearlogo"

    dst = tmp_path / "error.png"

    3. **test_process_season_poster_success**

    raw_bytes = _create_image_bytes((30, 30), "white", "PNG")   - Setup: Create season01-poster.jpg, mock season.nfo with TMDB ID

       - Action: Call process(season01-poster.jpg)

    # Mock os.replace to raise exception   - Expected: Success with season number in marker

    with patch("os.replace", side_effect=OSError("Mock error")):

        with pytest.raises(OSError, match="Mock error"):4. **test_process_image_already_has_marker**

            embed_marker_and_atomic_write(raw_bytes, dst, marker_data)   - Setup: Create poster.jpg with embedded marker

       - Action: Call process(poster.jpg)

    # Verify temp files cleaned up   - Expected: ImageProcessResult with success=True, file_modified=False, message contains "already processed"

    temp_files = list(tmp_path.glob(".tmp_*"))

    assert len(temp_files) == 05. **test_process_no_nfo_found**

```   - Setup: Create poster.jpg without any NFO file

   - Action: Call process(poster.jpg)

**Expected improvement**: 73% → 95%+ (+22%)   - Expected: ImageProcessResult with success=False, message contains "No NFO file found"



---6. **test_process_nfo_has_no_tmdb_id**

   - Setup: Create poster.jpg and NFO without TMDB ID

## 2. image_processor.py (Current: 86%, Target: 95%+)   - Action: Call process(poster.jpg)

   - Expected: ImageProcessResult with success=False, message contains "No TMDB ID"

**Missing lines**: 58, 93→112, 165, 172→176, 177→188, 183-186, 205, 251, 271

7. **test_process_no_image_candidate_selected**

### Tests to Add to `tests/unit/test_image_processor.py`   - Setup: Mock translator.select_best_image() returns None

   - Action: Call process(poster.jpg)

#### 1. test_process_unrecognized_image_filename   - Expected: ImageProcessResult with success=False, message contains "No suitable image"



```python8. **test_process_tmdb_download_fails**

def test_process_unrecognized_image_filename(   - Setup: Mock HTTP client to raise exception on image download

    tmp_path: Path, image_processor: ImageProcessor   - Action: Call process(poster.jpg)

) -> None:   - Expected: ImageProcessResult with success=False, exception set

    """Test unrecognized image filename (line 58)."""

    series_dir = tmp_path / "Series"9. **test_process_backup_creation_fails**

    series_dir.mkdir()   - Setup: Mock backup directory to be read-only

       - Action: Call process(poster.jpg)

    unrecognized_path = series_dir / "banner.jpg"   - Expected: ImageProcessResult with success=False, backup_created=False

    create_test_image(unrecognized_path)

    10. **test_parse_image_info_poster**

    result = image_processor.process(unrecognized_path)    - Input: basename="poster.jpg"

        - Expected: ("poster", None)

    assert result.success is False

    assert "Unrecognized image file" in result.message11. **test_parse_image_info_season_poster**

    assert result.kind == ""    - Input: basename="season01-poster.jpg", "season10-poster.png"

```    - Expected: ("poster", 1), ("poster", 10)



#### 2. test_process_image_nfo_not_found12. **test_parse_image_info_clearlogo**

   - Input: basename="clearlogo.png"

```python   - Expected: ("clearlogo", None)

def test_process_image_nfo_not_found(

    tmp_path: Path, image_processor: ImageProcessor13. **test_resolve_tmdb_ids_same_directory**

) -> None:    - Setup: Create Season 1/poster.jpg and Season 1/tvshow.nfo

    """Test NFO not found (line 165, 183-186)."""    - Action: Call _resolve_tmdb_ids(poster.jpg)

    series_dir = tmp_path / "Series"    - Expected: Returns TmdbIds from tvshow.nfo

    series_dir.mkdir()

    14. **test_resolve_tmdb_ids_parent_directory**

    poster_path = series_dir / "poster.jpg"    - Setup: Create Season 1/poster.jpg and tvshow.nfo in parent

    create_test_image(poster_path)    - Action: Call _resolve_tmdb_ids(poster.jpg)

        - Expected: Returns TmdbIds from parent tvshow.nfo

    result = image_processor.process(poster_path)

    15. **test_resolve_tmdb_ids_season_nfo_priority**

    assert result.success is False    - Setup: Create both season.nfo and tvshow.nfo

    assert "Could not resolve TMDB ID from NFO" in result.message    - Action: Call _resolve_tmdb_ids(season01-poster.jpg)

```    - Expected: Prefers season.nfo over tvshow.nfo for season posters



#### 3. test_process_season_poster_fallback_to_tvshow_nfo16. **test_create_backup_creates_proper_structure**

    - Setup: Create poster.jpg in /path/to/show/Season 1/

```python    - Action: Call _create_backup(poster.jpg)

def test_process_season_poster_fallback_to_tvshow_nfo(    - Expected: Backup created at backup_dir/show/Season 1/poster.jpg

    tmp_path: Path, image_processor: ImageProcessor

) -> None:17. **test_download_and_write_image_extension_change**

    """Test season poster fallback to tvshow.nfo (lines 172→176, 177→188)."""    - Setup: poster.jpg exists, TMDB returns PNG image

    series_dir = tmp_path / "Series"    - Action: Call _download_and_write_image()

    season_dir = series_dir / "Season 01"    - Expected: poster.png created, poster.jpg removed

    season_dir.mkdir(parents=True)

    18. **test_download_and_write_image_atomic_write**

    season_poster = season_dir / "season01-poster.jpg"    - Setup: Mock file system to verify atomic write pattern

    create_test_image(season_poster)    - Action: Call _download_and_write_image()

        - Expected: Writes to temp file first, then os.replace()

    # No season.nfo, but tvshow.nfo in parent

    tvshow_nfo = series_dir / "tvshow.nfo"#### Error Scenarios (5 tests)

    create_test_nfo(tvshow_nfo, 12345)

    1. **test_process_network_failure_during_tmdb_download**

    candidate = ImageCandidate(   - Setup: Mock HTTP client to raise httpx.NetworkError on image download

        file_path="/test.jpg", iso_639_1="en", iso_3166_1="US"   - Action: Call process(poster.jpg)

    )   - Expected: ImageProcessResult with success=False, exception set, no partial files

    image_processor.translator.select_best_image = Mock(return_value=candidate)

    2. **test_process_corrupted_image_response**

    img = Image.new("RGB", (100, 100), color="blue")   - Setup: Mock TMDB API to return invalid image bytes

    output = BytesIO()   - Action: Call process(poster.jpg)

    img.save(output, format="JPEG")   - Expected: ImageProcessResult with success=False, original file intact

    mock_response = Mock(content=output.getvalue())

    image_processor.http_client.get = Mock(return_value=mock_response)3. **test_process_permission_error_on_backup**

       - Setup: Mock backup directory to raise PermissionError

    result = image_processor.process(season_poster)   - Action: Call process(poster.jpg)

       - Expected: ImageProcessResult with success=False, backup_created=False

    assert result.success is True

    assert result.kind == "poster"4. **test_process_disk_full_during_write**

```   - Setup: Mock file write to raise OSError (disk full)

   - Action: Call process(poster.jpg)

#### 4. test_process_no_backup_when_backup_dir_none   - Expected: ImageProcessResult with success=False, original file intact



```python5. **test_process_file_deleted_during_processing**

def test_process_no_backup_when_backup_dir_none(   - Setup: Mock NFO file to exist initially, then be deleted

    tmp_path: Path, image_processor: ImageProcessor   - Action: Call process(poster.jpg)

) -> None:   - Expected: ImageProcessResult with success=False, graceful handling

    """Test no backup when backup_dir is None (line 205)."""

    image_processor.settings.original_files_backup_dir = None---



    series_dir = tmp_path / "Series"## 3. image_utils - 10 Tests

    series_dir.mkdir()

    poster_path = series_dir / "poster.jpg"**File**: `tests/unit/test_image_utils.py` (NEW FILE)

    nfo_path = series_dir / "tvshow.nfo"

    **Status**: ❌ NO TESTS EXIST

    create_test_image(poster_path)

    create_test_nfo(nfo_path, 12345)### Test Cases



    candidate = ImageCandidate(1. **test_read_embedded_marker_png_with_text_chunk**

        file_path="/new.jpg", iso_639_1="en", iso_3166_1="US"   - Setup: Create PNG with tEXt chunk containing JSON marker

    )   - Action: Call read_embedded_marker(png_path)

    image_processor.translator.select_best_image = Mock(return_value=candidate)   - Expected: Returns dict with marker data



    img = Image.new("RGB", (100, 100), color="green")2. **test_read_embedded_marker_jpeg_with_exif**

    output = BytesIO()   - Setup: Create JPEG with EXIF UserComment containing JSON marker

    img.save(output, format="JPEG")   - Action: Call read_embedded_marker(jpeg_path)

    mock_response = Mock(content=output.getvalue())   - Expected: Returns dict with marker data

    image_processor.http_client.get = Mock(return_value=mock_response)

    3. **test_read_embedded_marker_no_marker_returns_none**

    result = image_processor.process(poster_path)   - Setup: Create clean PNG/JPEG without marker

       - Action: Call read_embedded_marker(image_path)

    assert result.success is True   - Expected: Returns None

    assert result.backup_created is False

```4. **test_read_embedded_marker_malformed_json**

   - Setup: Create PNG with tEXt chunk containing invalid JSON

#### 5. test_process_extension_change_removes_old_file   - Action: Call read_embedded_marker(png_path)

   - Expected: Returns None (handles exception gracefully)

```python

def test_process_extension_change_removes_old_file(5. **test_read_embedded_marker_unsupported_format**

    tmp_path: Path, image_processor: ImageProcessor   - Setup: Create GIF or BMP file

) -> None:   - Action: Call read_embedded_marker(gif_path)

    """Test old file removed when extension changes (line 251)."""   - Expected: Returns None or raises appropriate exception

    series_dir = tmp_path / "Series"

    series_dir.mkdir()6. **test_embed_marker_and_atomic_write_png**

       - Setup: Create PNG image bytes and marker dict

    old_poster = series_dir / "poster.png"   - Action: Call embed_marker_and_atomic_write(bytes, dst, marker)

    nfo_path = series_dir / "tvshow.nfo"   - Expected: PNG written with tEXt chunk, read back successfully

    create_test_image(old_poster)

    create_test_nfo(nfo_path, 12345)7. **test_embed_marker_and_atomic_write_jpeg_with_piexif**

       - Setup: Create JPEG bytes and marker dict, piexif available

    # TMDB returns .jpg   - Action: Call embed_marker_and_atomic_write(bytes, dst, marker)

    candidate = ImageCandidate(   - Expected: JPEG written with EXIF UserComment

        file_path="/test.jpg", iso_639_1="en", iso_3166_1="US"

    )8. **test_embed_marker_and_atomic_write_jpeg_without_piexif**

    image_processor.translator.select_best_image = Mock(return_value=candidate)   - Setup: Mock piexif as unavailable

       - Action: Call embed_marker_and_atomic_write(jpeg_bytes, dst, marker)

    img = Image.new("RGB", (100, 100), color="blue")   - Expected: Falls back to writing without marker (or appropriate behavior)

    output = BytesIO()

    img.save(output, format="JPEG")9. **test_embed_marker_and_atomic_write_atomic_operation**

    mock_response = Mock(content=output.getvalue())   - Setup: Mock file system

    image_processor.http_client.get = Mock(return_value=mock_response)   - Action: Call embed_marker_and_atomic_write()

       - Expected: Verifies temp file created, then os.replace() called

    result = image_processor.process(old_poster)

    10. **test_embed_marker_and_atomic_write_invalid_image_data**

    assert result.success is True    - Setup: Provide corrupted image bytes

    assert not old_poster.exists()    - Action: Call embed_marker_and_atomic_write()

    assert (series_dir / "poster.jpg").exists()    - Expected: Raises appropriate exception

```

------

#### 6. test_process_unsupported_tmdb_format

## 4. RollbackService - 5 Tests

```python

def test_process_unsupported_tmdb_format(**File**: `tests/unit/test_rollback_service.py`

    tmp_path: Path, image_processor: ImageProcessor

) -> None:**Status**: ⚠️ PARTIAL COVERAGE (needs image-specific tests)

    """Test error when TMDB returns unsupported format (lines 93→112)."""

    series_dir = tmp_path / "Series"### Test Cases

    series_dir.mkdir()

    poster_path = series_dir / "poster.jpg"1. **test_restore_image_with_extension_change**

    nfo_path = series_dir / "tvshow.nfo"   - Setup: Backup has poster.png, current directory has poster.jpg

       - Action: Call execute_rollback()

    create_test_image(poster_path)   - Expected: poster.jpg removed, poster.png restored

    create_test_nfo(nfo_path, 12345)

    2. **test_restore_removes_all_extension_variants**

    candidate = ImageCandidate(   - Setup: Backup has clearlogo.png, current has clearlogo.jpg and clearlogo.jpeg

        file_path="/test.webp", iso_639_1="en", iso_3166_1="US"   - Action: Call execute_rollback()

    )   - Expected: Both clearlogo.jpg and clearlogo.jpeg removed, clearlogo.png restored

    image_processor.translator.select_best_image = Mock(return_value=candidate)

    3. **test_restore_both_nfo_and_images**

    mock_response = Mock(content=b"fake webp data")   - Setup: Backup contains tvshow.nfo and poster.jpg

    image_processor.http_client.get = Mock(return_value=mock_response)   - Action: Call execute_rollback()

       - Expected: Both files restored successfully

    result = image_processor.process(poster_path)

    4. **test_restore_mixed_backup_directory**

    assert result.success is False   - Setup: Backup has NFO files, posters, and clearlogos

    assert "Unsupported image format" in result.message   - Action: Call execute_rollback()

```   - Expected: All files restored, correct counts logged



#### 7. test_close_http_client5. **test_restore_case_insensitive_extensions**

   - Setup: Backup has poster.png, current has poster.JPG (uppercase)

```python   - Action: Call execute_rollback()

def test_close_http_client(image_processor: ImageProcessor) -> None:   - Expected: poster.JPG removed, poster.png restored

    """Test closing HTTP client (line 271)."""

    image_processor.close()---



    # Verify client closed## 5. RewriteService - 5 Tests

    with pytest.raises(Exception):

        image_processor.http_client.get("http://example.com")**File**: `tests/unit/test_rewrite_service.py`

```

**Status**: ⚠️ PARTIAL COVERAGE (needs image routing tests)

**Expected improvement**: 86% → 95%+ (+9%)

### Test Cases

------

1. **test_process_file_routes_image_to_image_processor**

## 3. file_scanner.py (Current: 80%, Target: 95%+)   - Setup: Mock ImageProcessor

- Action: Call _process_file(poster.jpg)

**Missing lines**: 33, 42→45, 45→49, 61-62, 65→58, 84, 87→82, 90-92, 101→96, 104-109   - Expected: ImageProcessor.process() called, not MetadataProcessor

### Tests to Add to `tests/unit/test_file_scanner.py`2. **test_process_file_routes_nfo_to_metadata_processor**

- Setup: Mock MetadataProcessor

#### 1. test_scanner_handles_scan_loop_exception   - Action: Call _process_file(tvshow.nfo)

- Expected: MetadataProcessor.process_file() called, not ImageProcessor

```python

def test_scanner_handles_scan_loop_exception(3. **test_process_file_callback_logs_image_success**

    file_scanner: FileScanner, callback_tracker: Mock   - Setup: Mock ImageProcessor to return success result

) -> None:   - Action: Call _process_file_callback(poster.jpg)

    """Test scanner handles exceptions in scan loop (lines 61-62)."""   - Expected: Logger.info called with "✅" message

    with patch.object(

        file_scanner, "_perform_scan", side_effect=RuntimeError("Mock error")4. **test_process_file_callback_logs_image_failure**

    ):   - Setup: Mock ImageProcessor to return failure result

        file_scanner.start(callback_tracker)   - Action: Call _process_file_callback(poster.jpg)

        time.sleep(0.2)   - Expected: Logger.warning called with "⚠️" message

        file_scanner.stop()

    5. **test_integration_both_processors_working**

    # Should not crash   - Setup: Create NFO and poster in test directory

```   - Action: Process both files through service

   - Expected: Both processed correctly with appropriate results

#### 2. test_scanner_handles_permission_error

---

```python

def test_scanner_handles_permission_error(## 6. FileMonitor (MediaFileHandler) - 3 Tests

    file_scanner: FileScanner, callback_tracker: Mock

) -> None:**File**: `tests/unit/test_file_monitor.py`

    """Test scanner handles PermissionError (lines 104-109)."""

    test_dir = file_scanner.settings.rewrite_root_dir / "test_permission"**Status**: ✅ BASIC COVERAGE (tests added, could use more scenarios)

    test_dir.mkdir()

    ### Additional Test Cases

    original_root = file_scanner.settings.rewrite_root_dir

    file_scanner.settings.rewrite_root_dir = test_dir1. **test_media_file_handler_detects_poster_creation**

       - Setup: Mock file system event for poster.jpg creation

    try:   - Action: Trigger on_created event

        with patch(   - Expected: Callback invoked with poster.jpg path

            "sonarr_metadata_rewrite.file_scanner.find_nfo_files",

            side_effect=PermissionError("Access denied"),2. **test_media_file_handler_detects_clearlogo_modification**

        ):   - Setup: Mock file system event for clearlogo.png modification

            file_scanner.start(callback_tracker)   - Action: Trigger on_modified event

            time.sleep(0.1)   - Expected: Callback invoked with clearlogo.png path

            file_scanner.stop()

    finally:3. **test_media_file_handler_ignores_banner**

        if test_dir.exists():   - Setup: Mock file system event for banner.jpg

            shutil.rmtree(test_dir)   - Action: Trigger on_created event

        file_scanner.settings.rewrite_root_dir = original_root   - Expected: Callback NOT invoked

```

------

#### 3. test_scanner_stop_event_during_nfo_processing

## 7. FileScanner - 3 Tests

```python

def test_scanner_stop_event_during_nfo_processing(**File**: `tests/unit/test_file_scanner.py`

    file_scanner: FileScanner, callback_tracker: Mock

) -> None:**Status**: ⚠️ PARTIAL COVERAGE (needs image scanning tests)

    """Test stop event during NFO processing (lines 84, 87→82)."""

    test_dir = file_scanner.settings.rewrite_root_dir / "test_stop_nfo"### Test Cases

    original_root = file_scanner.settings.rewrite_root_dir

    file_scanner.settings.rewrite_root_dir = test_dir1. **test_scanner_finds_both_nfo_and_images**

       - Setup: Directory with tvshow.nfo, poster.jpg, clearlogo.png, banner.jpg

    try:   - Action: Call _perform_scan()

        for i in range(100):   - Expected: Processes tvshow.nfo, poster.jpg, clearlogo.png (not banner.jpg)

            nfo_path = test_dir / f"test{i}.nfo"

            nfo_path.parent.mkdir(parents=True, exist_ok=True)2. **test_scanner_processes_images_after_nfo**

            nfo_path.touch()   - Setup: Directory with files, mock callback to track order

           - Action: Call _perform_scan()

        def slow_callback(path: Path) -> None:   - Expected: NFO files processed first, then images

            time.sleep(0.01)

            callback_tracker(path)3. **test_scanner_image_only_directory**

           - Setup: Directory with only poster.jpg and clearlogo.png

        file_scanner.start(slow_callback)   - Action: Call _perform_scan()

        time.sleep(0.05)   - Expected: Both images processed successfully

        file_scanner.stop()

        ---

        assert callback_tracker.call_count < 100

    finally:## 8. Models - 4 Tests

        if test_dir.exists():

            shutil.rmtree(test_dir)**File**: `tests/unit/test_models.py`

        file_scanner.settings.rewrite_root_dir = original_root

```**Status**: ⚠️ PARTIAL COVERAGE (needs new model tests)



#### 4. test_scanner_stop_event_during_image_processing### Test Cases



```python1. **test_image_candidate_initialization**

def test_scanner_stop_event_during_image_processing(   - Action: Create ImageCandidate with file_path, iso_639_1, iso_3166_1

    file_scanner: FileScanner, callback_tracker: Mock   - Expected: All fields set correctly

) -> None:

    """Test stop event during image processing (lines 90-92)."""2. **test_image_process_result_initialization**

    test_dir = file_scanner.settings.rewrite_root_dir / "test_stop_images"   - Action: Create ImageProcessResult with all fields

    original_root = file_scanner.settings.rewrite_root_dir   - Expected: Inherits from ProcessResult, has image-specific fields

    file_scanner.settings.rewrite_root_dir = test_dir

    3. **test_process_result_base_class**

    try:   - Action: Create base ProcessResult

        for i in range(100):   - Expected: Has common fields, no metadata/image specific fields

            img_path = test_dir / f"poster{i}.jpg"

            img_path.parent.mkdir(parents=True, exist_ok=True)4. **test_metadata_process_result_backward_compatibility**

            img_path.touch()   - Action: Create MetadataProcessResult

           - Expected: Has all ProcessResult fields plus tmdb_ids and translated_content

        def slow_callback(path: Path) -> None:

            time.sleep(0.01)---

            callback_tracker(path)

        ## 9. Integration Tests - Extend Existing Tests - 3 Tests

        file_scanner.start(slow_callback)

        time.sleep(0.05)**File**: `tests/integration/test_sonarr_integration.py`

        file_scanner.stop()

        **Status**: ⚠️ EXTEND EXISTING (add image verification to current tests)

        assert callback_tracker.call_count < 100

    finally:### Strategy

        if test_dir.exists():

            shutil.rmtree(test_dir)Instead of creating new integration tests, extend existing ones to verify image processing:

        file_scanner.settings.rewrite_root_dir = original_root

```- Modify `SeriesWithNfos` to also create placeholder images (poster.jpg, clearlogo.png)

- Add helper function `verify_images()` to verify image processing and language/country in markers

#### 5. test_scanner_callback_exception_for_images- Update existing tests to verify both NFO and image processing

- **Note**: `test_advanced_translation_scenarios` is for complicated translation tests only, skip image verification there

```python

def test_scanner_callback_exception_for_images(### Integration Test Cases

    file_scanner: FileScanner, callback_tracker: Mock

) -> None:1. **test_file_monitor_workflow (EXTEND)**

    """Test callback exception handling for images (lines 101→96)."""   - **Current**: Tests NFO file monitoring and translation

    test_dir = file_scanner.settings.rewrite_root_dir / "test_callback_error"   - **Add**: Create poster.jpg and clearlogo.png alongside NFO files

    original_root = file_scanner.settings.rewrite_root_dir   - **Verify**: Images rewritten with TMDB images, markers embedded with correct language/country info (zh-CN)

    file_scanner.settings.rewrite_root_dir = test_dir   - **Expected**: Both NFO and images processed in real-time



    try:2. **test_file_scanner_workflow (EXTEND)**

        test_files = [   - **Current**: Tests NFO file scanning and translation

            test_dir / "poster.jpg",   - **Add**: Create season01-poster.jpg in season directory

            test_dir / "clearlogo.png",   - **Verify**: Season poster rewritten with correct TMDB season poster, marker contains zh-CN language info

        ]   - **Expected**: Scanner processes both NFO and images



        for test_file in test_files:3. **test_rollback_service_mode (EXTEND)**

            test_file.parent.mkdir(parents=True, exist_ok=True)   - **Current**: Tests NFO rollback functionality

            test_file.touch()   - **Add**: Include images in initial setup (poster.jpg, clearlogo.png)

           - **Verify**: Both NFO and images restored, extension changes handled (.jpg ↔ .png)

        def error_callback(path: Path) -> None:   - **Expected**: Complete rollback of both file types

            callback_tracker(path)

            if path.suffix.lower() in [".jpg", ".jpeg", ".png"]:### Helper Updates Needed

                raise ValueError("Mock image processing error")

        **File**: `tests/integration/test_helpers.py`

        file_scanner.start(error_callback)

        time.sleep(0.1)1. **Add `create_placeholder_images()` function**

        file_scanner.stop()

           ```python

        assert callback_tracker.call_count == 2   def create_placeholder_images(series_path: Path, season: int | None = None) -> list[Path]:

    finally:       """Create minimal valid JPEG/PNG images as placeholders."""

        if test_dir.exists():   ```

            shutil.rmtree(test_dir)

        file_scanner.settings.rewrite_root_dir = original_root2. **Add `verify_images()` function**

```

   ```python

**Expected improvement**: 80% → 95%+ (+15%)   def verify_images(

       image_paths: list[Path],

---       expected_language: str,

       expect_marker: bool = True,

## 4. rollback_service.py (Current: 93%, Target: 100%)       expect_backup: bool = False,

   ) -> None:

**Missing lines**: 75-77, 131-133       """Verify images have been processed.



### Tests to Add to `tests/unit/test_rollback_service.py`       Checks:

       - Marker embedded with correct language/country info (e.g., zh-CN)

#### 1. test_rollback_file_when_backup_does_not_exist       - Backups created if expect_backup=True

       - Language and country code in marker match expected_language

```python       """

def test_rollback_file_when_backup_does_not_exist(   ```

    rollback_service: RollbackService, tmp_path: Path

) -> None:3. **Update `SeriesWithNfos` class**

    """Test rollback when backup doesn't exist (lines 75-77)."""

    file_path = tmp_path / "file.nfo"   - Add `create_images: bool = False` parameter

    file_path.write_text("current content")   - If True, create placeholder images alongside NFO files

       - Return tuple of (nfo_files, image_files) instead of just nfo_files

    result = rollback_service.rollback_file(file_path)

    ---

    assert result is False---

    assert file_path.exists()

    assert file_path.read_text() == "current content"## Expected Outcome

```

After implementing all missing tests:

### 2. test_cleanup_backups_when_backup_dir_does_not_exist

- **Total Tests**: ~215 tests (up from 147)

```python- **Confidence Level**: High for production deployment

def test_cleanup_backups_when_backup_dir_does_not_exist(- **Areas Fully Covered**:

    rollback_service: RollbackService, tmp_path: Path  - Image processing workflow

) -> None:  - TMDB image selection with language/country matching

    """Test cleanup when backup dir doesn't exist (lines 131-133)."""  - Marker embedding/reading with language verification

    rollback_service.settings.original_files_backup_dir = tmp_path / "nonexistent"  - Rollback with extension handling

      - File routing and monitoring

    # Should not raise  - Error scenarios (network, disk, permissions, corruption)

    rollback_service.cleanup_backups(days=7)

    ---

    assert not (tmp_path / "nonexistent").exists()---

```

## Notes

**Expected improvement**: 93% → 100% (+7%)

- All tests should follow existing test patterns in the repository

---- Use pytest fixtures from `tests/conftest.py` where applicable

- Integration tests should skip if `TMDB_API_KEY` not set

## Summary- Mock external HTTP calls in unit tests

- Use temporary directories for file system tests

**Total new test cases**: ~18 tests across 4 modules- Follow Black (line-length: 88) and Ruff linting rules

- Ensure MyPy type checking passes

**Expected coverage improvements**:

------

- `image_utils.py`: 73% → 95%+ (+22%)

- `file_scanner.py`: 80% → 95%+ (+15%)**Document Created**: 2025-10-27

- `image_processor.py`: 86% → 95%+ (+9%)**Last Updated**: 2025-10-27

- `rollback_service.py`: 93% → 100% (+7%)**Status**: Initial draft based on git diff analysis

- **Overall project**: 91% → 95%+ (+4%)

**Priority order**:

1. **image_utils.py** (biggest gap, 5 tests)
2. **file_scanner.py** (error handling, 5 tests)
3. **image_processor.py** (edge cases, 7 tests)
4. **rollback_service.py** (small gaps, 2 tests)

**Implementation notes**:

- All tests follow existing patterns in the repository
- Use pytest fixtures from `tests/conftest.py`
- Mock external HTTP calls in unit tests
- Use temporary directories for file system tests
- Follow Black (line-length: 88) and Ruff linting
- Ensure MyPy type checking passes
