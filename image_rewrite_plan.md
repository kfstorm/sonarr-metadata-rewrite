# Image Rewrite Implementation Plan

This document describes the design and implementation plan for adding localized image rewriting (posters and logos) to the sonarr-metadata-rewrite project.

Goals

- Add support for writing localized series and season poster image files, and series logo image files, alongside existing .nfo rewrites.

- Be transparent and avoid sidecar JSON files in media folders.

- Respect user `preferred_languages` ordering and require exact language+country match (no null fallbacks).

- Avoid downloading multiple image candidates per rewrite. Download only one chosen candidate when necessary.

- Persist the chosen TMDB image identity inside the rewritten image itself so restarts/container recreation do not lose state.

- Be safe with atomic writes.

- Requirements checklist

- [x] Single config flag `enable_image_rewrite` (default on) gates the behavior. (integration step)

- [x] Selection logic lives in `Translator` and returns at most one candidate or None.

- [x] Exact language+country matching only, in the order of `Settings.preferred_languages`.

- [x] Image file naming: series poster `poster.<ext>`, season poster `season{season:02d}-poster.<ext>`, series logo `logo.<ext>`; extensions chosen from TMDB candidate and limited to `.jpg`, `.jpeg`, or `.png`.

- [x] No sidecar JSON files in media folders.

- [x] Write durable marker into image metadata (PNG tEXt/iTXt or JPEG EXIF `UserComment`) reusing `ImageCandidate` fields as JSON: `{ file_path, iso_639_1, iso_3166_1 }`.

- [x] Atomic write: generate final image bytes with embedded marker in memory, write once to a temp file in the same directory, then atomic replace via os.replace.

- [x] Unit tests for selection and metadata embedding/reading. Integration tests for end-to-end rewrite with HTTP mocks.

Design overview

Components

- Translator (`src/sonarr_metadata_rewrite/translator.py`)

  - New method: `select_best_image(tmdb_ids: TmdbIds, preferred_languages: list[str], kind: Literal["poster", "logo"]) -> ImageCandidate | None`

  - Responsibilities:

  - Infer endpoint: if `kind == "poster"` and `tmdb_ids.season` is set -> /tv/{id}/season/{s}/images; else -> /tv/{id}/images. Logos are selected only from series-level `/tv/{id}/images`.

  - Call TMDB images endpoint once using `include_image_language` built by comma-joining `preferred_languages` exactly as given (preserve region tokens like "en-US").

  - For each preferred language (must be lang-country format), select the first candidate in the array whose `iso_639_1` and `iso_3166_1` exactly match the language and country part of the token. Ignore `vote_count` and `vote_average`. If none found, try the next preferred language. If no match for any, return None.

  - Return ImageCandidate dataclass (simplified): `{ file_path: str, iso_639_1: Optional[str], iso_3166_1: Optional[str] }` or None.

- Image utils (`src/sonarr_metadata_rewrite/image_utils.py`)

  - Functions:

  - `read_embedded_marker(path: Path) -> dict | None` : fast read that parses PNG tEXt/iTXt chunk or JPEG EXIF `UserComment` and returns parsed JSON marker if present.

  - `embed_marker_and_atomic_write(raw_bytes: bytes, dst: Path, marker: dict) -> None` : embed marker into image bytes in memory (PNG tEXt or JPEG EXIF), write the finalized bytes to a temp file next to `dst`, then `os.replace` to `dst` atomically.

  - Implementation notes:

  - Use Pillow for image IO.

  - For JPEG EXIF write, use `piexif` if available for correct EXIF structure; otherwise fallback to Pillow's basic `info` approach.

  - Keep marker JSON minimal. Example: `{"file_path":"/tXx123.jpg","iso_639_1":"ja","iso_3166_1":"JP"}`.

  - Read only the necessary header bytes when possible to avoid loading entire files when not needed.

- Image processor (`src/sonarr_metadata_rewrite/image_processor.py`)

  - Class `ImageProcessor` with method `process(image_path: Path) -> ImageProcessResult`

  - Resolve TMDB context for the given `image_path`:
    - Determine if it's a series poster/logo or a season poster based on basename pattern (see scanning rules).
    - Locate the associated NFO (e.g., `tvshow.nfo` for series-level, `season.nfo` in season folders) and extract TMDB IDs using existing metadata logic; if missing, return a failure result.
  - If the file exists, read embedded marker. If `marker.file_path == selected_candidate.file_path` -> return a no-op success result. Only download and rewrite when they do not match.

  - Otherwise, download candidate URL (TMDB base image url + file_path) to memory, embed marker JSON into the image bytes in memory, write the finalized bytes to a temporary file in the same directory, then atomic replace the target file.
  - The TMDB image base URL is hardcoded as `https://image.tmdb.org/t/p/original` in ImageProcessor. The `ImageCandidate.file_path` is always the suffix part.
  - Compute the target filename using normalized naming and the TMDB candidate's extension. If an existing file uses a different extension, replace into the normalized path and optionally remove other extension variants after success.
  - Backup/restore: Before replacing, create a backup of the existing image (if any) using the same backup mechanism as `.nfo` files. On rollback, restore the previous image from backup. Clean up backups per existing retention policy.

  - Return `ImageProcessResult` describing status: { path, action: "skipped" | "written" | "failed", reason? }.

  - Download implementation:

    - Use httpx with streaming to memory (BytesIO) to avoid intermediate on-disk files before embedding.

    - Use a small retry/backoff helper already in repository (`retry_utils`) for transient errors.

Integration points

- `rewrite_service.py`
  - Orchestrates both metadata and image rewriting. Calls `MetadataProcessor.process` for `.nfo` files and `ImageProcessor.process` for image files directly.
  - Determines which files to process via `file_scanner.py` results (see scanning rules below).
  - Logs actions and aggregates `MetadataProcessResult` and `ImageProcessResult`.

- `metadata_processor.py`
  - Focused solely on `.nfo` rewrites. No direct responsibility for images.

- `image_processor.py`
  - Processes poster/logo image files as directed by `RewriteService`.

Rewrite decision

- The durable marker in image metadata allows us to detect if the current file matches the desired candidate's TMDB image.
- If the embedded `file_path` equals the selected candidate's `file_path`, skip rewriting; otherwise download and rewrite.

Scanning rules

- Monitor and scan all image files with extensions `.jpg`, `.jpeg`, and `.png`.
- Filter to only process recognized poster/logo basenames (case-insensitive):
  - Series poster: `poster.<ext>`
  - Season poster: `seasonXX-poster.<ext>` (zero-padded season number)
  - Series logo: `logo.<ext>`
- Derive processing scope from basename:
  - `poster.*` and `logo.*` are series-level; `seasonXX-poster.*` is season-level with parsed season number.
- When rewriting, compute the destination path using the normalized basename and the TMDB candidate's extension; if an old variant exists with a different extension, remove it after successful replace.

Selection rules (detailed)

- Build `include_image_language` string by joining `Settings.preferred_languages` with commas, preserving each token exactly as provided (e.g., `en-US,ja-JP,zh-CN`).
- Call the appropriate TMDB images endpoint with `include_image_language` to get candidate images.
  - For posters, select from the `posters` array (season-level or series-level as applicable).
  - For logos, select from the `logos` array (series-level only).
- Matching policy (strict lang-country only):
  - Require all `preferred_languages` tokens to be in `lang-country` format.
  - Filter out candidates with null `iso_639_1` or null `iso_3166_1`.
  - Select the first candidate whose `f"{iso_639_1}-{iso_3166_1}"` exactly equals a preference token, respecting user order.
  - If none match, return None. Do not fallback to language-only or null-language images.
- Tie-breaker (when multiple candidates share the exact same lang-country): prefer higher `vote_count`, then higher `vote_average`.

Testing plan

- Unit tests
  - `tests/unit/test_translator.py`: test `select_best_image` with mocked TMDB responses for series and season endpoints (posters) and series-level logos, ensure selection honors order and exact-match rules.
  - `tests/unit/test_image_utils.py`: test embedding and reading marker for JPEG and PNG bytes.
  - `tests/unit/test_image_processor.py`: mock HTTP responses for download-to-memory and assert atomic replace behavior.

- Integration tests (no HTTP mocking)
  - Run end-to-end rewrite flow with temporary directories and real TMDB HTTP requests (require `TMDB_API_KEY` in environment). Skip tests when `TMDB_API_KEY` is not set.
  - Verify `poster.jpg`/`seasonXX-poster.jpg` and `logo.jpg` (or `.jpeg`/`.png`) are written and contain the embedded marker with the expected `file_path` and language.

Quality gates

- Run `scripts/lint.sh` and `scripts/run-unit-tests.sh` and `scripts/run-integration-tests.sh`.
- Fix any lint or type issues. Use Black line length 88 and Ruff for linting. Ensure Mypy passes for changed files.

Implementation steps (developer-friendly)

1. Implement `Translator.select_best_image` (posters and logos) returning single simplified ImageCandidate or None. Keep selection by strict lang-country preference; return only `{ file_path, iso_639_1, iso_3166_1 }`.
2. Add `src/sonarr_metadata_rewrite/image_utils.py` with read/embed helpers and an in-memory `embed_marker_and_atomic_write` using Pillow (and `piexif` for JPEG when available).
3. Add `src/sonarr_metadata_rewrite/image_processor.py` orchestrating: resolve TMDB IDs from NFO, select candidate, download-to-memory, embed-in-memory, atomic replace, backup old image, and return structured `ImageProcessResult`.
4. Update `rewrite_service.py` to orchestrate both metadata and image paths; remove image responsibilities from `metadata_processor.py`.
5. Refactor results: introduce `ProcessResult` (base), `MetadataProcessResult`, and `ImageProcessResult`. Align `ImageProcessor.process(image_path)` and `MetadataProcessor.process(nfo_path)` to return their respective results.
6. Extend `rollback_service.py` to restore backed-up images alongside `.nfo` files.
7. Add unit tests and run test suite. Fix any failures.
8. Add integration tests (no HTTP mocking) and run them (skip if `TMDB_API_KEY` is not set).
9. Update README and CLAUDE.md to document behavior and config.

Open questions / assumptions

- Assumption: TMDB base image URL is available in config or translator currently has knowledge of base images URL pattern; translator will return complete `file_path` and caller will use TMDB image base (e.g., `https://image.tmdb.org/t/p/original`) from translator or config.
- Assumption: `piexif` may not currently be in `pyproject.toml`; if not present add it and follow repo policy for pinned dependencies.
- Assumption: Season-level logos are not available from TMDB; initial implementation supports logos only at the series level.
- Assumption: Only `.jpg`, `.jpeg`, and `.png` image extensions are supported.

Rollback strategy

- The rewrite operation is reversible by Sonarr or users; our operations are atomic and create no sidecars.
- For images (including logo), before overwriting, create a backup using the same backup/restore mechanism as `.nfo` files. On rollback, restore the previous image from backup, handling extension differences (e.g., restoring `logo.png` if `logo.jpg` was replaced). Remove backup after successful restore or per retention policy.
- Existing `rollback_service` should be extended to support image files alongside `.nfo` files.

Security and privacy

- Do not embed secrets or API keys into files. The embedded marker contains only TMDB `file_path`, `tmdb_tv_id`, optional `tmdb_season_number`, and language/country codes.

Notes

- Keep changes minimal and well-tested. Follow existing repository patterns for logging, retry, and caching.

Result types

- Refactor `ProcessResult` into:
  - `ProcessResult` (base):
    - success: bool
    - file_path: Path
    - message: str
    - exception: Exception | None
    - backup_created: bool
    - file_modified: bool
  - `MetadataProcessResult(ProcessResult)`:
    - tmdb_ids: TmdbIds | None
    - translated_content: TranslatedContent | None
  - `ImageProcessResult(ProcessResult)`:
    - kind: Literal["poster","logo"]
    - selected_language: str
    - selected_file_path: str

## Multi-step Execution Plan

This section outlines the recommended step-by-step implementation sequence for the image rewrite feature. Each step should be completed and validated before moving to the next.

- [ ] Refactor result types
  - [ ] Refactor `ProcessResult` into base, `MetadataProcessResult`, and `ImageProcessResult` in `models.py`.
  - [ ] Update all usages and tests to use the new result types.

- [ ] Implement ImageCandidate and marker schema
  - [ ] Define `ImageCandidate` dataclass with fields: `file_path`, `iso_639_1`, `iso_3166_1`.
  - [ ] Update marker embedding/reading logic to use these fields.

- [ ] Update image selection logic
  - [ ] Implement strict lang-country matching in `Translator.select_best_image`.
  - [ ] Remove vote-based tie-breakers; select first candidate per preference.

- [ ] Implement image utils
  - [ ] Add `embed_marker_and_atomic_write` and `read_embedded_marker` in `image_utils.py` using Pillow/piexif.
  - [ ] Ensure marker is embedded in-memory before atomic write.

- [ ] Implement ImageProcessor
  - [ ] Implement `ImageProcessor.process(image_path)`:
    - [ ] Resolve TMDB IDs from NFO.
    - [ ] Select candidate and download image to memory.
    - [ ] Embed marker and write atomically.
    - [ ] Normalize extension and handle mismatches.
    - [ ] Create backup before replace.
    - [ ] Return `ImageProcessResult`.

- [ ] Update RewriteService orchestration
  - [ ] Refactor to call `ImageProcessor` directly for images and `MetadataProcessor` for NFOs.
  - [ ] Aggregate results and logging.

- [ ] Extend rollback_service for images
  - [ ] Add support for restoring image backups, including extension differences.
  - [ ] Integrate with existing NFO rollback logic.

- [ ] Update scanning and filtering logic
  - [ ] Ensure all .jpg/.jpeg/.png files are scanned.
  - [ ] Filter to poster/logo patterns and normalize destination filenames.

- [ ] Add and update tests
  - [ ] Update unit tests for selection, embedding, and processor logic.
  - [ ] Add integration tests (no HTTP mocking) for end-to-end flow; skip if TMDB_API_KEY is not set.

- [ ] Update documentation
  - [ ] Update README and CLAUDE.md to reflect new image rewrite behavior, config, and rollback.

Change log

- Created: 2025-10-26 by developer assistant
- Updated: 2025-10-27 by developer assistant
