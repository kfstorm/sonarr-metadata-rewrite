# sonarr-metadata-rewrite

![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/kfstorm/2eafe27677e3a2ebbda29cbd026ff32b/raw/coverage.json)
[![CI](https://github.com/kfstorm/sonarr-metadata-rewrite/actions/workflows/ci.yml/badge.svg)](https://github.com/kfstorm/sonarr-metadata-rewrite/actions/workflows/ci.yml)

Monitors Sonarr-generated .nfo files and overwrites them with TMDB translations in desired languages.

## Installation and Usage

### Direct Installation

```bash
# Install with uv
uv tool install sonarr-metadata-rewrite

# Or install with pip
pip install sonarr-metadata-rewrite
```

### Docker Usage

To avoid file permission issues when running in a container, always specify the appropriate user and group IDs that match your media file ownership:

#### Docker Run
```bash
# Get your user and group ID
id

# Run with proper user permissions
docker run -d \
  --name sonarr-metadata-rewrite \
  --user $(id -u):$(id -g) \
  -v /path/to/your/tv/shows:/tv \
  -v /path/to/config:/config \
  -e TMDB_API_KEY=your_api_key_here \
  -e REWRITE_ROOT_DIR=/tv \
  -e PREFERRED_LANGUAGES=zh-CN,ja-JP \
  sonarr-metadata-rewrite
```

#### Docker Compose
```yaml
version: '3.8'
services:
  sonarr-metadata-rewrite:
    image: sonarr-metadata-rewrite
    container_name: sonarr-metadata-rewrite
    user: "1000:1000"  # Replace with your actual UID:GID
    environment:
      - TMDB_API_KEY=your_api_key_here
      - REWRITE_ROOT_DIR=/tv
      - PREFERRED_LANGUAGES=zh-CN,ja-JP
      - CACHE_DURATION_HOURS=720
      - PERIODIC_SCAN_INTERVAL_SECONDS=86400
    volumes:
      - /path/to/your/tv/shows:/tv
      - /path/to/config:/config
    restart: unless-stopped
```

**Important**: 
- Replace `1000:1000` with your actual user and group ID (run `id` to find them)
- The user ID should match the owner of your media files to ensure proper permissions
- Without proper `--user` specification, the container may create files with root ownership

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TMDB_API_KEY` | *required* | Your TMDB API key |
| `REWRITE_ROOT_DIR` | `/tv` | Root directory to monitor for .nfo files |
| `PREFERRED_LANGUAGES` | `en-US` | Comma-separated list of language codes (e.g., `zh-CN,ja-JP`) |
| `CACHE_DURATION_HOURS` | `720` | How long to cache translations (30 days) |
| `PERIODIC_SCAN_INTERVAL_SECONDS` | `86400` | How often to scan for existing files (24 hours) |

## Rollback to Original Metadata

If you want to restore the original English metadata from Sonarr:

### Method 1: Using Sonarr UI
1. **Stop the translation service**
2. **Delete translated .nfo files** from your series directories
3. **Go to Sonarr > Series > [Select Series] > Refresh Series**
4. Sonarr will regenerate original English .nfo files

### Method 2: Using Command Line
```bash
# Stop the service first
# Then delete .nfo files and refresh via API
curl -X POST "http://localhost:8989/api/v3/command" \
  -H "X-Api-Key: YOUR_SONARR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "RefreshSeries", "seriesId": SERIES_ID}'
```

### Method 3: Bulk Rollback Script
```bash
#!/bin/bash
# Example script to rollback all series
MEDIA_ROOT="/path/to/your/media"
SONARR_URL="http://localhost:8989"
SONARR_API_KEY="your_api_key"

# Find and delete all .nfo files
find "$MEDIA_ROOT" -name "*.nfo" -delete

# Trigger refresh for all series
curl -X POST "$SONARR_URL/api/v3/command" \
  -H "X-Api-Key: $SONARR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "RefreshSeries"}'
```

**Important**: Always stop the translation service before performing rollback operations to prevent it from immediately retranslating the restored files.
