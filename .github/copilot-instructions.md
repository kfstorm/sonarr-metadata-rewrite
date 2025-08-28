# GitHub Copilot Instructions

Purpose
- Short, actionable guidance for GitHub Copilot when generating code, tests, or PR drafts for this repository.
- CLAUDE.md is the authoritative source for design rationale and full workflows. Always consult it for detailed decisions: ../CLAUDE.md

Top-level rule
- Follow everything in `CLAUDE.md`. This file highlights immediate rules Copilot must always enforce when producing changes.

Must-follow checklist (Copilot MUST enforce)
- Respect code style and linters:
  - Run formatters and linters locally when possible: Black (line-length: 88), Ruff, MyPy (strict typing) with Pydantic plugin.
  - Fix obvious lint failures; avoid producing code that breaks pre-commit hooks.
- Tests:
  - Add/update unit tests for any non-trivial behavior change (tests/unit).
  - Add integration tests (tests/integration) when behavior affects end-to-end flows; integration tests use Docker fixtures.
  - Run ./scripts/run-unit-tests.sh and ./scripts/run-integration-tests.sh when applicable.
- CI and scripts:
  - Use existing scripts: ./scripts/setup-dev.sh, ./scripts/lint.sh, ./scripts/combine-coverage.sh, etc.
  - Use uv for running the CLI: uv run sonarr-metadata-rewrite
- Secrets and configuration:
  - Do NOT add secrets, credentials, or personal data in code or repository files.
  - The TMDB_API_KEY must come from environment (.env) per CLAUDE.md; do not hardcode keys.
- Backwards compatibility:
  - Preserve backwards compatibility unless a breaking change is explicitly requested and documented.
- File operations and behavior:
  - Respect atomic file write behavior, optional backups, and reprocessing-avoidance logic described in CLAUDE.md.
- API usage:
  - Follow TMDB integration rules: use /tv/{id}/translations and episode endpoints, handle HTTP 429 with exponential backoff, and cache translations where appropriate.
- Project conventions:
  - Follow repository layout (src/ package), versioning (_version.py via Hatch/VCS tags), and module separation.

Branch, commit, and PR conventions
- Branch name: kebab-case with prefix: feat/, fix/, chore/, docs/, test/ (e.g., feat/add-tmdb-cache).
- Commit message: type(scope?): short summary
  - Example: feat(translator): add diskcache for TMDB translations
- PR title: mirror commit title. PR body should include:
  - Summary: what changed and why (1–2 sentences)
  - Test plan: how changes were validated (scripts/ commands / CI)
  - Compatibility notes and migration steps if any
  - Linked issue: #NNN (if applicable)

Quick practical checks before proposing a PR
- [ ] Code formatted with Black and linted with Ruff
- [ ] Mypy checks (or documented typing exceptions)
- [ ] Unit tests added/updated and run
- [ ] Integration tests added/updated when flow changes
- [ ] Documentation updated (README, comments, or CLAUDE.md for design changes)
- [ ] No secrets in code or config
- [ ] PR description follows conventions above and links to issue if present

Things Copilot must avoid
- Large architectural rewrites without a human-written design or an opened issue requesting the change.
- Hardcoding environment or CI assumptions not documented in CLAUDE.md.
- Changing license, owner metadata, or legal files.

If requirements are ambiguous
- Prefer generating a short PR draft or an issue that outlines the proposed approach, including a test plan and impact analysis, and request human review before implementing broad changes.

Where to find more information
- CLAUDE.md (primary): ../CLAUDE.md
- scripts/: development and test scripts referenced above
- tests/: unit and integration test patterns and fixtures
- .github/: PR/issue templates and CI config

Example PR template (for generated PRs)
- Title: feat(<scope>): short summary
- Body:
  - Summary: what changed and why
  - Testing: commands used locally and CI expectation
  - Notes: breaking changes, migration steps
  - Linked issue: #NNN (if applicable)

This file is intentionally concise and operational. Use CLAUDE.md for full development workflow, design constraints, and detailed examples.
