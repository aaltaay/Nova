# Tester memory (living)

Living knowledge for the Nova `tester` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/tester.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-16T23:32:00-04:00
source_revision: 13e530f
result: FAIL
metrics:
  pytest_passed: 677
  vitest_passed: 223
  vitest_files: 49
  playwright_passed: 11
blockers:
  - "vitest: src/stock_view/stockViewTerminal.test.tsx > renders terminal chrome, charts, and rail for matching symbol — missing [data-testid=\"sv-trading-lock\"] (reproduced twice, not flaky)"
  - "playwright: 3 e2e specs (baseline.spec.ts, workspace-context.spec.ts, level2-tape-modules.spec.ts) fail on missing 'Stock View' header text / unreachable 'Look up symbol' input (reproduced twice, not flaky)"
dashboard_freshness: clean
notes: "last_dream_at=2026-07-18T03:09:15-0400; All 3 gates re-run this session (pytest+vitest+playwright, all fresh). vitest/playwright failures trace to the same in-progress, uncommitted frontend/src/stock_view/ header refactor (git status: ?? untracked dir) — StockViewHeader no longer renders the trading-lock testid or literal 'Stock View' label some e2e/unit specs assert on. Not fixed here per task scope (tester does not touch product code); flag to whoever owns that WIP (widgets / Stock View work) before it lands. pytest 677 includes the known-benign torchvision c0000139 native-loader crash log during test_news_impact.py (PROBLEM_LOG 2026-07-16) — exit 0, no test failures."
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

- [x] **Refresh test counts** — periodically re-run full pytest/Vitest/Playwright collection and update Current snapshot when they drift (last refresh 2026-07-16: 677 / 223-of-224 / 11-of-14, 2 real regressions found — see Run log).
- [ ] **Expand routing table** — add rows for `backend/news*`, `backend/scanner*`, `backend/l2*`, `frontend/src/strategy/*`, `frontend/src/TickerChart*`, `frontend/src/workspace/*` once those areas get touched often.
- [ ] **Ruff / backend lint gate** — if the repo adopts Ruff (or documents a preferred command), add it beside frontend `npm run lint`.
- [ ] **CI parity** — read `.github/workflows/*` and note any gates the local tester should mirror (matrix Python version, e2e on PR only, etc.).
- [ ] **Seed a golden browser path** — one short click-path (e.g. open Gappers → pick a symbol → Stock View) recorded here so UI verifies are consistent.
- [ ] **Timeout defaults** — record typical full-suite wall times so the agent sets sensible `block_until_ms` instead of guessing.
- [ ] **Promote top PROBLEM_LOG traps** — when a new test-infra trap appears 2+ times, add it to `tester.md` Known traps and check it off here.

### Completed

- [x] 2026-07-16 — Full gate refresh: 677 pytest / 223-of-224 Vitest (49 files) / 11-of-14 Playwright. Found 2 real (non-flaky) regressions in uncommitted `frontend/src/stock_view/` WIP — flagged in snapshot `blockers`, not fixed (out of tester scope).
- [x] 2026-07-15 — Continuity refresh: promoted test counts in `tester.md` to **562** backend / **131** Vitest (28 files) / **14** Playwright; backlog item left open for future drift checks.
- [x] 2026-07-15 — Verified commands, routing, traps, trading safety, flakiness, server lifecycle (initial specialize pass).
- [x] 2026-07-15 — Self-improvement protocol + this memory file.

---

## Learned facts (pending promotion)

Facts discovered in a run that are **not yet** in `tester.md`. After promoting into `tester.md`, delete the bullet here (or move to Completed note).


---

**(empty)**
## Run log

Newest first. Keep entries short. Skip boring all-green scoped runs unless a command/path was corrected.

<!-- RUN_LOG_START -->

### 2026-07-16 — Snapshot refresh: full pytest + Vitest + Playwright

- **Scope:** Dashboard-freshness refresh — re-run all 3 deterministic gates and update Current snapshot (no product code touched).
- **Commands:** `py -3 -m pytest backend/tests -q` → **677 passed**; `npx vitest run` → 224 tests/49 files, 2 failed; retried the 2 failing files → `StockViewHeader.test.tsx` passed clean (flaky, act() warning race — not re-flagged), `stockViewTerminal.test.tsx` failed identically both times → **223/224 passed real**; `npx playwright test` → 14 tests, 3 failed, retried the 3 → identical failures both times → **11/14 passed real** (31–37s wall time, safe to run every refresh).
- **Result:** FAIL (2 confirmed, reproducible regressions — not flaky, not infra).
- **Root cause:** `frontend/src/stock_view/` is an entirely untracked directory (`git status` → `?? frontend/src/stock_view/`) mid-refactor. Current `StockViewHeader.tsx` no longer renders `data-testid="sv-trading-lock"` or a literal `"Stock View"` text label that `stockViewTerminal.test.tsx` and 3 Playwright specs (`baseline.spec.ts`, `workspace-context.spec.ts`, `level2-tape-modules.spec.ts`) assert on; the L2/T&S symbol-switch e2e spec also times out because the header refactor makes `getByLabel('Look up symbol')` unreachable in that flow.
- **Learning:** When `git status` shows a whole feature dir as untracked, expect its own tests to be ahead of (or behind) its implementation — verify with `git status`/`git log -- <path>` before assuming a real-suite regression is stable; don't touch it, hand off to the WIP owner.
- **Promoted to tester.md:** no (single-incident WIP note, not a durable trap/routing fact yet)

### 2026-07-16 — Stock View right-rail L2+T&S combined layout

- **Scope:** widgets rail fix — quote → (L2|T&S one card) → horizontal drag → Open ticket.
- **Commands:** `npm run test -- --run src/stock_view/stockViewTerminal.test.tsx` → **11 passed**; browser `?view=stock&symbol=AAPL`.
- **Result:** PASS — live geometry: quote top; L2+T&S same row (top=212); 1 rail horizontal handle between depth/open; `--sv-depth-pct: 72%`; Open has Unlock/Buy/Sell/Limit/Market/Stop/qty. Synthetic pointer drag via eval did not move React handler (wiring + title confirm drag/dblclick reset).
- **Learning:** Console buffer often has stale HMR/`API_URL`/provider errors from earlier sessions — prefer fresh open + layout DOM geometry over raw console dump for Stock View layout claims.
- **Promoted to tester.md:** no

### 2026-07-16 — Stock View bump-under-quote layout

- **Scope:** NewsImpactPanel under quote (`afterQuote` / `includeImpact={false}`); Stock View CSS.
- **Commands:** `npm run test -- quotePanels tickerDetailComposition stockViewNav` → **19 passed** (3 files). Browser: `?view=stock&symbol=AAPL`.
- **Result:** PASS — impact under `.stock-view-quote` / `after_quote`; absent from news footer; body = main | resize | quote.
- **Learning:** Stock View URL is query `?view=stock&symbol=…`, not hash `#/stock/…`.
- **Promoted to tester.md:** no

### 2026-07-16 — IBKR active-tab L1 streaming scoped verify

- **Scope:** `scanner_l1` / HOD active quota / ticks / reprice / discovery + frontend `useScannerPriceStream` / `scanAge` + `tsc --noEmit`.
- **Commands:** backend pytest (8 files) → **49 passed**; vitest → **8 passed** (2 files); `npx tsc --noEmit` → PASS. Live: `/api/health` up; `/api/ibkr/status` `connected:true` (live gateway).
- **Result:** PASS (unit/typecheck). Live L1 behavior not claimed — needs backend restart evidence + WS `price_patch` observation.
- **Learning:** Parent-scoped path `cd backend && pytest tests/...` works; keep repo-root form as default in tester.md.
- **Promoted to tester.md:** no

### 2026-07-16 — Phase G2 Hotkey Manager UI browser verify

- **Scope:** Settings → Hotkeys DAS manager (import/export/help/safety).
- **Commands:** `npm run test -- src/hotkeys src/components/SettingsWorkspace.test.tsx` → 21 passed; `npm run build` → PASS; agent-browser on `http://localhost:5173`.
- **Result:** PASS (all 8 checklist items)
- **Learning:** Servers already up; Export file download capture flaky in agent-browser headless — use serialize + localStorage evidence.
- **Promoted to tester.md:** yes — hotkeys routing row

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
