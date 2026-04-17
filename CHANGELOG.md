# Change log (agent-maintained)

This file is a running narrative of **what changed in this repo and why**, so future agent and human sessions can get oriented in minutes without digging through diffs.

- **Scope:** code behavior, module boundaries, public APIs, constants, tooling, rules, user-visible UI changes.
- **Out of scope:** pure typo fixes, formatting-only edits, local scratch files.

Bug fixes should **also** be logged in `PROBLEM_LOG.md` (symptom / cause / fix). This file answers "what does the codebase do now and why"; `PROBLEM_LOG.md` answers "what went wrong and how was it diagnosed."

## How agents update this file

1. **When:** After completing any task that changes logic, public behavior, a module boundary, constants, config, build, or rules. Skip pure cosmetics.
2. **Where:** Prepend a new `##` section **immediately below** the `<!-- ENTRIES_START -->` marker (newest entries at the top).
3. **Commit together:** The changelog entry ships in the **same commit** as the code it describes. Do not push code without an entry.
4. **Keep it short:** A few lines per field. No secrets, tokens, or personal data.

Entry template (copy and fill in):

```markdown
## YYYY-MM-DD — Short descriptive title

- **What:** 1–2 sentences on what changed (user-visible + internal).
- **Why:** Trigger for the change (user request, bug class, performance, cleanup).
- **Files touched:** Key files only, e.g. `backend/scanner.py`, `frontend/src/App.tsx`.
- **How it works now:** The mental model a future agent needs — the "oh, got it" paragraph.
- **Verified by:** How you confirmed it works (built + ran, test name, manual click path).
- **Follow-ups:** (optional) anything deferred.
- **Related:** (optional) commit SHA, PROBLEM_LOG entry date, issue link.
```

<!-- ENTRIES_START -->

## 2026-04-17 — Add agent-maintained CHANGELOG.md and `change-log` rule

- **What:** Introduced `CHANGELOG.md` at the repo root and a new always-on rule `.cursor/rules/change-log.mdc` that requires agents to prepend a human-readable summary after every non-trivial task. Sits alongside the existing `problem-log.mdc` / `commit-after-tasks.mdc` policies.
- **Why:** Reading raw diffs or `git log` is too slow when re-entering the project. The user wants a single "swipe through and understand" file, especially the *"how it works now"* narrative that commits and bug logs don't capture.
- **Files touched:** `CHANGELOG.md` (new), `.cursor/rules/change-log.mdc` (new).
- **How it works now:** Three agent-maintained docs cover different questions: `CHANGELOG.md` = "what does this codebase do now and why" (newest-first, prepend on every task), `PROBLEM_LOG.md` = "what bug happened and how was it fixed" (newest-first, prepend on resolutions), `.cursor/rules/*.mdc` = persistent policies. Task completion is not done until the changelog entry exists and ships in the same commit as the code.
- **Verified by:** Built and ran the app via `Run Stock Alert.bat` (uvicorn on `:8000`, Vite on `:5173`) — no code paths changed, doc-only change.
- **Follow-ups:** `progress.md` and `findings.md` (Phase-0 leftovers, last touched 2026-04-13) overlap with this file and should probably be archived or deleted in a future task.
- **Related:** Mirrors the newest-first `<!-- ENTRIES_START -->` convention in `PROBLEM_LOG.md`.
