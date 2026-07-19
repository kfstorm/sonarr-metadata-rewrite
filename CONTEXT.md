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

**TMDB Response Cache**:
Persistent local cache of the JSON representation returned for one
HTTPX-serialized TMDB GET URL. It stores provider data, not derived translation
content.
_Avoid_: Translation cache, cached TranslatedContent

**TMDB Request Identity**:
Stable identity of a request for one TMDB representation based on its HTTP
method and fully serialized URL, built by HTTPX before dispatch. It does not
distinguish request headers, credentials, or local selection preferences.
_Avoid_: Endpoint-specific cache key, request path alone, header-variant key

**TMDB JSON Representation**:
JSON document returned by TMDB for a TMDB Request Identity. It is provider
data, not an HTTP client response or derived translation content.
_Avoid_: httpx.Response, TranslatedContent

**Cacheable TMDB Outcome**:
A JSON representation returned with status 200, or an explicit not-found
result, for a TMDB Request Identity. All other HTTP and network failures are
not cacheable outcomes.
_Avoid_: Cached client error, cached rate-limit response, cached server error

**TMDB Cache Lifetime**:
Period during which a Cacheable TMDB Outcome is authoritative locally. It
applies uniformly to all cacheable outcomes.
_Avoid_: Endpoint-specific cache lifetime

**TMDB Response Cache Namespace Version**:
Version identifying a TMDB Response Cache contract. It changes only when the
cache payload or TMDB Request Identity semantics become incompatible.
_Avoid_: Parser version, application release version

**Cacheable TMDB Read**:
An idempotent TMDB GET operation whose provider data uses the TMDB Response
Cache. Translation, details, image, and external-ID reads are cacheable TMDB
reads.
_Avoid_: Cached derived translation, image-selection, or details result

**Lazy Cache Reclamation**:
Deferred physical removal of expired cache entries. Expiration makes an
outcome unavailable immediately; later cache writes reclaim its storage.
_Avoid_: Serving expired outcomes, timed cache purge
