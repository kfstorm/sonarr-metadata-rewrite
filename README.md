# sonarr-metadata-rewrite

![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/kfstorm/2eafe27677e3a2ebbda29cbd026ff32b/raw/coverage.json)
[![CI](https://github.com/kfstorm/sonarr-metadata-rewrite/actions/workflows/ci.yml/badge.svg)](https://github.com/kfstorm/sonarr-metadata-rewrite/actions/workflows/ci.yml)

Monitors Sonarr-generated .nfo files and overwrites them with TMDB translations in desired languages.

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
