# Maintainer memory (living)

Living knowledge for the Nova `maintainer` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/maintainer.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-16T00:00:00-04:00
source_revision: b8626e4
result: FINDINGS
metrics:
  findings_total: 34
  findings_non_baseline: 32
  main_py_lines: 168
  app_tsx_lines: 83
blockers: []
dashboard_freshness: stale
notes: "Line counts and finding totals come from tools/maintainer_checks.py — re-run for live numbers."
```

Accepted-baseline *rationale* stays below; current measured line counts come from `maintainer_checks`, not from this prose table alone.

---

## How to continue improving (for humans + agents)

Pick the next open item in **Backlog**, or after any significant change ask:

> Use the maintainer subagent to audit the repo.

Or specifically:

> Improve the maintainer agent — work the next backlog item in `.cursor/agent-memory/maintainer-memory.md`.

Durable facts (commands, severity rules, traps) get **promoted into `maintainer.md`**. Baselines, suppressions, run history, and open ideas stay **here**.

---

## Accepted baselines

Documented known violations that must **not** be reported as new CRITICAL findings. Rationale is durable here; obtain current line counts from `py -3 tools/maintainer_checks.py`. Report WARNING if a baselined file grew past the last accepted count.

| Path | Limit | Baseline lines (accepted) | Why accepted |
|------|-------|---------------------------|--------------|
| `backend/hod_momo.py` | 400 | 941 | Module-level globals reassigned by `load_state`/`reset_all`; tests monkeypatch those globals — further split needs a shared-state module (see `file-size-limits.mdc`) |
| `backend/strategy/executor.py` | 400 | 494 | Order-safety gate chain + kill-switch path kept in one audited place; tests monkeypatch `_open_positions` / `_kill_switch_tripped` (see `file-size-limits.mdc`) |

Hard limits that are **not** baselined (any breach is CRITICAL):

| Path | Limit |
|------|-------|
| `backend/main.py` | 200 |
| `frontend/src/App.tsx` | 150 |

---

## Suppressions

False positives the deterministic scanner or greps keep hitting. Pattern + reason. Newest first.

_(empty)_

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [ ] **Weekly automation** — optional Cursor Automation or scheduled CI job that runs `tools/maintainer_checks.py --json` and posts a summary.
- [ ] **CI gate** — add a GitHub Actions job mirroring the deterministic scanner + `ruff check backend` (start as warning-only).
- [ ] **Feed-mixing heuristics** — extend the scanner with AST/grep rules for IBKR→Alpaca silent fallbacks called out in `single-market-data-feed.mdc`.
- [ ] **Changelog/PROBLEM_LOG drift detector** — compare recent `git log` subjects to whether a matching entry was added in the same commit.
- [ ] **Frontend component line-count accuracy** — refine React ≤300 detection (currently any `.tsx` under `frontend/src`).
- [ ] **Promote top findings** — after 2+ identical WARNING classes, add a Known trap bullet to `maintainer.md`.

### Completed

- [x] 2026-07-15 — Initial maintainer agent, memory, and deterministic scanner.

---

## Learned facts (pending promotion)

Facts discovered in a run that are **not yet** in `maintainer.md`. After promoting, delete the bullet here.

_(empty)_

---

## Run log

Newest first. Keep entries short. Skip boring all-clean runs unless a command/path was corrected.

<!-- RUN_LOG_START -->

### 2026-07-15 — Agent install

- **Scope:** Meta — create maintainer sentinel + `tools/maintainer_checks.py`.
- **Result:** n/a (protocol install)
- **Learning:** Baselines seeded from `file-size-limits.mdc` (hod_momo 941, executor 494 via `count_lines`).
- **Files updated:** `maintainer.md`, `maintainer-memory.md`, `tools/maintainer_checks.py`.

<!-- RUN_LOG_END -->
