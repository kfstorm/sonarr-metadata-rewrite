check design doc #file:image_rewrite_plan.md and see if we missed some test cases in #file:missing_test_cases.md . Also consider error cases and edge cases. If you think we need any more cases, append them to the test cases doc at the end with a special section, and implement these test cases.

- Add retry on getting TMDB ID from nfo file. (It's possible that Sonarr creats image files before creating .nfo file.)
- Update docs (CLAUDE.md, README.md, ...)
- Fix imports not at the top of files. `git grep -E -B 1 '^\s+from .* import .*|^\s+import .*'`
- clearlogo.png is not being rewritten.
