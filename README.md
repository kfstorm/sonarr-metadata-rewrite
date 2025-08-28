# Sonarr Metadata Rewrite

![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/kfstorm/2eafe27677e3a2ebbda29cbd026ff32b/raw/coverage.json)
[![CI](https://github.com/kfstorm/sonarr-metadata-rewrite/actions/workflows/ci.yml/badge.svg)](https://github.com/kfstorm/sonarr-metadata-rewrite/actions/workflows/ci.yml)

Ever been frustrated that Sonarr only gives you English metadata for your TV
shows? This tool fixes that by watching for Sonarr's `.nfo` files and
automatically replacing them with translations in whatever language you prefer.

It's my solution to [Sonarr Issue #269](
https://github.com/Sonarr/Sonarr/issues/269) - turns out a lot of people want
their media metadata in their native language, but Sonarr doesn't support this
natively.

## What it does

The tool runs as a background service that:

- Watches your media folders for when Sonarr creates or updates `.nfo` files
- Grabs the TMDB ID from those files and fetches translations from TMDB's API
- Replaces the English metadata with your preferred language(s)
- Does this fast enough that you barely notice it happening
- Keeps backups of the original files in case you want them back
- Caches everything so it doesn't spam TMDB's API

You can configure multiple languages with fallback priority - like Chinese
first, then Japanese, then just leave it in English if neither is available.

## Installation

You'll need Docker and a free TMDB API key from
[themoviedb.org](https://www.themoviedb.org/settings/api).

**Docker (recommended):**

```bash
docker run -d \
  --name sonarr-metadata-rewrite \
  -e TMDB_API_KEY=your_api_key_here \
  -e REWRITE_ROOT_DIR=/media \
  -e PREFERRED_LANGUAGES=zh-CN,ja-JP \
  -v /path/to/your/tv/shows:/media \
  -v sonarr-metadata-cache:/app/cache \
  -v sonarr-metadata-backups:/app/backups \
  --restart unless-stopped \
  kfstorm/sonarr-metadata-rewrite:latest
```

**Docker Compose:**

```yaml
version: '3.8'
services:
  sonarr-metadata-rewrite:
    image: kfstorm/sonarr-metadata-rewrite:latest
    container_name: sonarr-metadata-rewrite
    environment:
      - TMDB_API_KEY=your_api_key_here
      - REWRITE_ROOT_DIR=/media
      - PREFERRED_LANGUAGES=zh-CN,ja-JP
      # Optional: customize cache duration (default: 30 days)
      # - CACHE_DURATION_HOURS=168
    volumes:
      - /path/to/your/tv/shows:/media
      - sonarr-metadata-cache:/app/cache
      - sonarr-metadata-backups:/app/backups
    restart: unless-stopped

volumes:
  sonarr-metadata-cache:
  sonarr-metadata-backups:
```

## Configuration

### Required Settings

```bash
TMDB_API_KEY=your_api_key_here      # Your TMDB API key
REWRITE_ROOT_DIR=/media             # Path to your TV shows (inside container)
# Comma-separated language codes in priority order
PREFERRED_LANGUAGES=zh-CN,ja-JP
```

### Optional Settings (with defaults)

```bash
# Metadata Format Configuration
METADATA_FORMAT=auto                   # Metadata format detection (auto, kodi, emby)
                                      # auto: Automatically detect format from files
                                      # kodi: Force Kodi/XBMC format
                                      # emby: Force Emby format

# Scanning & Monitoring
PERIODIC_SCAN_INTERVAL_SECONDS=86400  # How often to scan directory (default: daily)
ENABLE_FILE_MONITOR=true              # Real-time file monitoring (default: true)
ENABLE_FILE_SCANNER=true              # Periodic directory scanning (default: true)

# Caching & Storage
CACHE_DURATION_HOURS=720              # Cache translations (default: 30 days)
CACHE_DIR=./cache                     # Cache directory (default: ./cache)

# Backup
ORIGINAL_FILES_BACKUP_DIR=./backups   # Backup original files (default: ./backups)
                                      # Set to empty string to disable backups
```

**Language codes** are ISO 639-1 format:
- `zh-CN` - Chinese (Simplified)
- `ja-JP` - Japanese
- `ko-KR` - Korean
- `fr-FR` - French
- `de-DE` - German
- `es-ES` - Spanish

You can list multiple languages separated by commas - it'll try them in
order.

### Highly Recommended Volume Mappings

While only the media directory is strictly required, these volumes will
improve your experience:

```bash
# Media directory (required)
-v /path/to/your/tv/shows:/media

# Cache directory (highly recommended - persists translation cache across
# container restarts)
-v sonarr-metadata-cache:/app/cache

# Backup directory (highly recommended - keeps original .nfo files safe)
-v sonarr-metadata-backups:/app/backups
```

Without these volumes, you'll lose cached translations and backups when the
container is recreated.

## Running it

The Docker container runs automatically once started. You can check the logs:

```bash
docker logs sonarr-metadata-rewrite
```

You'll see something like:

```text
🚀 Starting Sonarr Metadata Rewrite...
✅ TMDB API key loaded (ending in ...xyz)
📁 Monitoring directory: /media
🌍 Preferred languages: ['zh-CN', 'ja-JP']
✅ Service started successfully
```

The container runs in the background. When Sonarr updates your shows, this
will automatically translate the metadata files.

To stop the container:

```bash
docker stop sonarr-metadata-rewrite
```

## How it works

The service has a few main parts:

**File monitoring** - Uses Python's `watchdog` library to watch for file
changes in real-time

**TMDB integration** - Extracts TMDB IDs from Sonarr's XML files and
fetches translations via their API

**Smart caching** - Stores translations locally so it doesn't hit the API
repeatedly for the same content

**Batch processing** - Also scans your existing files periodically to catch
anything it might have missed

**Safe file handling** - Does atomic writes and keeps backups so you never
lose data

The whole thing is designed to be invisible - just set it up once and forget
about it.

## Going back to English

If you want to restore Sonarr's original English metadata:

**Important: Stop the container first!** Otherwise it'll just translate
everything again.

```bash
docker stop sonarr-metadata-rewrite
```

### Steps to restore English metadata

1. Delete the translated .nfo files from your TV show directories
2. Go to Sonarr > Series > Update All
3. Sonarr will regenerate the original English .nfo files

NOTE: Restoring backups are not implemented yet.

## Development

Want to hack on this? Cool!

### Setup

```bash
git clone https://github.com/kfstorm/sonarr-metadata-rewrite.git
cd sonarr-metadata-rewrite
./scripts/setup-dev.sh
echo "TMDB_API_KEY=your_key" > .env
```

**Run tests:**

```bash
./scripts/run-unit-tests.sh          # Fast unit tests
./scripts/run-integration-tests.sh   # Slower integration tests (needs Docker)
./scripts/combine-coverage.sh        # Combine coverage reports
```

**Code quality:**

```bash
./scripts/lint.sh                    # Fix formatting and imports
./scripts/lint.sh --check            # Just check, don't fix
```

The codebase uses modern Python tooling - `uv` for dependencies, Black for
formatting, Ruff for linting, MyPy for type checking. There are pre-commit
hooks that run all the checks automatically.

## Troubleshooting

### Service won't start

- Check that your TMDB API key is valid
- Make sure the media directory exists and is readable
- Look at the error messages, they're usually pretty helpful

### Files aren't getting translated

- Verify your `.nfo` files actually contain TMDB IDs (look for
  `<uniqueid type="tmdb">123456</uniqueid>`)
- Check that TMDB has translations in your preferred language for that content
- Make sure Sonarr is actually writing new `.nfo` files (try refreshing a series)

### Worried about API limits

- TMDB has rate limits, but the caching means most requests only happen once
  per series/episode
- If you have a huge library, just let it run overnight - it'll pace itself naturally
- Rate limiting isn't implemented yet, so be mindful if processing thousands
  of files at once

## License

MIT License - do whatever you want with it.

---

This project scratches my own itch of wanting Chinese metadata for my media
library. If it helps you too, that's awesome! Feel free to contribute or
report issues.
