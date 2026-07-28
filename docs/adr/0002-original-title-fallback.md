# Resolve Empty Translation Titles with Original Titles

**Status:** Accepted

When an explicitly available TMDB Translation Record has an empty title and
its Translation Tag's primary language matches the media's Original Language,
use TMDB's explicit Original Title at that tag's priority position. This keeps
the configured preference order from being defeated by a later tag merely
because TMDB omits a same-language title, while retaining the Original Title's
language-only provenance instead of treating it as locale-specific content.

## Consequences

- An absent Translation Record is not eligible, but a returned record remains
  eligible even when all of its localizable fields are empty.
- Original-Title Fallback precedes titles from later Translation Tags.
- Only fields explicitly identified by TMDB as `original_title` or
  `original_name` qualify; localized `title` and `name` fields do not.
- Overview and tagline continue normal field-level Translation fallback and
  never use Details metadata as original content.
- Selection Tag and Content Source remain distinct and are reported for both
  modified and unchanged files.
