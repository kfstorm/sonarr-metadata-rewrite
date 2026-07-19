# Cache TMDB Provider JSON Responses

**Status:** Accepted

Cache every idempotent TMDB read as provider JSON for a versioned,
HTTPX-serialized GET URL, rather than caching parsed application models. This
prevents a parser change, such as adding `tagline`, from treating absent fields
in an old cached model as authoritative data while preserving reuse across
parser-only releases.

## Consequences

- Cache only 200 responses and 404 outcomes, using one configured lifetime.
  Other HTTP outcomes and network failures are never cached.
- Request identity uses the HTTP method and fully serialized URL built by HTTPX
  before dispatch. Query-parameter ordering remains part of URL identity.
  Headers are outside the initial cache contract.
- Change the cache namespace only when provider JSON storage or request
  identity semantics become incompatible. Legacy entries are ignored and
  reclaimed through DiskCache's lazy expiry lifecycle.
- Do not add request single-flight coordination until duplicate TMDB traffic
  becomes a demonstrated operational problem.
