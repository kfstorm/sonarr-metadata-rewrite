---
name: github-release-key-changes
description: Draft and, after explicit approval, update GitHub Release notes with a user-facing Key Changes section. Use whenever a GitHub Actions tag workflow created a release, or when users ask to improve, backfill, review, or update GitHub release notes and changelogs for the latest or historical releases.
compatibility: Requires GitHub CLI authentication with read access to inspect releases and write access only after approval.
---

# GitHub Release Key Changes

Maintain a concise user-facing summary above GitHub's generated release notes.
GitHub's `What's Changed` list is a complete change list, but mixes features,
fixes, CI, tests, and dependency updates. `Key Changes` gives users a faster
way to understand changes that affect installation, configuration, operation,
or output.

## Scope

Use this skill after a tag-triggered GitHub Action creates a release, or when
the user asks to improve existing release notes.

Target only published, non-prerelease releases unless the user explicitly
requests drafts or prereleases. Treat the latest release as the newest release
matching those conditions.

Ask the user to choose one scope before inspecting changes:

1. Latest stable release
2. All historical stable releases

## Existing Sections

Inspect target release bodies before generating drafts.

- For a single target with an existing `## Key Changes` section, ask whether
  to update it. If declined, stop without creating a new draft.
- For historical scope, list every target that already has the section and ask
  once whether to update those sections. Do this before researching or drafting
  replacements for those tags. A request to "replace" or "improve" sections is
  not update approval. Skip those tags entirely if declined.
- For approved updates, replace the complete existing `## Key Changes` block.
  Do not append a second section.

## Research

For every release that needs a draft:

1. Fetch its release body with `gh release view <tag> --json body`.
2. Preserve the complete generated `## What's Changed` section for review.
3. Inspect the tag comparison and linked pull requests or commits when a title
   is ambiguous. Use `gh api`, `gh pr view`, and `gh repo view` as needed.
4. Identify only user-visible changes. Prefer outcomes over implementation.

Include:

- New user-facing capabilities.
- User-visible behavior or configuration changes.
- Fixes users can observe, including correctness, backup, rollback, lookup,
  translation, retry, and compatibility fixes.
- Installation, deployment, image, or runtime changes users must know about.

Exclude:

- CI, test, build, lint, release-workflow, and repository-maintenance changes.
- Dependency-only updates unless a user-visible compatibility or security
  effect is demonstrated.
- Internal refactors and documentation-only changes.

Write clear English. Use flat bullets by default. Group a long list under
`### Features` and `### Fixes` only when grouping materially improves scanning.
Do not impose a bullet limit. If no user-visible changes exist, write exactly:

```markdown
- No user-visible changes.
```

## Draft Review

Never edit a release before explicit user approval. Present one block per
release, ordered newest to oldest for historical scope:

```markdown
### <tag>

#### Proposed Key Changes
## Key Changes

- <user-facing change>

#### Existing What's Changed
<complete existing generated What's Changed section and remaining generated
release-note content>
```

Ask for confirmation after all requested drafts are shown. A user may approve
all releases or name specific tags. Do not infer approval from a request to
draft, inspect, or summarize.

## Apply Approved Drafts

For each approved release:

1. Re-fetch the body to avoid overwriting concurrent edits.
2. Insert `## Key Changes` at the very top when absent, or replace its complete
   existing block when the user approved an update.
3. Preserve the generated `What's Changed`, contributors, full changelog link,
   and unrelated manual text byte-for-byte where practical.
4. Update with `gh release edit <tag> --notes-file <temporary-file>`.
5. Re-fetch the release and verify exactly one `## Key Changes` section exists
   at the top and all generated content remains.

Report updated tags, skipped tags, and verification results. Do not create,
delete, publish, or change release tags.
