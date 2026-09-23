# Maintainer memory (living)

Living knowledge for the Nova `maintainer` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/maintainer.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-20T14:52:00-04:00
source_revision: working-tree
result: FINDINGS
metrics:
  findings_total: 30
  findings_non_baseline: 27
  files_scanned: 806
  swallowed_exception: 0
  except_return_empty: 0
  executor_py_lines: 375  # under hard 400; prior baseline 494 retired
blockers: []
dashboard_freshness: refresh-required
notes: >
  AUDIT-ONLY dual-source position hunt: UI GET /api/ibkr/positions →
  get_portfolio()/ib.portfolio(); SELL gate + OS flatten →
  get_positions()/ib.positions(). Same-nature CRITICAL on OS flatten
  (empty positions → skip SELL + cancel protective legs). Fail-loud
  empty-on-error (bucket A) already closed; this is API split-brain.
```

Accepted-baseline *rationale* stays below; current measured line counts come from `maintainer_checks`.

---

## How to continue improving (for humans + agents)

Pick the next open item in **Backlog**, or after any significant change ask:

> Use the maintainer subagent to audit the repo.

---

## Accepted baselines

**(none over hard limit)** — `backend/strategy/executor.py` measured **375** lines (2026-07-20 dual-source audit); prior 494 baseline retired. Phase 12 deferral note still in `architecture/phase-12-executor-deferral.md` for placement-chain cohesion, not file-size.

Hard limits:

| Path | Limit |
|------|-------|
| `backend/main.py` | 200 |
| `frontend/src/App.tsx` | 150 |
| `frontend/src/index.css` | 50 |

`hod_momo.py` is no longer baselined (Phase 10 facade ≤400).

---

## Swallow heuristic policy

`check_swallowed_errors` targets **unlogged product-code silence** — a
read that can disguise a real market/account failure as empty success. It is
not a blanket "no except: pass anywhere" rule. Two exclusions:

1. **Path class exclusion:** `tools/` (one-off scripts) and test files never
   contribute `swallowed_exception` / `bare_except` / `except_return_empty`
   findings — they aren't the live read-path this heuristic protects, and
   flagging them only drowns the signal.
2. **Path allowlist** (`EXCEPT_RETURN_EMPTY_ALLOWLIST` /
   `SWALLOWED_EXCEPTION_ALLOWLIST` in `tools/maintainer_lib/swallow.py`):
   off the money path only -- modules whose empty-on-error behavior is
   deliberate and logged (disk/JSON loaders, already-loud-logged Alpaca
   snapshot/news degrades). Scanner discovery and IBKR positions/orders reads
   must never be added -- they raise or 503 instead (bucket A of the
   fail-loud remainder plan).
3. **Money path (2026-09-23, AGENTS.md §6.3):** in `execution/`, `ibkr/`,
   `practice/`, `sim/`, `kill_switch/`, `bot/` and `frontend/src/ibkr/` the
   kinds are `*_money` and fail `--gate`; file allowlists do not apply. A
   deliberately silent site (a timeout that ends a wait, idempotent
   `list.remove`, parse fall-through, `managedAccounts()` fail-closed) carries
   `# maintainer: allow-swallow <reason>` on its `except` line. Judge those
   reasons on every audit.

Do not add a new path to either allowlist without confirming the failure
mode still fails loud somewhere (a log line, a raised error, or a fail-closed
caller) — the allowlist is for reducing noise, not for hiding a new class of
silent empty-success.

## Suppressions

**(empty)** — see "Swallow heuristic policy" above for path-class exclusions,
which are heuristic scope decisions, not baseline suppressions of real findings.

---

## Backlog

- [ ] **Weekly automation** — optional Cursor Automation or scheduled CI job for `tools/maintainer_checks.py --json`
- [ ] **CI gate** — GitHub Actions job for maintainer scanner + ruff (warning-first)
- [ ] **Feed-mixing heuristics** — AST/grep for IBKR→Alpaca silent fallbacks
- [ ] **Cross-feature import cleanup** — migrate baseline-warned frontend deep imports to public barrels
- [ ] **Executor shared-state extract** — only after Phase 12 entry gate + security review
- [ ] **Emit key-file line counts from the tool** — `maintainer_checks.py` doesn't emit `main_py_lines`/`index_css_lines`/`app_tsx_lines`/`hod_momo_lines`/`executor_lines` as a JSON field; every memory snapshot update hand-transcribes them from separate ad hoc counts, which is how `index_css_lines: 18` drifted (copy-paste from `main_py_lines`) in the 2026-07-16 phase-13-close snapshot. Adding a `key_file_lines` dict to the JSON report would remove the manual step.
- [ ] **Fail-quiet heuristics** — extend `maintainer_checks` beyond `except: pass`: (a) `except …: return []/{}` in `backend/ibkr|scanner*|hod_momo*`; (b) `logger.*("%s", exc)` without `describe_exc`/`!r`/`exc_info`; (c) FE `.catch(() => {})` and bare `catch { // silent }`; (d) cache assign after empty discovery result without last-good guard.
- [ ] **Require `describe_exc` in hot loops** — integrity/HOD seed/enrichment/session loops still log `%s`, exc (blank for TimeoutError).
- [ ] **Position SSOT heuristic** — flag call sites that mix `get_positions`/`ib.positions` with `get_portfolio`/`ib.portfolio` for qty gates vs UI (dual-source / Flatten NO_POSITION class).

### Completed

- [x] 2026-07-16 — Pattern-Driven Architecture Phases 0–13 (CSS split, constants barrels, component/chart splits, runtime_state, scanner/ticker/depth/HOD facades, error visibility, executor deferral).
- [x] 2026-07-16 — Phase 1 gates: CSS hard limit, baseline growth, import_main + cross-feature warnings.
- [x] 2026-07-15 — Initial maintainer agent, memory, and deterministic scanner.

---

## Run log

<!-- RUN_LOG_START -->

### 2026-07-20 — Dual-source position / Flatten SELL refusal (AUDIT ONLY)

- **Scope:** Breadth hunt for portfolio-vs-positions split-brain before any validate.py symptom patch. No product edits.
- **Commands:** `py -3 tools/maintainer_checks.py --json` (30/27 non-baseline, 0 swallow); greps for get_positions/get_portfolio/ib.positions/ib.portfolio + FE flatten/exit paths.
- **Result:** FINDINGS — UI `/api/ibkr/positions` → `get_portfolio()`; validate `_position_qty` + executor_flatten `_actual_position_qty` → `get_positions()`. Manual Flatten false-refuses (safe). OS flatten with empty `positions()` success + real portfolio qty → skip SELL **and** cancel protective legs (CRITICAL naked-long). validate-only portfolio switch risks OVERSELL if portfolio inflated; must SSOT all consumers. `executor.py` now 375 lines (baseline 494 retired).
- **Learning:** Empty-on-error fail-loud does not close dual-IB-API divergence; successful empty `positions()` is still a lie when `portfolio()` has qty.
- **Files updated:** this memory only.

### 2026-07-20 — Fail-loud remainder: bucket A fix + bucket B policy

- **Scope:** Implemented `.cursor/plans/fail-loud_remainder_dad88d8f.plan.md`. Bucket A: IBKR positions/orders (`get_positions`/`get_portfolio`/`open_orders`/`closed_orders`) now raise `IbkrAccountError` on disconnect/API failure instead of returning `[]`; routes 503; `execution/validate._position_qty`, `strategy/executor._cancel_bracket_if_parent_unfilled` (kill switch), and `strategy/executor_flatten` (flatten preview/positions, protective-leg cancel) all fail closed on the new error instead of guessing "flat". Frontend `useIbkrAccount`/`useClosedOrders` + `PositionsPanel`/`WorkingOrdersPanel`/`ClosedOrdersPanel`/`ClosedOrdersModule` keep last-good rows and show an error line instead of wiping to `[]` or (for closed orders) substituting sample data on a genuine fetch failure. Bucket B: added the tools/tests path-class exclusion and the two named allowlists documented above; added matching tests.
- **Commands:** `pytest backend/tests/test_ibkr_account.py backend/tests/test_ibkr_orders.py backend/tests/test_orders_api_contract.py backend/tests/test_execution_validate.py backend/tests/test_executor.py` (all pass); `npx vitest run src/ibkr src/closed_orders` (137 pass); `py -3 -m pytest tools/test_maintainer_checks.py -q` (25 pass); `py -3 tools/maintainer_checks.py --json` (30 findings / 27 non-baseline, 0 swallow-heuristic noise).
- **Result:** FIXED — the real "flat account" lie (positions/orders exception → `[]` → executor/flatten/UI treating a transient IBKR read failure as "no position/order") is closed. Maintainer noise from `tools/`, tests, and 5 already-deliberate modules is gone; `check_swallowed_errors` no longer needs manual per-run triage of those paths.
- **Learning:** the more dangerous defect wasn't in `account.py`/`orders.py` themselves — it was downstream: `executor_flatten._actual_position_qty` returning `None` on a *failed read* was indistinguishable from `None` on a *genuinely flat position*, so a transient IBKR hiccup during a deliberate flatten would skip the market SELL **and** cancel the protective stop/target, leaving a real position naked. Fixed by making the read raise and having `flatten_positions` abort (not guess) on that specific exception.
- **Files updated:** `backend/ibkr/errors.py`, `backend/ibkr/account.py`, `backend/ibkr/orders.py`, `backend/routes/trading.py`, `backend/execution/validate.py`, `backend/strategy/executor.py`, `backend/strategy/executor_flatten.py`, `frontend/src/ibkr/useIbkrAccount.ts`, `frontend/src/ibkr/PositionsPanel.tsx`, `frontend/src/ibkr/WorkingOrdersPanel.tsx`, `frontend/src/ibkr/TradingTab.tsx`, `frontend/src/closed_orders/useClosedOrders.ts`, `frontend/src/closed_orders/ClosedOrdersModule.tsx`, `frontend/src/closed_orders/ClosedOrdersPanel.tsx`, `tools/maintainer_checks.py`, `tools/test_maintainer_checks.py`, this memory, `CHANGELOG.md`, `PROBLEM_LOG.md`. Dashboard not refreshed this pass (no line-count/phase change to `agent-maintainer.canvas.tsx`).

### 2026-07-20 — Full fail-quiet / silent-error audit

- **Scope:** Global silent-failure audit prioritized on scanner/IBKR/HOD/trading. Deterministic scan + targeted greps; no product edits.
- **Commands:** `py -3 tools/maintainer_checks.py --json` (exit 0, 36 findings / 7 swallows); `pytest tools/test_maintainer_checks.py -q` (16 pass, 1 unrelated index.css assertion fail); multiline greps for `return []`/`pass` after except; FE `.catch(()=>{})` inventory.
- **Result:** FINDINGS — bridge gapper wipe already fixed; remaining P0 is IB-level `scan_symbols`/`snapshot_quotes` failure collapsing to `[]` then overwriting caches; asymmetric movers wipe; HOD seed wipe on empty; blank `%s` TimeoutError logs in loops; FE promise swallows; maintainer tool gaps documented in backlog.
- **Learning:** `except: pass` is the minority class. The wipe pattern is `failure → empty collection → assign cache`. `ibkr.errors.describe_exc` is the existing fix pattern for blank TimeoutError — underused outside chart_bars/bridge.
- **Files updated:** this memory only. Dashboard not refreshed (audit report to parent).

### 2026-07-18 — Danger sniff (secrets / swallow / order path)

- **Scope:** Secrets + danger only (Daddy parallel with security vulnerability audit). Skipped file-size triage, pip_audit, npm audit.
- **Commands:** `py -3 tools/maintainer_checks.py --json` (exit 0); `check_secrets`/`check_swallowed_errors` direct; `ruff --select BLE,TRY203,S105,S106,S107`; complementary greps for placeOrder / key assigns; `git check-ignore .env`.
- **Result:** FINDINGS (danger) — 0 `secret_pattern` in scanned source; 4 `swallowed_exception` (1 production-relevant: `scanner_l1.py:181`); order send confined to `ibkr/orders.py` via safety gate; `.env` ignored/untracked.
- **Learning:** Maintainer secret scanner does not read `.env` (correct — gitignored artifact). Local `.env` still holds live-shaped keys; hygiene note for humans only, never echo values. `scanner_l1` silent `except Exception: pass` around optional `hod_momo_active` import is a new swallow vs 2026-07-16 snapshot (was 1 → now 4).
- **Files updated:** this memory (Current snapshot + this entry). No product code. Dashboard not refreshed (parent/security parallel).

### 2026-07-16 — Dashboard reconciliation (post phase-13, HEAD 13e530f)

- **Scope:** Re-ran deterministic scan against current working tree (HEAD `13e530f`) to reconcile a stale/suspicious Current-snapshot capture (`captured_at 2026-07-16T14:20:00-04:00`, `source_revision phase-13-close`, `dashboard_freshness refresh-required`).
- **Result:** FINDINGS — 10 total / 6 non-baseline: `backend/hod_momo_active.py` 436>400, `frontend/src/constantGroups/chart_api.ts` 413>400, `frontend/src/constantGroups/market_ui.ts` 401>400, `frontend/src/ibkr/ManualOrderTicket.tsx` 331>300, `tools/sync_agent_surfaces.py` 401>400, 1 swallowed exception (`backend/ibkr/ticks.py:59`, benign `list.remove` `ValueError` swallow). `executor.py` baseline stable at 494. `hod_momo.py` (133 lines) and `main.py` (18 lines) well under limit.
- **Root cause of the wrong metrics:** No bug in `tools/maintainer_checks.py` — verified its `count_lines()` against direct measurement for `main.py`, `index.css`, `App.tsx`, `hod_momo.py`, `executor.py` and all matched. The prior snapshot's `index_css_lines: 18` was a manual data-entry error (duplicate of the adjacent `main_py_lines: 18` value, not a fresh recount) — `index.css` is actually 48 lines. `main_py_lines: 18` itself was coincidentally already correct: `main.py` had been refactored further than the last snapshot's author expected, down to an 18-line composition root delegating to `app_lifespan.py` / `app_routers.py`. Systemic cause: the tool doesn't emit these five convenience metrics itself, so every memory update requires hand-transcription — logged as a backlog item instead of editing the tool (outside this read-only auditor's remit).
- **Files updated:** this memory (Current snapshot + backlog + this entry), `agent-maintainer.canvas.tsx` (hand-written pill/stat/table figures reconciled to fresh scan; generated `AGENT_SNAPSHOT_MAINTAINER` block refreshed via `sync_agent_surfaces.py --write`). No product code touched; no PROBLEM_LOG entry added (no actual code/tool defect found, per self-annealing step 3 — root cause was a documentation data-entry error, not a build/runtime/logic failure).

### 2026-07-16 — Phase 13 program close

- **Scope:** Full maintainer + pytest 669 + Vitest 178 + build + Playwright 14.
- **Result:** FINDINGS — 3 non-baseline artifacts only (after sync_agent_surfaces trim); 0 swallowed exceptions; executor baseline intact.
- **Learning:** Windows console must stay ASCII in human reports; hod_momo baseline removed after Phase 10 facade.
- **Files updated:** this memory, `architecture/program-close-metrics.md`, roadmap status.

### 2026-07-16 — Phase 1 gates

- **Scope:** CSS hard limit, baseline growth, dependency warnings.
- **Result:** FINDINGS — index.css hard-fail until Phase 2.
- **Files updated:** `tools/maintainer_checks.py`, `tools/maintainer_lib/deps.py`.

<!-- RUN_LOG_END -->
