# Tester memory (living)

Living knowledge for the Nova `tester` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/tester.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-15T23:00:00-04:00
source_revision: b8626e4
result: PASS
metrics:
  pytest_passed: 562
  vitest_passed: 131
  vitest_files: 28
  playwright_passed: 14
blockers: []
dashboard_freshness: stale
notes: "Counts from 2026-07-15 continuity refresh; tip work may have drifted — backlog #1."
```

Counts live only here (and in canvas snapshots derived from this block). Do not hardcode volatile totals in `tester.md`.

---

## How to continue improving (for humans + agents)

Pick the next open item in **Backlog**, or after any test run ask:

> Use the tester subagent to verify \<change\>, then apply its self-improvement protocol.

Or specifically:

> Improve the tester agent — work the next backlog item in `.cursor/agent-memory/tester-memory.md`.

Durable facts (commands, traps, routing) get **promoted into `tester.md`**. Run history and open ideas stay **here**.

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [ ] **Refresh test counts** — periodically re-run full pytest/Vitest/Playwright collection and update Current snapshot when they drift (last refresh 2026-07-15: 562 / 131 / 14).
- [ ] **Expand routing table** — add rows for `backend/news*`, `backend/scanner*`, `backend/l2*`, `frontend/src/strategy/*`, `frontend/src/TickerChart*`, `frontend/src/workspace/*` once those areas get touched often.
- [ ] **Ruff / backend lint gate** — if the repo adopts Ruff (or documents a preferred command), add it beside frontend `npm run lint`.
- [ ] **CI parity** — read `.github/workflows/*` and note any gates the local tester should mirror (matrix Python version, e2e on PR only, etc.).
- [ ] **Seed a golden browser path** — one short click-path (e.g. open Gappers → pick a symbol → Stock View) recorded here so UI verifies are consistent.
- [ ] **Timeout defaults** — record typical full-suite wall times so the agent sets sensible `block_until_ms` instead of guessing.
- [ ] **Promote top PROBLEM_LOG traps** — when a new test-infra trap appears 2+ times, add it to `tester.md` Known traps and check it off here.

### Completed

- [x] 2026-07-15 — Continuity refresh: promoted test counts in `tester.md` to **562** backend / **131** Vitest (28 files) / **14** Playwright; backlog item left open for future drift checks.
- [x] 2026-07-15 — Verified commands, routing, traps, trading safety, flakiness, server lifecycle (initial specialize pass).
- [x] 2026-07-15 — Self-improvement protocol + this memory file.

---

## Learned facts (pending promotion)

Facts discovered in a run that are **not yet** in `tester.md`. After promoting into `tester.md`, delete the bullet here (or move to Completed note).

_(empty)_

---

## Run log

Newest first. Keep entries short. Skip boring all-green scoped runs unless a command/path was corrected.

<!-- RUN_LOG_START -->

### 2026-07-15 — Continuity refresh full gates

- **Scope:** Step 1 continuity refresh — re-verify ledger counts for Nova-OS-Status / tester facts.
- **Commands:** `py -3 -m pytest backend/tests -q` → 562 passed; `npx vitest run` → 131 passed (28 files); `npm run build` → PASS; `npx playwright test` → 13/14 then retry of `tabs switch` → PASS (14/14).
- **Result:** PASS (Playwright: one parallel flake, retry clean)
- **Learning:** Baseline `tabs switch` can flake under 12 workers; single-test retry is enough before declaring FAIL.
- **Promoted to tester.md:** yes — 562 / 131 / 14 counts

### 2026-07-15 — Memory + self-improvement protocol added

- **Scope:** Meta — create living memory / backlog for continuous tester improvement.
- **Result:** n/a (protocol install)
- **Learning:** None yet; backlog seeded for next runs.
- **Files updated:** `tester.md` (protocol), `tester-memory.md` (this file).

### 2026-07-15 — stockViewNav scoped smoke

- **Scope:** `frontend/src/utils/stockViewNav.ts`
- **Commands:** `npm run test -- src/utils/stockViewNav.test.ts` → 4 passed
- **Result:** PASS
- **Learning:** none (commands already correct)
- **Promoted to tester.md:** no

<!-- RUN_LOG_END -->
