# Sample Emby Format Files

This directory contains sample .nfo files in Emby format to demonstrate the new multi-format support.

## Series Format (Emby with `<series>` root)

File: `sample_emby_series.nfo`
```xml
<?xml version="1.0" encoding="utf-8"?>
<series>
  <title>Breaking Bad</title>
  <overview>A high school chemistry teacher diagnosed with inoperable lung cancer turns to manufacturing and selling methamphetamine in order to secure his family's future.</overview>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <uniqueid type="imdb">tt0903747</uniqueid>
  <genre>Drama</genre>
  <genre>Crime</genre>
  <premiered>2008-01-20</premiered>
  <year>2008</year>
  <status>Ended</status>
  <mpaa>TV-MA</mpaa>
  <studio>AMC</studio>
  <runtime>47</runtime>
</series>
```

## Episode Format (Emby with `<episode>` root)

File: `sample_emby_episode.nfo`
```xml
<?xml version="1.0" encoding="utf-8"?>
<episode>
  <title>Pilot</title>
  <overview>Walter White, a struggling high school chemistry teacher, is diagnosed with advanced lung cancer. He turns to a life of crime, producing and selling methamphetamine with a former student, Jesse Pinkman, with the goal of securing his family's financial future before he dies.</overview>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <uniqueid type="imdb">tt0959621</uniqueid>
  <aired>2008-01-20</aired>
  <season>1</season>
  <episode>1</episode>
  <runtime>58</runtime>
  <director>Vince Gilligan</director>
  <writer>Vince Gilligan</writer>
  <mpaa>TV-MA</mpaa>
  <rating>8.2</rating>
  <votes>25487</votes>
</episode>
```

## Mixed Format (Kodi root with Emby elements)

File: `sample_mixed_format.nfo`
```xml
<?xml version="1.0" encoding="utf-8"?>
<tvshow>
  <title>Breaking Bad</title>
  <overview>This uses overview instead of plot, but with Kodi tvshow root</overview>
  <uniqueid type="tmdb" default="true">1396</uniqueid>
  <uniqueid type="imdb">tt0903747</uniqueid>
  <genre>Drama</genre>
  <genre>Crime</genre>
  <premiered>2008-01-20</premiered>
  <year>2008</year>
  <status>Ended</status>
</tvshow>
```

## Configuration Examples

### Auto-Detection (Default)
```bash
METADATA_FORMAT=auto
```
This will automatically detect whether files are Kodi or Emby format and handle them appropriately.

### Force Emby Format
```bash
METADATA_FORMAT=emby
```
This will treat all files as Emby format, supporting both `<overview>` and `<plot>` elements.

### Force Kodi Format
```bash
METADATA_FORMAT=kodi
```
This will treat all files as traditional Kodi format with `<title>` and `<plot>` elements.

## Key Differences

| Format | Root Elements | Description Element | Series ID Location |
|--------|---------------|-------------------|-------------------|
| Kodi | `<tvshow>`, `<episodedetails>` | `<plot>` | `<uniqueid type="tmdb">` |
| Emby | `<series>`, `<episode>` | `<overview>` (preferred), `<plot>` (fallback) | `<uniqueid type="tmdb">` |
| Mixed | Any combination | Both supported | `<uniqueid type="tmdb">` |

The new format system is designed to be fully backward compatible - existing Kodi setups will continue to work without any configuration changes.