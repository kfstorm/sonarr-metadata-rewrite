# Media Metadata Rewrite

This service localizes Sonarr TV and Radarr movie metadata plus selected local
artwork using TMDB resources.

## Language

**Target Root NFO**:
An NFO whose XML root is `<tvshow>` or `<movie>` and can identify media for
image processing.
_Avoid_: Any NFO, parent NFO

**Episode NFO**:
An NFO rooted at `<episodedetails>` that contains metadata for one or more TV
episodes.
_Avoid_: Season NFO

**Movie NFO**:
An NFO rooted at `<movie>` describing one Radarr-managed movie.
_Avoid_: Video NFO

**Media Type**:
The TMDB resource family, either TV or movie.
_Avoid_: Source application

**Artwork Kind**:
The local artwork category selected for rewriting: poster or clearlogo.
_Avoid_: Image type
