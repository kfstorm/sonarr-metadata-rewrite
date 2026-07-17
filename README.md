# Sonarr Metadata Rewrite

![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/kfstorm/2eafe27677e3a2ebbda29cbd026ff32b/raw/coverage.json)
[![CI](https://github.com/kfstorm/sonarr-metadata-rewrite/actions/workflows/ci.yml/badge.svg)](https://github.com/kfstorm/sonarr-metadata-rewrite/actions/workflows/ci.yml)

Sonarr only generates English metadata. Radarr can generate movie metadata in
one configured language, but it cannot make artwork follow that language and
does not support an ordered language fallback. This tool watches Sonarr TV and
Radarr movie `.nfo` files, then applies your preferred language list in order.
It rewrites poster and clearlogo images to language-specific variants when
available (e.g., `poster.jpg`, `clearlogo.png`, `season01-poster.jpg`).

The same Radarr artwork gap is described in [localized poster issue #9863](
https://github.com/Radarr/Radarr/issues/9863), [translated images issue #5277](
https://github.com/Radarr/Radarr/issues/5277), and [metadata artwork language
issue #8025](https://github.com/Radarr/Radarr/issues/8025).

It also addresses [Sonarr Issue #269](
https://github.com/Sonarr/Sonarr/issues/269) and
[Sonarr Issue #6663](https://github.com/Sonarr/Sonarr/issues/6663)
. It turns out a lot of people want
their media metadata in their native language, but Sonarr doesn't support this
natively.

## What it does

The tool runs as a background service that:

- Watches your media folders for when Sonarr or Radarr creates or updates `.nfo`
  files
- Grabs the TMDB ID from those files and fetches translations from TMDB's API
- Applies preferred languages in order, falling back when a title, plot, or
  image is unavailable in a higher-priority language
- Rewrites poster and clearlogo images based on your preferred language-country
  codes (e.g., `en-US`, `ja-JP`) when such variants exist on TMDB
- Does this fast enough that you barely notice it happening
- Keeps backups of the original files in case you want them back
- Caches everything so it doesn't spam TMDB's API

You can configure multiple languages with fallback priority, such as Chinese
first and Japanese second. Metadata fields may use different fallback languages
when TMDB has only a title or plot in the higher-priority language.

## Installation

You'll need Docker and a **TMDB API Read Access Token** from
[themoviedb.org](https://www.themoviedb.org/settings/api).

⚠️ **Important**: This application requires an **API Read Access Token**, NOT an
"API Key". Get your API Read Access Token from the
[TMDB API settings page](https://www.themoviedb.org/settings/api)
under the "API Read Access Token" section. Learn more about authentication at
the [TMDB Authentication Guide](https://developer.themoviedb.org/docs/authentication-application).

**Docker (recommended):**

Create a configuration file:

```dotenv
TMDB_API_KEY=your_api_read_access_token_here
REWRITE_ROOT_DIRS=/tv,/anime
PREFERRED_LANGUAGES=zh-CN,ja-JP
```

```bash
docker run -d \
  --name sonarr-metadata-rewrite \
  --user $(id -u):$(id -g) \
  --env-file /path/to/sonarr-metadata-rewrite.env \
  -v /path/to/tv/shows:/tv \
  -v /path/to/anime:/anime \
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
    user: "${UID:-1000}:${GID:-1000}"
    env_file:
      - /path/to/sonarr-metadata-rewrite.env
    volumes:
      - /path/to/tv/shows:/tv
      - /path/to/anime:/anime
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
TMDB_API_KEY=your_api_read_access_token_here  # Your TMDB API Read Access Token
# One or more media directories (comma-separated) to watch for
# Sonarr/Radarr NFO files
REWRITE_ROOT_DIRS=/tv,/anime
# Comma-separated language codes in priority order
PREFERRED_LANGUAGES=zh-CN,ja-JP
```

`REWRITE_ROOT_DIR` (singular, one path) is also accepted for backward
compatibility. `REWRITE_ROOT_DIRS` takes priority when both are set.

### Optional Settings (with defaults)

```bash
# Scanning & Monitoring
PERIODIC_SCAN_INTERVAL_SECONDS=86400  # How often to scan directory (default: daily)
ENABLE_FILE_MONITOR=true              # Real-time file monitoring (default: true)
ENABLE_FILE_SCANNER=true              # Periodic directory scanning (default: true)

# NFO & Images
ENABLE_NFO_REWRITE=true               # Translate NFO files (default: true)
ENABLE_IMAGE_REWRITE=true             # Rewrite posters/clearlogos (default: true)

# Caching & Storage
CACHE_DURATION_HOURS=720              # Cache translations (default: 30 days)
CACHE_DIR=./cache                     # Cache directory (default: ./cache)

# TMDB API Rate Limiting
TMDB_MAX_RETRIES=3                    # Max retry attempts (default: 3)
TMDB_INITIAL_RETRY_DELAY=1.0          # Initial retry delay (default: 1.0)
TMDB_MAX_RETRY_DELAY=60.0             # Max retry delay (default: 60.0)

# Backup
ORIGINAL_FILES_BACKUP_DIR=./backups   # Backup original files (default: ./backups)
                                      # Applies to both .nfo and images. Set to
                                      # empty string to disable backups.
                                      # Files are stored under their full absolute
                                      # path (e.g. /app/backups/tv/Show/tvshow.nfo)
                                      # so backups from different root dirs never
                                      # collide.
                                      # Backups created by older single-root-dir
                                      # versions are still found and restored
                                      # automatically (backward compatible).

# Service Mode
SERVICE_MODE=rewrite                  # Service mode: 'rewrite' or 'rollback'
                                      # (default: rewrite)
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

### Which images are rewritten?

If image rewriting is enabled, the service recognizes these filenames:

- TV series-level: `poster.*`, `clearlogo.*`
- Season-level: `seasonNN-poster.*` (e.g., `season01-poster.jpg`)
- Specials: `season-specials-poster.*`
- Movie-level: `poster.*`, `clearlogo.*`

Current Radarr Kodi/Emby metadata generation creates movie posters but not
clearlogos. Existing `clearlogo.*` files in movie directories are still
rewritten when a matching TMDB image is available.

Supported extensions: `.jpg`, `.jpeg`, `.png`.

When rewriting, the tool selects the first TMDB image that exactly matches your
preferred language-country codes in order. It then writes the image atomically,
embeds a small JSON marker in the image metadata indicating the TMDB file path
and language, and normalizes the extension to match TMDB while preserving the
original filename stem. If the existing image already matches the selected
candidate (based on the embedded marker), it is skipped to avoid unnecessary
writes.

### File Permissions (Important!)

The `--user` parameter in the Docker examples above is **critical** for
maintaining proper file permissions. Here's why:

- Without `--user`, Docker runs the container as root by default
- Files created by the container (rewritten .nfo files, cache, backups) will be
  owned by root
- This can cause permission issues when trying to access files from your host system
- Sonarr or other applications may not be able to read the rewritten files

**For Docker run:**

```bash
--user $(id -u):$(id -g)
```

This automatically uses your current user's UID and GID.

**For Docker Compose:**

```yaml
user: "${UID:-1000}:${GID:-1000}"
```

Set the UID and GID environment variables first:

```bash
export UID=$(id -u)
export GID=$(id -g)
docker compose up -d
```

**To check your user ID:**

```bash
id -u  # Shows your user ID (UID)
id -g  # Shows your group ID (GID)
```

### Highly Recommended Volume Mappings

While only the media directories are strictly required, these volumes will
improve your experience:

```bash
# Media directories (required - mount each root dir separately)
-v /path/to/your/tv/shows:/tv
-v /path/to/your/anime:/anime

# Cache directory (highly recommended - persists translation cache across
# container restarts)
-v sonarr-metadata-cache:/app/cache

# Backup directory (highly recommended - keeps original .nfo and image files safe)
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
🚀 Starting Sonarr and Radarr Metadata Rewrite...
✅ TMDB API key loaded (ending in ...xyz)
📁 Monitoring directory: /tv
📁 Monitoring directory: /anime
🌍 Preferred languages: ['zh-CN', 'ja-JP']
✅ Service started successfully
```

The container runs in the background. When Sonarr updates TV shows or Radarr
updates movies, it automatically translates their metadata files.

To stop the container:

```bash
docker stop sonarr-metadata-rewrite
```

## How it works

The service has a few main parts:

**File monitoring** - Uses Python's `watchdog` to watch for file changes
(.nfo and image files) in real-time

**TMDB integration** - Extracts TMDB IDs from Sonarr and Radarr XML files and
fetches translations via their API

**Smart caching** - Stores translations locally so it doesn't hit the API
repeatedly for the same content

**Batch processing** - Also scans your existing files periodically to catch
anything it might have missed (both .nfo and image files)

**Safe file handling** - Does atomic writes, embeds tiny markers in images to
avoid reprocessing, and keeps backups so you never lose data

The whole thing is designed to be invisible - just set it up once and forget
about it.

## Restoring originals (rollback)

If you want to restore Sonarr or Radarr original English metadata (and images),
use the built-in rollback functionality to automatically restore all original
files from backups.

### Automated Rollback (Recommended)

Set the service to rollback mode, which will restore all original files from backups:

**Docker:**

Use same configuration file as your running rewrite service:

```bash
docker run --rm \
  --user $(id -u):$(id -g) \
  -e SERVICE_MODE=rollback \
  --env-file /path/to/sonarr-metadata-rewrite.env \
  -v /path/to/tv/shows:/tv \
  -v /path/to/anime:/anime \
  -v sonarr-metadata-backups:/app/backups \
  kfstorm/sonarr-metadata-rewrite:latest
```

**Docker Compose:**

```yaml
# Temporarily change your docker-compose.yml
environment:
  - SERVICE_MODE=rollback
  # ... other environment variables
```

The rollback service will:
- Restore all original .nfo and image files from the backup directory
- Skip any shows/episodes that have been deleted
- Log the restoration progress
- Hang after completion (preventing restart loops)

**Important:** The service will hang after rollback completion to prevent
restart loops. Stop it manually when done:

```bash
docker stop sonarr-metadata-rewrite
```

## Development

Want to hack on this? Cool!

### Setup

```bash
git clone https://github.com/kfstorm/sonarr-metadata-rewrite.git
cd sonarr-metadata-rewrite
./scripts/setup-dev.sh
cat > .env <<'EOF'
TMDB_API_KEY=your_api_read_access_token_here
REWRITE_ROOT_DIRS=/path/to/tv/shows,/path/to/anime
PREFERRED_LANGUAGES=zh-CN,ja-JP
EOF
```

**Run tests:**

```bash
./scripts/run-unit-tests.sh          # Fast unit tests
./scripts/run-integration-tests.sh   # Slower integration tests (needs Docker)
./scripts/combine-coverage.sh        # Combine coverage reports
```

**Code quality:**

```bash
./scripts/lint.sh                    # Fix formatting and lint issues
./scripts/lint.sh --check            # Run quality checks without fixes
```

The codebase uses modern Python tooling - `uv` for dependencies, Ruff for
formatting and linting, MyPy for type checking. There are pre-commit hooks that
run all checks automatically.

## Troubleshooting

### Service won't start

- Check that your TMDB API Read Access Token is valid (see authentication
  section above)
- Make sure the media directory exists and is readable
- Look at the error messages, they're usually pretty helpful

### Authentication errors (401 Unauthorized)

If you see "401 Unauthorized" errors:

- **Most common cause**: You're using an "API Key" instead of an
  "API Read Access Token"
- **Solution**: Get the correct "API Read Access Token" from
  [TMDB API settings](https://www.themoviedb.org/settings/api)
- **How to tell**: API Read Access Tokens are much longer than API Keys
- **Reference**: [TMDB Authentication Guide](https://developer.themoviedb.org/docs/authentication-application)

### Files aren't getting translated

- Verify your `.nfo` files actually contain TMDB IDs (look for
  `<uniqueid type="tmdb">123456</uniqueid>`)
- Check that TMDB has translations in your preferred language for that content
- Make sure Sonarr is actually writing new `.nfo` files (try refreshing a series)

### File permission issues

If you're seeing permission denied errors or files owned by root:

- Make sure you're using the `--user` parameter in your Docker command
- For existing containers, stop and recreate with the proper `--user` setting
- Check file ownership: `ls -la /path/to/your/tv/shows/`
- Files should be owned by your user, not root

**Fix for existing root-owned files:**

```bash
# Stop the container first
docker stop sonarr-metadata-rewrite

# Fix ownership (replace with your actual path and user)
sudo chown -R $(id -u):$(id -g) /path/to/your/tv/shows/

# Restart with proper --user parameter
```

### API rate limits

- TMDB has rate limits, and the service includes automatic retry logic with
  exponential backoff
- Most requests are cached, so they only happen once per series/episode
- If you have a huge library, the service will automatically handle rate
  limits and pace itself
- You can configure retry behavior with `TMDB_MAX_RETRIES`,
  `TMDB_INITIAL_RETRY_DELAY`, and `TMDB_MAX_RETRY_DELAY` settings

## License

MIT License - do whatever you want with it.

---

This project scratches my own itch of wanting Chinese metadata for my media
library. If it helps you too, that's awesome! Feel free to contribute or
report issues.
