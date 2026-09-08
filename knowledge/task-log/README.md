# Nova task log

Append-only folder of **completed work narratives** — what we set out to do, why the fix looks the way it does, and how to think about it next time.

Since 2026-09-08 the **default home for that narrative is the pull request body** (`.github/pull_request_template.md`). This folder is for work that ships **without** a PR: direct pushes, ops diagnoses, audit conclusions, and local docs commits. Rule: `.cursor/rules/task-log.mdc`.

Do not write both a PR body and a file here for the same job. Entries already in this folder are append-only history -- never delete one to deduplicate against a PR.

This is **not** a substitute for:

| File | Job |
|------|-----|
| `CHANGELOG.md` | Short "what the codebase does now" |
| `PROBLEM_LOG.md` | Bug/failure diagnosis after a **fix** (symptom -> cause -> fix) |
| GitHub Issues (label `deferred`) | Known bugs and parked features that are **not** done yet |
| Agent `*-memory.md` | Per-specialist working memory (not the SSOT for parked work) |
| PR body / this folder | Full task story + **reasoning / tradeoffs** |

Cold agents should skim `INDEX.md` and the repo's merged PRs, then open the matching entry before re-touching the same area.

## When to write a file here

**Required** at the end of every completed task **with no PR** that changed code, config, docs policy, agent wiring, or security posture — and after every specialist run that produced a material result (fix, audit conclusion, ops diagnosis) outside a PR.

**Skip** only for: pure typos, formatting-only, aborted work with nothing learned, or “status check / crack index” with no decision.

## How to add an entry

1. Copy `_template.md` → `YYYY-MM-DD-<kebab-slug>.md` (UTC or local calendar date; newest work uses today’s date).
2. Fill every section. The **Why this approach** section is mandatory — that is the point of this log.
3. Prepend a row to `INDEX.md` (newest first).
4. Cross-link from `CHANGELOG.md` / `PROBLEM_LOG.md` / the GitHub issue when those also get an entry (`Related:` -> task-log path).
5. In the agent Lifecycle line, set `task_log=<relative-path>|<PR URL>|skipped|n/a`.

Helper:

```text
py -3 tools/task_log_new.py --slug short-name --title "Human title"
```

## Ownership

- **Parent / implementer** writes the narrative for product work they ship, including one aggregate narrative when in-session work spans multiple domains (zero-hop default — see `specialist-routing.mdc`).
- **Docs** may tidy formatting; must not invent technical reasons.
- Rule: `.cursor/rules/task-log.mdc` (always apply).
