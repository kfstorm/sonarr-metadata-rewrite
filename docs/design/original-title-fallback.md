# Original Title Fallback Design

## Status

Implemented and awaiting review in [PR 114](https://github.com/kfstorm/sonarr-metadata-rewrite/pull/114).

This design implements [ADR 0002](../adr/0002-original-title-fallback.md) and
uses the canonical language from the project [context](../../CONTEXT.md).

## Goal

Prevent a later preferred Translation Tag from replacing a media item's
Original Title when an earlier, same-language Translation Record exists but has
an empty title.

Given this preference order:

```text
zh-CN,zh-TW,en-US
```

and this provider data:

```text
zh-CN.title = empty
zh-CN.overview = simplified Chinese overview
zh-TW.title = traditional Chinese title
original_language = zh
original_title = simplified Chinese original title
```

the resolved fields are:

```text
title = original_title, selected at zh-CN
overview = zh-CN overview
```

The Original Title keeps its language-only `zh` Content Source. It is not
reclassified as `zh-CN` content.

## Non-Goals

- Infer an original locale, region, or script from Original Language.
- Use localized Details `title` or `name` as an Original Title.
- Use Details overview or tagline as original content.
- Change field-level Translation fallback for overview or tagline.
- Add implicit bare-language entries to the configured preference list.
- Persist provenance in NFO XML comments or custom elements.
- Change image selection or rewriting.

## Provider Inputs

### Translation Records

The Translations API supplies records identified by `iso_639_1` and an
optional `iso_3166_1`. The resulting Translation Tag is either a bare language,
such as `ja`, or a language-region tag, such as `zh-CN`.

A record remains present even when its `data` object is absent or all of its
localizable fields are empty. Translation parsing therefore:

- Requires a non-empty `iso_639_1`.
- Treats a missing or null `data` value as an empty object.
- Treats missing, null, empty, and whitespace-only fields as Empty Metadata
  Fields.
- Preserves the Translation Record after normalization even if title,
  overview, and tagline are all empty.

An absent Translation Record remains distinct from a returned empty record.
Only the returned record can become eligible for Original-Title Fallback.

### Original Title Details

The Details API request does not include a `language` parameter. Only these
explicit field pairs can produce an Original Title candidate:

| Original Language field | Original Title field |
| --- | --- |
| `original_language` | `original_title` |
| `original_language` | `original_name` |

Both normalized fields must be non-empty. A localized `title` or `name` never
substitutes for a missing Original Title field.

This is a provider-capability rule rather than a media-type allowlist. Current
movie and TV series representations expose an explicit Original Title. Current
episode representations do not, so episodes naturally have no Original Title
candidate. In particular, a series Original Language cannot turn an episode's
localized `name` into an Original Title.

## Field Provenance

Every resolved field carries provenance instead of overloading one `language`
string with both source and selection meanings. The existing
`TranslatedString` and `TranslatedContent` type names remain to limit the scope
of the change, but `TranslatedString` gains these concepts:

| Property | Meaning |
| --- | --- |
| `content` | Normalized value; may be a selected absence. |
| `source` | Content Source kind, or no source for an Unresolved Field. |
| `source_tag` | Actual provider language or Translation Tag, when known. |
| `selection_tag` | Preferred Translation Tag position that resolved the field. |

Content Source kinds are:

| Source | Source tag | Selection tag |
| --- | --- | --- |
| TMDB Translation Record | Record's Translation Tag | Same preferred tag |
| TMDB Details Original Title | Original Language | Eligible preferred tag |
| Existing NFO Content | Unknown | None |
| Backup NFO Content | Unknown | None |

An empty field with no source is an Unresolved Field. An empty field with a
source is a Selected Empty Field. This distinction preserves existing tagline
semantics: selecting an empty Backup NFO tagline restores the absence of a
tagline instead of leaving a translated tagline in place.

Parsed Translation Record fields carry their provider source and source tag but
do not receive a selection tag until selected. Selection creates resolved field
values rather than mutating cached or parsed provider data.

## Resolution Algorithm

Title, overview, and tagline remain independently resolved. Iterate configured
preferred Translation Tags in order and consider only an exact Translation
Record match.

For each matching record:

1. If title is unresolved and the record title is non-empty, select it from the
   TMDB Translation Record.
2. If title is unresolved and the record title is empty, obtain Original Title
   Details at most once for the resource.
3. If the Translation Tag and Original Language have equal primary language
   subtags and an explicit Original Title exists, select that title at the
   current Translation Tag's priority position.
4. If overview is unresolved and the record overview is non-empty, select it
   from the TMDB Translation Record.
5. If tagline is unresolved and the record tagline is non-empty, select it from
   the TMDB Translation Record.
6. Stop when all fields are resolved; otherwise continue to the next preferred
   Translation Tag.

Primary language comparison is case-insensitive and ignores region and script.
It applies to both bare-language and language-region Translation Tags. For
example, `zh-CN`, `zh-Hant-TW`, and `zh` all have the primary language `zh`.
This comparison establishes only a Language Match; it does not increase the
Original Title's precision.

Original-Title Fallback occurs while processing the eligible record. It
therefore precedes a non-empty title from every later Translation Tag.

After the preference list is exhausted:

- A processing result with at least one preferred field selects Existing NFO
  Content for unresolved fields.
- Existing backup restoration behavior applies when no preferred field was
  selected and a Backup NFO Content value is available.
- Fields that remain absent retain their explicit selected-empty or unresolved
  state as required by writing behavior.

The existing post-selection Original Title lookup is removed. It runs too late
to precede titles from later Translation Tags, loses provenance, and can treat
an episode's localized name as original content.

## Details Read Behavior

The Details read is lazy. It occurs only when all of these conditions hold:

- Title is still unresolved.
- An exact preferred Translation Record exists.
- That record has an Empty Metadata Field for title.

The result is reused for every later eligible record in the same resource
resolution. The existing TMDB Response Cache stores the raw Details JSON, so no
derived selection or preference-dependent value is cached.

Details outcomes have these effects:

| Outcome | Behavior |
| --- | --- |
| Explicit Original Language and Original Title | Evaluate Language Match. |
| HTTP 404 | Continue normal Translation fallback. |
| Missing or empty Original field | Continue normal Translation fallback. |
| Language mismatch | Continue normal Translation fallback. |
| Network error or non-404 HTTP error | Fail and leave the NFO unchanged. |

Failing closed on transient Details errors prevents temporary provider failure
from replacing a same-language Original Title with a later-language title.

## Logging

Both modified and unchanged processing results report Original-Title Fallback.
The message includes:

- The actual Original Title value.
- Its Original Language.
- The Selection Tag whose empty title it filled.

Example modified result:

```text
Successfully translated (
  title: Original Title "捕风追影" [zh], fallback for zh-CN;
  description: zh-CN;
  tagline: zh-TW
)
```

Example unchanged result:

```text
Content already matches preferred translation (
  title: Original Title "捕风追影" [zh], fallback for zh-CN
)
```

Normal fields continue to report their source Translation Tags. If all selected
fields come directly from one Translation Record, the existing concise message
remains valid:

```text
Successfully translated to zh-CN
```

No provenance is written to the NFO. Every processing pass reconstructs it from
cached or freshly fetched TMDB provider data.

## Cache Compatibility

The TMDB Response Cache already stores raw provider JSON rather than parsed
translation models. Preserving empty Translation Records and adding field
provenance are parser and selection changes, so they do not require a cache
namespace version change or cache migration.

The Details request without a `language` parameter has its own serialized URL
identity. Preference changes continue to reuse the same raw Translation and
Details responses.

## Code Changes

Expected implementation surfaces:

| File | Change |
| --- | --- |
| `models.py` | Add provenance and Original Title details. |
| `translator.py` | Preserve empty records and explicit Original facts. |
| `metadata_processor.py` | Resolve Original Title at the eligible tag. |
| `metadata_processor.py` | Track NFO and backup provenance. |
| `metadata_processor.py` | Remove the post-selection Details lookup. |
| `metadata_processor.py` | Render provenance-aware result messages. |
| Unit tests | Cover parsing, selection, sources, writing, and logging. |
| Integration tests | Retain the Radarr and Sonarr reproductions. |

No configuration or environment variable changes are required.

## Test Design

### Translator Tests

- Preserve an exact Translation Record whose fields are all empty.
- Normalize missing, null, empty, and whitespace-only fields.
- Preserve a countryless record as a bare-language Translation Tag.
- Return Original Title facts only from explicit `original_title` or
  `original_name` fields.
- Do not combine a series Original Language with an episode localized `name`.
- Request Details without a `language` parameter.

### Metadata Processor Tests

- A present empty-title record with a Language Match selects Original Title
  before a later Translation Tag title.
- An absent record does not trigger Original-Title Fallback.
- A language mismatch continues to the next Translation Tag.
- A non-empty record title wins without a Details read.
- Bare-language Translation Tags can trigger fallback.
- Overview and tagline continue independently through later Translation
  Records and never use Details fields.
- Details 404 or missing facts continues fallback.
- A transient Details failure returns a processing error and leaves the NFO
  unchanged.
- Original Title provenance separates Original Language from Selection Tag.
- Existing and Backup NFO Content have unknown source language and no Selection
  Tag.
- Selected empty Backup NFO tagline removes an existing tagline.
- Modified and unchanged messages include the Original Title value, Original
  Language, and Selection Tag.

Tests exercise the public `process_file()` behavior where practical. Focused
translator parsing tests may call parsing seams directly, but processor tests do
not depend on new private helper names.

### Integration Tests

Retain the current real-provider reproductions:

- A French movie keeps `Le Fabuleux Destin d'Amélie Poulain` instead of using
  the later `en-US` title `Amélie`.
- A Simplified Chinese movie keeps `捕风追影` instead of using the later
  `zh-TW` title `捕風追影`.
- A Chinese TV series keeps `大明王朝1566` instead of using the later English
  title `Ming Dynasty in 1566`.

## Verification

Run:

```bash
./scripts/run-unit-tests.sh
./scripts/run-integration-tests.sh
./scripts/combine-coverage.sh
./scripts/lint.sh --check
npx jscpd
```

Verification completed:

- Unit tests: 347 passed.
- Integration tests: 22 passed, including all three title reproductions.
- Combined coverage: 96%.
- Lint and duplication checks: passed.

## Rejected Options

### Fall back when the Translation Record is absent

Rejected. Absence gives no evidence that TMDB associates the media with the
requested Translation Tag. Only a returned record with an empty title is
eligible.

### Try all explicit Translation titles before Original Title

Rejected. This allows a later Translation Tag to defeat the configured priority
of an earlier record solely because TMDB omitted its same-language title.

### Treat Original Title as Selection Tag content

Rejected. Original Language lacks region and script precision. Selection Tag
and Content Source remain separate.

### Use localized Details fields as original content

Rejected. Details does not expose the provenance of localized `title`, `name`,
`overview`, or `tagline` fields.

### Continue after transient Details errors

Rejected. Continuing can rewrite a correct Original Title with a later-language
title while the provider is temporarily unavailable.

### Persist provenance in NFO XML

Rejected. Private comments or elements would pollute interoperable NFO output.
The service can reconstruct provenance from cached provider responses.

### Add resource-type eligibility checks

Rejected. Eligibility depends on explicit Original Language and Original Title
facts, not a hard-coded resource family. Resources without those facts simply
cannot produce a candidate.
