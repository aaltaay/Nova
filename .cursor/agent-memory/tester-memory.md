# Tester memory (living)

Living knowledge for the Nova `tester` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/tester.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-24T01:45:00-04:00
source_revision: d06d2d0+local-wip
result: PASS
metrics:
  pytest_passed: 974
  vitest_passed: 454
  vitest_files: 108
  playwright_passed: 11
blockers:
  - "playwright: 3 e2e specs (baseline.spec.ts, workspace-context.spec.ts, level2-tape-modules.spec.ts) historically failed on Stock View header — not re-verified this run"
dashboard_freshness: clean
notes: "2026-07-24 final execution measurement WIP: focused pytest 60 and Vitest 23 pass; full pytest 974 pass with known TorchVision DLL diagnostic; full Vitest 108 files / 454 pass. Account → Latency browser fixture proves mixed-SLA suppression, population SLA rows, child-leg exclusion/slippage, clean console, and zero mutation requests. Tester fixed a concrete 407-line telemetry maintainer regression by extracting cached reconciliation mapping; execution-scope maintainer warning cleared. Full Playwright remains stale."
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
- [ ] **Expand routing table** — add rows for `backend/news*`, `backend/scanner*`, `backend/l2*`, `frontend/src/strategy/*`, `frontend/src/TickerChart*`, `frontend/src/workspace/*`, `frontend/src/closed_orders/*` (+ `closeFullPosition` / `test_closed_orders.py`), and `frontend/src/ibkr/orderQtyMath*` + `workingOrderCells*` + `backend/tests/test_open_orders_row.py` / `test_order_times.py` once those areas get touched often.
- [ ] **Ruff / backend lint gate** — if the repo adopts Ruff (or documents a preferred command), add it beside frontend `npm run lint`.
- [ ] **CI parity** — read `.github/workflows/*` and note any gates the local tester should mirror (matrix Python version, e2e on PR only, etc.).
- [ ] **Seed a golden browser path** — one short click-path (e.g. open Gappers → pick a symbol → Stock View) recorded here so UI verifies are consistent.
- [x] **Timeout defaults** — Vitest full suite ~11–16s wall (99/422, verbose) on this machine → `block_until_ms` ≥ 60000 is safe; pytest/playwright still TBD.
- [ ] **Promote top PROBLEM_LOG traps** — when a new test-infra trap appears 2+ times, add it to `tester.md` Known traps and check it off here.

### Completed

- [x] 2026-07-22 — Timeout defaults: Vitest full suite ~11–16s (99 files / 422 tests, verbose) recorded under pending facts + backlog checked off.
- [x] 2026-07-16 — Full gate refresh: 677 pytest / 223-of-224 Vitest (49 files) / 11-of-14 Playwright. Found 2 real (non-flaky) regressions in uncommitted `frontend/src/stock_view/` WIP — flagged in snapshot `blockers`, not fixed (out of tester scope).
- [x] 2026-07-15 — Continuity refresh: promoted test counts in `tester.md` to **562** backend / **131** Vitest (28 files) / **14** Playwright; backlog item left open for future drift checks.
- [x] 2026-07-15 — Verified commands, routing, traps, trading safety, flakiness, server lifecycle (initial specialize pass).
- [x] 2026-07-15 — Self-improvement protocol + this memory file.

---

## Learned facts (pending promotion)

Facts discovered in a run that are **not yet** in `tester.md`. After promoting into `tester.md`, delete the bullet here (or move to Completed note).

- **localhost:5173 ≠ Nova when Altay Studio is up:** On this machine `::1:5173` can be Altay Studio (jobfinder) while Nova Vite listens on `127.0.0.1:5173`. Prefer `http://127.0.0.1:5173` for browser verify; `localhost` may resolve to IPv6 and show the wrong app.
- **Stale uvicorn vs new routes:** After shipping a new FastAPI path, live `openapi.json` / curl 404 while `TestClient(main.app)` 200 means the running API process did not reload — not a code regression. Confirm with OpenAPI path list before FAIL-ing the feature.
- **WID-027 Vitest scope:** `src/closed_orders` + `closeFullPosition.test.ts` + `registry.test.ts` = **17** tests (widgets sometimes claim ~21 — recount with `--reporter=verbose`).
- **Vitest act() gate:** After `IS_REACT_ACT_ENVIRONMENT` setup (`frontend/src/testSetup/reactActEnvironment.ts` + `test.setupFiles`), prove with `npx vitest run --reporter=verbose` and grep for `not configured to support act` / `was not wrapped in act` / `An update to .* inside a test was not wrapped in act` — default reporter hides these on green runs (PROBLEM_LOG 2026-07-20 / 2026-07-22).
- **Full Vitest wall time (this machine):** ~11–16s for 99 files / 422 tests (`--reporter=verbose`).
- **Vite browser-module fixture identity:** dynamically importing a source path without its dev-server `?t=` suffix can create a second module instance. For a read-only browser timing fixture, import the exact loaded URL from `performance.getEntriesByType('resource')`.
- **Intentional browser 503 checks:** route-fulfilled 503s appear as console resource errors even when React handles them correctly. Record them as expected error-state evidence, then use a fresh fixture-only context to prove zero uncaught/page/React errors.

---

## Run log

Newest first. Keep entries short. Skip boring all-green scoped runs unless a command/path was corrected.

<!-- RUN_LOG_START -->

### 2026-07-24 — Final maintainer-fix verification

- **Scope:** Mixed benchmark SLA suppression, bracket leg attribution, cancel feedback/poll recovery, public execution-latency imports, dashboard semantics, and current API/browser schemas.
- **Commands:** focused pytest **60 passed**; full pytest **974 passed** (known TorchVision DLL diagnostic, exit 0); focused Vitest **23 passed**; full Vitest **108 files / 454 passed**; ESLint/build/Ruff/agent contract/diff check passed.
- **Concrete fix:** Maintainer found `execution/telemetry.py` at 407 lines. Extracted cached reconciliation evidence mapping to `execution/reconciliation.py`; focused 29 + final 60 + full 974 passed. Maintainer returned to the prior repository-wide 31/28 findings with no execution-scope file-size warning.
- **Browser/API:** Restarted tester-owned API only; Vite stayed running. Current GET schema includes `aggregate_scope`, `sla_status`, and `segments.fill_leg`. Fresh populated browser fixture showed suppressed aggregate SLA, population Pass/Insufficient rows, target child exclusion/slippage, 0 console/page errors, and 0 mutation requests.
- **Result:** PASS with known repository/environment warnings. No order/probe/env/gateway/gate/cadence change, commit, or push.
- **task_log:** existing aggregate `knowledge/task-log/2026-07-24-end-to-end-execution-measurement.md`
- **problem_log:** `2026-07-24 — Fill-leg telemetry pushed the execution callback owner over its file limit`
- **Promoted to tester.md:** no

### 2026-07-24 — End-to-end execution measurement + Account Latency

- **Scope:** Complete uncommitted ADR 007 execution measurement and Account → Latency dashboard; read-only APIs/browser only, no broker probe or mutation action.
- **Commands:** focused pytest **58 passed**; full pytest **972 passed** (known TorchVision DLL diagnostic, exit 0); focused Vitest **21 passed**; full Vitest **108 files / 452 passed**; ESLint/build/Ruff lint/agent contract passed. Maintainer strict scan remained findings (31/28, repository debt); optional Ruff format check reported 20 changed files would reformat.
- **Browser:** Fresh Playwright context with only two metric GETs intercepted; populated operations/hops/populations/provenance/exclusions + browser-local timing, loading/error/stale/reset warnings, rapid Account section switching. Final clean context: 0 console errors, 0 page errors, 0 mutation requests.
- **API restart:** Old :8000 process served the pre-segmentation schema; restarted only `run_api.py`, left Vite untouched, then both authorized GETs returned the current bounded schema (limit 500, no raw rows/account field).
- **Result:** PASS with known non-blocking repository/environment warnings. No product/test fix, order, env/gateway/gate/cadence change, commit, or push.
- **task_log:** existing aggregate `knowledge/task-log/2026-07-24-end-to-end-execution-measurement.md`
- **Promoted to tester.md:** no (two pending browser-harness facts)

### 2026-07-22 — Vitest act() environment warning fix verify

- **Scope:** Commits `ea85715` (IS_REACT_ACT_ENVIRONMENT setupFiles) + `f09985a` (WorkspaceContext deferred config under `act`).
- **Commands:** Spot-check 5 files → **31 passed**; full `npx vitest run --reporter=verbose` → **99 files / 422 passed** (exit 0).
- **Act warning counts:** `not configured to support act` = **0**; `was not wrapped in act` = **0**; `An update to … not wrapped in act` = **0**. No remaining act-related lines in verbose output.
- **Result:** PASS. Browser skipped (unit-infra only). No product edits, no orders, no commit.
- **task_log:** skipped (verify-only)
- **Promoted to tester.md:** no (pending fact + snapshot refresh)

### 2026-07-19 — Filled polish (tooltips) Open/Closed verify

- **Scope:** widgets title/tooltip polish on Filled/Remaining/Avg fill — `orderTableColumns`, `workingOrderCells`, `closedOrderCells` (+ panels/dock).
- **Commands:** Vitest 6 files → **34 passed**; `orderQtyMath` → **8 passed**; pytest orders L2 (contract + open row + times + closed) → **12 passed**.
- **Result:** PASS. Cell text + `title=` strings asserted (e.g. `35 of 100 shares filled`, Remaining working). No layout change; browser skipped (UI/API up). No orders placed.
- **Note:** prior run-log residual (remaining-null → "—") now covered — `workingOrderCells` has derive qty−filled when `remaining_qty` null.
- **task_log:** `knowledge/task-log/2026-07-19-filled-polish-tester-verify.md`
- **Promoted to tester.md:** no

### 2026-07-19 — Open/Closed order qty/price/time math verify

- **Scope:** orderQtyMath + working/closed order cells + open-order row mapping + order times (read-only review).
- **Commands:** Vitest 8 files → **38 passed**; `pytest tests/test_open_orders_row.py test_order_times.py test_closed_orders.py` (from `backend/`) → **9 passed**.
- **Result:** PASS (suites green). Residual: Remaining **column** still uses raw `remaining_qty` (`workingOrderCells.tsx` L71 → "—" on null) while Fill/actions use `remainingShares()` / `remainingSharesWhole()`. Avg fill is IB-only (`status.avgFillPrice`); Nova does not compute it.
- **Suggested next tests:** `workingOrderCells` remaining-null derives qty−filled; `test_open_orders_row` remaining=None when status.remaining missing.
- **Promoted to tester.md:** no (pending routing backlog already lists closed_orders)

### 2026-07-18 — Closed Orders widget (WID-027) scoped verify

- **Scope:** `closed_orders` slice, `GET /orders/closed`, Flatten via `closeFullPosition` → place/ORDERS_GATE; registry id.
- **Commands:** `pytest test_closed_orders.py + test_open_orders_row.py` → **5 passed** (3+2); Vitest closed_orders+closeFullPosition+registry → **17 passed**; `npm run build` → PASS. TestClient `/api/ibkr/orders/closed` → 200; live uvicorn OpenAPI missing path → 404 (stale process).
- **Result:** PASS with notes (unit/build/browser chrome). Safety: status `orders_enabled:false` / `spend_status:locked`; Flatten SPY disabled; `auto_live` still rejected in control_mode (code). No orders placed.
- **Browser:** Trading tab — CLOSED ORDERS heading, Modules “Closed Orders SIDE_PANEL”, Working Orders separate; console vite/HMR only.
- **Known cracks:** `sv-trading-lock` / Playwright Stock View header — not re-run; not WID-027 regressions.
- **Promoted to tester.md:** no (pending facts only)

### 2026-07-18 — Working Orders widget (WID-026) scoped verify

- **Scope:** widgets WorkingOrdersPanel + open-orders row fields + Trading highlight / Stock View rail.
- **Commands:** `pytest backend/tests/test_open_orders_row.py -q` → **2 passed**; `vitest` WorkingOrdersPanel + stockViewTerminal → **17 passed**; `npm run build` → PASS. Browser: Trading tab on `127.0.0.1:5173` (IBKR `connected:false`).
- **Result:** PASS (unit/build). Browser: Trading disconnect guide mounts; `working-orders-panel` / `trading-working-orders-host` absent by design until IBKR connected — not a Working Orders regression. Paper place skipped (`orders_enabled:false`, gateway live/disconnected). Fresh console after clear: no WorkingOrders / React crash errors.
- **Known cracks:** `sv-trading-lock` missing — this scoped `stockViewTerminal` run is green (test now expects lock testid null at L530); Playwright Stock View header crack not re-run (out of scope). Not claiming full-fleet crack clearance.
- **Learning:** agent-browser first `npx` can EBUSY on Windows binary copy; retry with `npx --yes agent-browser@0.32.2` worked. Working Orders host only renders inside `status.connected` Trading layout.
- **Promoted to tester.md:** no

### 2026-07-18 — Phase G3 Hotkeys / Nova Actions browser verify

- **Scope:** Settings → Hotkeys G3 UI + Stock View Trading quick-bar; no order clicks; servers already up.
- **Commands:** agent-browser on `http://127.0.0.1:5173` (not `localhost` — see pending fact). IBKR `/api/ibkr/status` → `connected:false`.
- **Result:** PASS — inactive DAS banner; Nova Actions table (6 defaults + Show button); Active Nova shortcuts (Automation six); Map dialog from temporary `CXL ALLSYMB` row (cancelled, no Create); Stock View `?view=stock&symbol=AAPL` quick-bar 5 buttons; console clean (vite/devtools only). Trading tab shows IBKR disconnected (no quick-bar there — expected).
- **Learning:** G3 quick-bar lives on Stock View rail (`TickerTradeActionBar`), not Trading-tab disconnect screen. Hotkeys Settings works without IBKR.
- **Promoted to tester.md:** no (pending: localhost vs 127.0.0.1 trap)

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
