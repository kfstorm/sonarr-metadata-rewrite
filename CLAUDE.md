# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sonarr Metadata Translation Layer - A compatibility layer that monitors Sonarr-generated .nfo files and overwrites them with TMDB translations in desired languages. This addresses [Sonarr Issue #269](https://github.com/Sonarr/Sonarr/issues/269) which requests multilingual metadata support.

The project includes a fully functional metadata translation service with real-time file monitoring, TMDB API integration, caching, and comprehensive error handling.

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

### Application Usage
```bash
# Run the translation service
uv run sonarr-metadata-rewrite

# Check version
uv run sonarr-metadata-rewrite --version

# Example with all optional settings
REWRITE_ROOT_DIR=/home/user/media \
PREFERRED_LANGUAGES='zh-CN,ja-JP' \
CACHE_DURATION_HOURS=720 \
PERIODIC_SCAN_INTERVAL_SECONDS=3600 \
uv run sonarr-metadata-rewrite
```

## Technical Architecture

### Current Implementation
Complete metadata translation service with Click framework providing:
- Entry point: `sonarr_metadata_rewrite.main:cli` command that runs a persistent service (CLI: `sonarr-metadata-rewrite`)
- Real-time file monitoring with watchdog for immediate translation
- Periodic directory scanning for batch processing of existing files
- TMDB API integration with caching and rate limiting
- Pydantic-based configuration with comprehensive settings validation
- Atomic file operations with optional backup functionality
- Project structure follows Python package standards with src/ layout

### Core Components
1. **CLI Interface** (`main.py`)
   - Click-based command that runs a persistent service
   - Comprehensive configuration validation on startup
   - Signal handlers for graceful shutdown
   - Error handling with proper exit codes

2. **RewriteService** (`rewrite_service.py`)
   - Main orchestrator coordinating all metadata translation components
   - Manages file monitoring, scanning, and processing lifecycle
   - Handles service startup/shutdown and resource cleanup

3. **MetadataProcessor** (`metadata_processor.py`)
   - Complete .nfo file processing workflow
   - TMDB ID extraction from XML files
   - Translation selection based on language preferences
   - Atomic file writes with optional backup creation

4. **Translator** (`translator.py`)
   - TMDB API client with httpx for reliable HTTP requests
   - Translation caching with diskcache for performance
   - Rate limiting compliance and error handling
   - Support for both series and episode translations

5. **FileMonitor** (`file_monitor.py`)
   - Real-time file system monitoring using watchdog
   - Immediate processing of .nfo file creation/modification events
   - Recursive directory watching with event filtering

6. **FileScanner** (`file_scanner.py`)
   - Periodic directory scanning for batch processing
   - Configurable scan intervals for existing file processing
   - Thread-based background scanning with graceful shutdown

7. **Configuration** (`config.py`)
   - Pydantic Settings-based configuration management
   - Environment variable loading with .env file support
   - Comprehensive validation for all required settings

8. **Data Models** (`models.py`)
   - TmdbIds: TMDB identifier structures for series/episodes
   - TranslatedContent: Translated metadata containers
   - ProcessResult: Processing outcome tracking

### TMDB API Integration Design
- **Target Endpoints**: `/tv/{series_id}/translations` and `/tv/{series_id}/season/{season_number}/episode/{episode_number}/translations`
- **Rate Limits**: 40 requests per 10 seconds per IP address
- **Language Codes**: ISO 639-1 format with optional country codes (e.g., "zh-CN", "ja-JP")
- **ID Extraction**: TMDB IDs from `<uniqueid type="tmdb">` XML tags in .nfo files

### Development Tooling
- **Package Manager**: uv with pyproject.toml dependency management
- **Code Quality**: Black (line-length: 88), Ruff (E/W/F/I/B/C4/UP rules), MyPy (strict typing) with Pydantic plugin
- **Architecture**: Tach module dependency enforcement with tach.toml for 8 modules
- **Testing**: pytest with coverage, separate unit/integration test directories
- **Dead Code**: Vulture with whitelist support
- **Automation**: pre-commit hooks for all quality checks

### File Structure
```
src/sonarr_metadata_rewrite/
├── __init__.py (version definition)
├── main.py (CLI entry point)
├── config.py (Pydantic settings configuration)
├── models.py (data structures)
├── translator.py (TMDB API client)
├── metadata_processor.py (file processing workflow)
├── file_monitor.py (real-time monitoring)
├── file_scanner.py (periodic scanning)
└── rewrite_service.py (service orchestrator)
tests/
├── unit/ (fast unit tests for all modules)
├── integration/ (TMDB API tests)
└── conftest.py (shared test fixtures)
scripts/ (development automation)
```

### Key Technical Constraints
- **Python**: >=3.10 with strict typing enforcement
- **Dependencies**: Core runtime deps (Click, Pydantic, httpx, watchdog, diskcache)
- **TMDB Rate Limits**: ~50 requests/second (not fixed, subject to change) - addressed with caching
- **File Format**: Sonarr generates XML .nfo files with TMDB IDs
- **Target Files**: `tvshow.nfo` (series) and episode-specific .nfo files
- **Service Architecture**: Long-running daemon process with graceful shutdown support
