# 2026-09-08 -- Deferred tracker moves to GitHub Issues

- **Status:** completed
- **Agents:** parent (Cursor cloud agent)
- **Domain:** docs | tester
- **Related:** `CHANGELOG.md` 2026-09-08 · `PROBLEM_LOG.md` 2026-09-08 deferred fence parser · GitHub Issues labeled `deferred`

## Task

Operator asked to move the parked-bug / to-do tracker into GitHub instead of markdown files.

## Goal

One list a human can browse on github.com, and one command agents still run (`deferred_log.py status`), with no second editable markdown to-do.

## Why it mattered

`DEFERRED_LOG.md` was the constitution SSOT, but the operator wanted GitHub Issues. Leaving both as editable lists would drift. The deep-dive had just added D-011..D-040, so a cutover now copies a complete snapshot.

## What we changed

- Created labels (`deferred`, `P0`..`P3`, `decision`, `blocked`, `parked`, `domain:*`) and one issue per D-NNN (open items stay open; D-006/D-007/D-008 closed).
- `tools/deferred_github.py` + `deferred_log.py` read/create via `gh`. `--path` still parses markdown for tests and one-shot `publish`.
- `DEFERRED_LOG.md` is how-to only.
- Constitution / MDC / agent-ops updated so agents open Issues, not prepend markdown.
- Fixed `_section` so a how-to mention of `<!-- CLOSED_START -->` cannot swallow the open list (would have closed live issues on migrate).

## How it works now

Browse https://github.com/aaltaay/Nova/issues?q=is%3Aissue+label%3Adeferred

Agents: `py -3 tools/deferred_log.py status` before any fix. New item: `next-id` then `gh issue create` with title `D-NNN -- title` and the labels in the how-to. Close the issue when fixed; still write `PROBLEM_LOG.md` for bugs.

CHANGELOG, PROBLEM_LOG, and `knowledge/task-log/` stay in git. Those answer "what changed / what we fixed / why," not "what is still open."

## Why this approach

- **Issues as SSOT, markdown as how-to.** A generated markdown mirror would become a second tracker the next time someone edited the file by habit.
- **Keep `deferred_log.py`.** Agents and the session brief already call it. Swapping the backend to `gh` avoided teaching a new command.
- **Rejected:** moving PROBLEM_LOG / CHANGELOG / task-log / roadmap into Issues. Those are history and product-phase ledgers. Dumping them into Issues would bury the to-do.
- **Rejected:** GitHub Projects as the first cut. Issues + severity/domain labels are enough to filter. A Project board can be added later without a second SSOT.
- **Line-anchored fences.** `str.find` on the how-to sentence was a migrate foot-gun; fixed before `publish`.

## Verification

- `pytest tools/test_deferred_log.py tools/test_deferred_github.py`
- `python3 tools/deferred_log.py publish --path /tmp/deferred-log-migrate.md` then `status` / `next-id`
- `python3 tools/doc_invariants.py`

## Follow-ups

Optional: a GitHub Project board that views the same `deferred` issues. Do not file a second markdown list.

## Keywords

GitHub Issues, deferred, D-NNN, deferred_log.py, publish, CLOSED_START fence, SSOT
