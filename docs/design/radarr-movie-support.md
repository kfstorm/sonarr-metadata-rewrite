# Radarr Movie Support Design

## Status

Accepted design. Implementation has not started.

## Goal

Extend the service to rewrite Radarr Kodi/Emby movie metadata and localized
movie artwork while preserving existing Sonarr TV behavior.

The service must support Radarr-generated movie NFO files in either supported
naming mode:

- `movie.nfo`
- `<VideoFileName>.nfo`

Movie artwork support is limited to Radarr's recognized short names:

- `poster.*`
- `clearlogo.*`

Supported extensions remain `.jpg`, `.jpeg`, and `.png`.

## Sources and Constraints

- Radarr's Kodi/Emby metadata root is `<movie>`.
- Radarr requires each managed movie to have its own directory. A flat
  multi-movie directory is not a supported Radarr library layout.
- Radarr writes `movie.nfo` when `UseMovieNfo` is enabled. Otherwise it writes
  `<VideoFileName>.nfo`.
- Radarr's current Kodi/Emby metadata provider generates short artwork names.
  In current Radarr releases, TMDB-provided movie covers generate `poster.*`
  and `fanart.*`; they do not generate `clearlogo.*`. The service still
  rewrites an existing movie `clearlogo.*` from another artwork source.
- Sonarr's Kodi/Emby metadata uses `<tvshow>` for series metadata and
  `<episodedetails>` for episode metadata. Sonarr does not generate season NFO
  files. Season artwork is identified by its filename and uses the parent TV
  show ID.
- Radarr movie NFO files are expected to contain a TMDB ID. Movie processing
  does not resolve missing TMDB IDs through IMDb or TVDB.

## Domain Model

`TmdbIds` becomes media-aware:

- `tmdb_id`: TMDB resource ID.
- `media_type`: `tv` or `movie`.
- `season` and `episode`: TV-only optional fields.

Resource paths:

| Media | Resource path |
| --- | --- |
| TV show | `tv/{tmdb_id}` |
| TV episode | `tv/{tmdb_id}/season/{season}/episode/{episode}` |
| Movie | `movie/{tmdb_id}` |

Movie identifiers must not contain season or episode values.

## Metadata Processing

All NFO files remain eligible for metadata processing. The XML root controls
the processing branch:

| Root | Behavior |
| --- | --- |
| `<tvshow>` | Existing series title and plot rewrite. |
| `<episodedetails>` | Episode rewrite; supports multi-episode NFO. |
| `<movie>` | New movie title and plot rewrite. |
| Other | Unsupported NFO result. |

Movie rewriting updates only `<title>` and `<plot>`. It must preserve
`<originaltitle>`, `<sorttitle>`, all identifiers, ratings, watched state, and
all other Radarr-generated XML.

For a movie NFO without a TMDB ID, processing stops without an external ID
lookup. This relies on Radarr's guaranteed TMDB ID and avoids matching a movie
to an incorrect TMDB resource.

Episode processing retains parent-series ID lookup. When an episode needs a
parent series ID, search at most three ancestor directories. At each directory,
inspect NFO contents and select a unique `<tvshow>` root NFO. Ignore movie,
episode, and unknown roots. No matching TV show continues the search; multiple
TV show roots make resolution fail.

Existing backup, original-content restoration, language fallback, atomic write,
and reprocessing-avoidance behavior applies to movies without changes.

## Translator Behavior

TV requests remain unchanged. Movie requests use TMDB movie resources:

| Operation | TV | Movie |
| --- | --- | --- |
| Translations | `/tv/{id}/translations` | `/movie/{id}/translations` |
| Original details | `/tv/{id}` | `/movie/{id}` |
| Images | `/tv/{id}/images` | `/movie/{id}/images` |

Translation parsing uses `data.name` for TV and `data.title` for movies. Both
use `data.overview` for plots. Original-title fallback uses `original_name` for
TV and `original_title` for movies.

The existing TV external-ID lookup remains TV-only. Movie processing does not
call it because a Radarr movie without a TMDB ID is skipped.

Image selection continues to fetch all image candidates and filter locally by
exact language-country preference order. It does not add
`include_image_language`, matching existing project behavior for TMDB image API
compatibility.

## Image Processing

Image handling uses one shared flow:

1. Parse a supported filename and determine artwork kind plus optional TV
   season number.
2. Inspect all NFO files in the image directory.
3. Keep only NFO files rooted at `<tvshow>` or `<movie>`; ignore
   `<episodedetails>` and unsupported roots.
4. Require exactly one retained root NFO. Zero or multiple candidates return a
   failure result and make no TMDB request or file write.
5. Use that root NFO's media type and TMDB ID to select an image.
6. Reuse existing marker comparison, backup creation/restoration, download,
   extension normalization, and atomic image write behavior.

This allows a Sonarr TV root directory to contain `tvshow.nfo` plus episode
NFO files without making series or season artwork ambiguous.

TV image behavior remains:

- `poster.*` and `clearlogo.*` use series images.
- `seasonNN-poster.*` and `season-specials-poster.*` use season images.
- Image NFO resolution is limited to the image directory. It does not search
  ancestors.

Movie image behavior:

- `poster.*` and `clearlogo.*` use movie images.
- Season poster filenames with a movie NFO are rejected.
- Long movie artwork names such as `<VideoFileName>-poster.*` and
  `<VideoFileName>-clearlogo.*` are ignored. Radarr currently recognizes such
  files but does not generate them through its Kodi/Emby metadata provider.

## Integration Test Design

Integration tests use a real Radarr container and real Radarr-generated NFO
and image files. Only the video file may be a test fixture. NFO files and
images must not be mocked or hand-authored.

The test matrix has four scenarios:

| NFO mode | File monitor | Periodic scanner |
| --- | --- | --- |
| `movie.nfo` | Test | Test |
| `<VideoFileName>.nfo` | Test | Test |

Every scenario verifies all of the following:

- Radarr produced the selected NFO naming mode and a `<movie>` document.
- Movie `<title>` and `<plot>` were rewritten to the preferred language.
- Radarr-produced `poster.*` received a marker for the expected localized TMDB
  candidate.

Movie `clearlogo.*` rewriting is covered by unit tests because Radarr does not
currently generate that file from its TMDB metadata. The integration fixture
must have a localized TMDB poster candidate for the configured language.
Missing upstream data fails the test rather than skipping it.

Unit tests cover NFO parsing, media-aware paths and endpoints, movie title
parsing, original-title fallback, movie image resolution, ambiguous root-NFO
rejection, and all existing TV/episode behavior affected by the shared flow.

TDD is deliberately not required. Implementation order is production code,
unit tests, integration tests, then full verification.

## Verification

Run:

```bash
./scripts/run-unit-tests.sh
./scripts/run-integration-tests.sh
./scripts/combine-coverage.sh
./scripts/lint.sh --check
```

The baseline combined coverage measured before this work is 95%. Combined
coverage must not decrease.

## Rejected or Superseded Options

### Image-only Radarr support

Rejected. The goal includes movie metadata, and Radarr's `<movie>` NFO contains
the title and plot fields that require localized rewriting.

### Require specific NFO filenames for image association

Rejected. Radarr supports two NFO naming modes. Image association therefore
uses parsed root content rather than `movie.nfo` or a video-derived name.

### Reject an image directory whenever it has multiple NFO files

Rejected. A valid Sonarr TV root can contain `tvshow.nfo` plus episode NFO
files when season folders are disabled. Only multiple target roots
(`<tvshow>`/`<movie>`) are ambiguous; episode and unrelated NFO files are
ignored for image association.

### Apply movie-only NFO rules to all TV metadata

Rejected. TV requires `<episodedetails>` processing for episode title and plot
translation. TV metadata processing must continue to handle series and
episode roots independently.

### Add season title and plot translation

Rejected. Sonarr and Kodi do not define or generate a season NFO for this
workflow. Season localization remains artwork-only.

### Support long Radarr artwork names

Rejected. Current Radarr Kodi/Emby metadata generation produces short names.
Long-name support would require synthetic integration fixtures and would not
validate Radarr's actual output.

### Support a flat multi-movie Radarr directory

Rejected. Radarr requires a distinct directory for each managed movie. Flat
movie directory behavior is outside supported Radarr operation.

### Resolve movie IDs through IMDb or TVDB

Rejected. Radarr movie NFO files are expected to have a TMDB ID. Skipping a
missing ID is safer than resolving a potentially wrong movie.

### Treat duplicate `movie.nfo` and video-named movie NFO files as equivalent

Rejected. More than one target root NFO in an image directory is treated as
ambiguous even when IDs match. This keeps image ownership deterministic.

### Use TDD as an implementation constraint

Rejected. TDD was explicitly removed from the task. Tests remain mandatory,
but production code may be written before tests.

### Rename the package or CLI

Rejected. The package, CLI, and Docker image remain
`sonarr-metadata-rewrite` to avoid breaking existing users. Documentation and
runtime text should state that Radarr is supported.
