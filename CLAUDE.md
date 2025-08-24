# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sonarr Metadata Translation Layer - A compatibility layer that monitors Sonarr-generated .nfo files and overwrites them with TMDB translations in desired languages. This addresses [Sonarr Issue #269](https://github.com/Sonarr/Sonarr/issues/269) which requests multilingual metadata support.

The project is currently in Phase 1 (Project Foundation) with basic CLI structure and comprehensive development tooling in place.

## Essential Development Commands

### Setup and Environment
```bash
# Initial setup (installs dependencies and pre-commit hooks)
./scripts/setup-dev.sh

# Install project in development mode after dependencies change
uv sync --group dev
```

### Code Quality and Testing
```bash
# Run all linting checks and fixes
./scripts/lint.sh

# Run checks only (no auto-fixes)
./scripts/lint.sh --check

# Run unit tests with coverage
./scripts/run-unit-tests.sh

# Run integration tests (requires TMDB_API_KEY environment variable)
TMDB_API_KEY=your_key ./scripts/run-integration-tests.sh

# Combine coverage from unit and integration tests
./scripts/combine-coverage.sh
```

### Application Usage
```bash
# Run the CLI tool (currently validates TMDB API key only)
TMDB_API_KEY=your_key uv run sonarr-metadata

# Or install and run globally
uv sync && uv run sonarr-metadata --version
```

## Technical Architecture

### Current Implementation
Minimal CLI application with Click framework providing:
- Entry point: `sonarr_metadata.main:cli` command
- Configuration: Environment-based TMDB API key validation
- Project structure follows Python package standards with src/ layout

### Core Components
1. **CLI Interface** (`main.py`)
   - Click-based command with version option
   - TMDB API key validation on startup
   - Error handling with proper exit codes

2. **Configuration** (`config.py`)
   - `get_tmdb_api_key()` function reads `TMDB_API_KEY` environment variable
   - Raises `ValueError` for missing configuration

### TMDB API Integration Design
- **Target Endpoints**: `/tv/{series_id}/translations` and `/tv/{series_id}/season/{season_number}/episode/{episode_number}/translations`
- **Rate Limits**: 40 requests per 10 seconds per IP address
- **Language Codes**: ISO 639-1 format with optional country codes (e.g., "zh-CN", "ja-JP")
- **ID Extraction**: TMDB IDs from `<uniqueid type="tmdb">` XML tags in .nfo files

### Development Tooling
- **Package Manager**: uv with pyproject.toml dependency management
- **Code Quality**: Black (line-length: 88), Ruff (E/W/F/I/B/C4/UP rules), MyPy (strict typing)
- **Architecture**: Tach module dependency enforcement with tach.toml
- **Testing**: pytest with coverage, separate unit/integration test directories
- **Dead Code**: Vulture with whitelist support
- **Automation**: pre-commit hooks for all quality checks

### File Structure
```
src/sonarr_metadata/
├── __init__.py (version definition)
├── main.py (CLI entry point)
└── config.py (environment configuration)
tests/
├── unit/ (fast unit tests)
└── integration/ (TMDB API tests)
scripts/ (development automation)
```

### Key Technical Constraints
- **Python**: >=3.10 with strict typing enforcement
- **Dependencies**: Minimal runtime deps (only Click currently)
- **TMDB Rate Limits**: ~50 requests/second (not fixed, subject to change) - critical for caching design
- **File Format**: Sonarr generates XML .nfo files with TMDB IDs
- **Target Files**: `tvshow.nfo` (series) and episode-specific .nfo files
