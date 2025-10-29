# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## Project Overview

Sonarr Metadata Rewrite - A compatibility layer that monitors
Sonarr-generated .nfo files and overwrites them with TMDB translations in
desired languages, and rewrites poster/clearlogo images to language-specific
variants when available. This addresses [Sonarr Issue #269](
https://github.com/Sonarr/Sonarr/issues/269) which requests multilingual
metadata support.

The project includes a metadata translation service and an image rewrite
pipeline with real-time file monitoring, TMDB API integration, intelligent
caching, comprehensive error handling, and reprocessing avoidance.

## Essential Development Commands

### Setup and Environment

```bash
# Initial setup (installs dependencies and pre-commit hooks)
./scripts/setup-dev.sh

# Install project in development mode after dependencies change
uv sync --group dev

# Create .env file with required API key for development and testing
echo "TMDB_API_KEY=your_api_key_here" > .env
```

### Code Quality and Testing

```bash
# Run all linting checks and fixes
./scripts/lint.sh

# Run checks only (no auto-fixes)
./scripts/lint.sh --check

# Run unit tests with coverage
./scripts/run-unit-tests.sh

# Run integration tests
./scripts/run-integration-tests.sh

# Combine coverage from unit and integration tests
./scripts/combine-coverage.sh
```

### Development Usage

```bash
# Run in development mode (requires .env file with TMDB_API_KEY)
uv run sonarr-metadata-rewrite

# Check version
uv run sonarr-metadata-rewrite --version

# Run with custom settings for testing
REWRITE_ROOT_DIR=/tmp/test/media \
PREFERRED_LANGUAGES='zh-CN,ja-JP' \
CACHE_DURATION_HOURS=1 \
uv run sonarr-metadata-rewrite
```

## Technical Architecture

### Current Implementation

Metadata translation and image rewrite service with Click framework providing:

- Entry point: `sonarr_metadata_rewrite.main:cli` command that runs a
  persistent service (CLI: `sonarr-metadata-rewrite`)
- Real-time file monitoring with watchdog for immediate processing (.nfo and
  rewritable images)
- Periodic directory scanning for batch processing of existing files
- TMDB API integration with intelligent caching and exponential backoff retry
  for rate limit handling
- Reprocessing avoidance to prevent unnecessary file updates and API calls
- Pydantic-based configuration with comprehensive settings validation
- Atomic file operations with optional backup functionality
- Project structure follows Python package standards with src/ layout and
  _version.py

### Core Components

1. **CLI Interface** (`main.py`)
Click-based command that runs a persistent service. Performs comprehensive
configuration validation on startup, installs signal handlers for graceful
shutdown, starts the service synchronously, and uses proper exit codes on
failure.

1. **RewriteService** (`rewrite_service.py`)
Orchestrator coordinating metadata and image processing components. Manages
file monitoring, scanning, and processing lifecycle, and handles
startup/shutdown and resource cleanup.

1. **MetadataProcessor** (`metadata_processor.py`)
Complete .nfo file processing workflow: extract TMDB IDs from XML, select
translation based on language preferences, and write atomically with optional
backup creation.

1. **Translator** (`translator.py`)
TMDB API client using httpx with diskcache-backed caching and exponential
backoff for HTTP 429. Supports series and episode translations. For images,
fetches `/tv/{id}/images` or `/tv/{id}/season/{s}/images`, filters locally for
preferred language-country (e.g., `en-US`) and chooses the first exact match;
does not pass `include_image_language` due to TMDB API issues.

1. **FileMonitor** (`file_monitor.py`)
Real-time file system monitoring using watchdog. Processes .nfo and image files
on close/move events. Recursive directory watching.

1. **FileScanner** (`file_scanner.py`)
Periodic directory scanning for batch processing. Scans for both `.nfo` files
and rewritable images. Configurable scan intervals, thread-based background
scanning with graceful shutdown.

1. **Configuration** (`config.py`)
Pydantic Settings-based configuration with custom env source parsing
`PREFERRED_LANGUAGES` as a comma-separated string (not JSON) into `list[str]`.
Includes `ENABLE_IMAGE_REWRITE` flag (default: true). Loads from .env and
performs comprehensive validation.

1. **Data Models** (`models.py`)
TmdbIds: TMDB identifier structures for series/episodes. TranslatedContent:
Translated metadata containers. ProcessResult: base outcome. MetadataProcessResult:
NFO-specific. ImageCandidate: TMDB image candidate (file_path, iso_639_1,
iso_3166_1). ImageProcessResult: image-specific outcome.

1. **Version Management** (`_version.py`)
Hatch-generated version file from VCS tags with dynamic version handling and
development fallback.

### TMDB API Integration Design

- **Text endpoints**: `/tv/{series_id}/translations` and
  `/tv/{series_id}/season/{season_number}/episode/{episode_number}/translations`
- **Image endpoints**: `/tv/{series_id}/images` and `/tv/{series_id}/season/{season_number}/images`
  - Don’t pass `include_image_language`; fetch all and filter client-side in
    code due to TMDB API quirk
- **Rate Limits**: TMDB has rate limits, and explicit rate limiting with
  exponential backoff retry is implemented to handle HTTP 429 responses
- **Language Codes**: ISO 639-1 format with optional country codes (e.g.,
  "zh-CN", "ja-JP")
- **ID Extraction**: TMDB IDs from `<uniqueid type="tmdb">` XML tags in
  .nfo files

### Development Tooling

- **Package Manager**: uv with pyproject.toml dependency management
- **Code Quality**: Black (line-length: 88), Ruff (E/W/F/I/B/C4/UP rules),
  MyPy (strict typing) with Pydantic plugin
- **Architecture**: Tach module dependency enforcement with tach.toml for
  module boundaries (including `_version`)
- **Testing**: pytest with coverage, separate unit/integration test
  directories with shared container infrastructure
- **Integration Testing**: Docker-based Sonarr integration with comprehensive
  test scenarios
- **Dead Code**: Vulture with whitelist support
- **Automation**: pre-commit hooks for all quality checks

### File Structure

```text
src/sonarr_metadata_rewrite/
├── __init__.py (version definition)
├── _version.py (generated version file)
├── main.py (CLI entry point)
├── config.py (Pydantic settings configuration)
├── models.py (data structures)
├── translator.py (TMDB API client)
├── metadata_processor.py (file processing workflow)
├── file_monitor.py (real-time monitoring)
├── file_scanner.py (periodic scanning)
├── image_utils.py (image metadata embed/read helpers)
├── image_processor.py (poster/clearlogo rewrite)
└── rewrite_service.py (service orchestrator)
tests/
├── unit/ (fast unit tests for all modules)
├── integration/ (comprehensive Sonarr integration tests with Docker)
│   └── fixtures/ (container management, series management, subprocess service)
└── conftest.py (shared test fixtures)
scripts/ (development automation)
```

### Image Rewriting Design

- Target filenames: `poster.*`, `clearlogo.*`, `seasonNN-poster.*`,
  `season-specials-poster.*` where extension is one of `.jpg`, `.jpeg`, `.png`
- TMDB base URL: `https://image.tmdb.org/t/p/original`; use candidate `file_path`
- Selection policy: match exact language-country in order of `preferred_languages`
- Reprocessing avoidance: embed marker with `file_path`, `iso_639_1`, `iso_3166_1`
  in PNG tEXt or JPEG EXIF UserComment; if marker matches current selection,
  skip writing
- Atomic writes: write to temp file and replace; normalize extension according
  to TMDB candidate while preserving original stem
- Backups: if `ORIGINAL_FILES_BACKUP_DIR` is set, copy original before rewrite
- Rollback: restores both `.nfo` and image files; removes conflicting ext variants

### Key Technical Constraints

- **Python**: >=3.10 with strict typing enforcement
- **Dependencies**: Core runtime deps (Click, Pydantic, httpx, watchdog,
  diskcache) plus Pillow and piexif for image processing
- **TMDB Rate Limits**: TMDB has rate limits, and explicit rate limiting with
  exponential backoff retry is implemented - the service automatically retries
  rate-limited requests with configurable delays
- **File Format**: Sonarr generates XML .nfo files with TMDB IDs
- **Target Files**: `tvshow.nfo` (series), episode-specific .nfo files, and
  image files matching the patterns above
- **Service Architecture**: Long-running daemon process with graceful
  shutdown support
- **Reprocessing Avoidance**: Implemented to prevent unnecessary API calls and
  file writes for both text and images
