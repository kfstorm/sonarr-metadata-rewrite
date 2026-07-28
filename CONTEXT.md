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

**Translation Tag**:
The language identifier of a TMDB Translation Record, consisting of a language
and an optional region.
_Avoid_: Required locale, Original Language

**Translation Record**:
TMDB translation metadata explicitly associated with one Translation Tag. An
absent record is distinct from a present record even when all of the record's
localizable fields are empty.
_Avoid_: Localized document, language translation

**Empty Metadata Field**:
A provider field that is missing, null, empty, or contains only whitespace.
These representations carry the same absence of content.
_Avoid_: Invalid translation, absent Translation Record

**Unresolved Field**:
A metadata field for which no source has been selected.
_Avoid_: Selected empty field, missing Translation Record

**Selected Empty Field**:
An empty metadata field deliberately selected from a known Content Source. It
can represent an instruction to preserve or restore the absence of a value.
_Avoid_: Unresolved Field, ignored field

**Original Language**:
TMDB's language-only classification of a media item's original version. It
does not identify a region, script, or locale.
_Avoid_: Original locale, source locale

**Original Title**:
A title explicitly identified by TMDB as `original_title` or `original_name`.
A localized `title` or `name` is not an Original Title.
_Avoid_: Details title, localized name

**Language Match**:
Equality of the primary language subtags of a Translation Tag and an Original
Language, without considering region or script.
_Avoid_: Locale match, script match

**Original-Title Fallback Eligibility**:
A Translation Record is eligible when its title is an Empty Metadata Field and
its Translation Tag's language matches the media's Original Language. An
absent record is not eligible.
_Avoid_: Missing-locale fallback, locale inference

**Original-Title Fallback**:
Use of the media's Original Title to fill an eligible Translation Record's
empty title. It occupies that Translation Tag's priority position ahead of all
later tags.
_Avoid_: Original translation, language fallback

**Field-Level Translation Fallback**:
Independent selection of title, overview, and tagline from Translation
Records in preference order. Overview and tagline never use Original-Title
Fallback.
_Avoid_: Document fallback, locale document selection

**Selection Tag**:
The preferred Translation Tag position at which a metadata field is resolved.
It is not necessarily the language tag of the selected content.
_Avoid_: Source locale, content language

**Content Source**:
The provider field and language precision from which selected content actually
originates. Original Title content retains its Original Language and is not
reclassified as its Selection Tag.
_Avoid_: Selected locale, effective locale

**Existing NFO Content**:
Metadata already present in the NFO and preserved after preferred Translation
Records provide no value. Its language is unknown and it has no Selection Tag.
_Avoid_: Original Language content, original translation

**Backup NFO Content**:
Metadata restored from the persisted backup NFO after no preferred Translation
Record can supply content. Its language is unknown and it has no Selection Tag.
_Avoid_: Existing NFO Content, Original Language content

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
