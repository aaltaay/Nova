---
description: Static marketing news ranking and publication contract
globs: tools/ai_news*.py,tools/test_ai_news*.py
alwaysApply: false
---

# Marketing news digest

- Public RSS/Atom only; this tooling never participates in scanner or broker execution.
- Apply strict AI-used-in-trading topic rules, block publisher spam even through Google News wrappers, and cap mega-wire publishers at two stories while retaining a stricter caller cap.
- The full feed may use a 14-day recency half-life with a 90-day age limit; the homepage keeps its short teaser and existing honesty floor.
- Native trade-press feeds and separate per-outlet searches avoid one combined search starving smaller publications. Decode gzip bodies even without an encoding header; malformed compressed bodies fail as unavailable feeds with a warning.
- Avoid clock-only rewrites by comparing ordered published story content and the rendered blocks at the previous publication time. Changes to title, URL, summary, source, publication date, selection or rendering must still publish. Invalid prior JSON is a cache miss, never a crash.
- Preserve the existing PR helper and token configuration, required Desktop pack checks, and derived version scheme when recovering historical WIP.
- Following ADR 003 (functional core / imperative shell), topic predicates and publication comparison helpers stay separate from fetching and file writes. Tests are split by ranking, parsing, and publishing responsibility; keep each module below 400 lines.
