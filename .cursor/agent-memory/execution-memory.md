# Execution Auditor memory (living)

Living knowledge for the Nova `execution` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/execution.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-20T19:35:00Z
source_revision: local-wip
result: paper-place-order-confidence-pass
metrics:
  unit_tests: 49_passed_execution_plus_safety
  validate_tests: 8_passed
  agent_contract: pass
  live_status: paper_armed_connected
blockers: []
dashboard_freshness: clean
```

Machine-readable block only. Update after material runs. Do not duplicate mutable truth that lives in canonical domain sources.

---

## Durable cancel / gate facts (promoted)

- **Broker cancel SSOT:** all production cancels → `execution.service.execute(operation="cancel")` → `broker_send` → `ibkr.orders.cancel_order` → `ib.cancelOrder`. AST forbids other `cancelOrder` call sites.
- **Dedicated cancel gate:** `validate.validate_command` uses `assert_cancel_allowed` → reason code `CANCEL_GATE` (IBKR_ENABLED + connected). Place/replace use `assert_orders_allowed` / `ORDERS_GATE` (also orders-enabled + live-confirm). Cancel skips BuyingPower / position checks.
- **Callers (facades, not second SSOTs):** `DELETE /api/ibkr/order/{id}`, `DELETE /api/ibkr/orders?symbol=`, hotkeys `cancel_symbol`, executor kill / cancel_working_entry / flatten via `_cancel_via_service`.
- **Not broker cancel:** Nova OS staged-ticket `reject` (confirm queue). Sample Working Orders mock disables cancel (`onCancelOrder=undefined`).
- **UML gap:** no sequence diagram for cancel → CANCEL_GATE; ADR 007 + validation path table only.
- **Ledger crack:** `cancel_working_entry` cancels with `source="kill"` instead of `source="cancel_working"`.
- **Probe CLI:** `--confirm-paper-orders` is required even with `--synthetic`.

---

## Durable close / flatten facts (promoted)

- **Cancel ≠ Close.** Cancel removes a **working order**. Close/exit places an opposing order to flatten a **filled position**.
- **System 2 Close SSOT:** `POST /api/ibkr/order` → `execute(place, source="manual")` → `ORDERS_GATE` + `check_account_and_position` (`NO_POSITION` / `OVERSELL` for SELL). UI: `TickerTradeActionBar` Close; Nova Actions `exit_pos` / `exit_pos_pct` via `runNovaAction` → `placeIbkrOrder` (MKT). Long→SELL, short→BUY.
- **Nova OS flatten SSOT:** `POST /api/strategy/executor/flatten` + typed `FLATTEN` → `flatten_positions` → cancel bracket legs (`execute(cancel, source=flatten)`) then market SELL (`execute(place, source=flatten)`). Reconciles IBKR real qty; tracked **longs** only. Not the per-symbol widget Close.
- **Webull mapping:** Positions Close → WID-019 / `exit_pos`. Working cancel → WID-026. Closed/history tabs (WID-020) are **display-only** — do not put flatten on history rows.
- **"No matter what" is forbidden:** Close still needs ORDERS_GATE + UI PIN/spend; only cancel is softer (CANCEL_GATE).
- **Gap:** manual Close does **not** cancel protective bracket legs; Nova OS flatten does. No close/exit UML yet (pair with cancel UML backlog).

## Durable position-qty SSOT facts (promoted 2026-07-20)

- **Dual IB caches:** UI `GET /api/ibkr/positions` → `get_portfolio()` → `ib.portfolio()`. Safety long-qty → `get_positions()` → `ib.positions()` (`validate._position_qty`, `executor_flatten._actual_position_qty` / preview). Same symbol can be in one cache and not the other.
- **UI Flatten always `source="manual"`** — never `source="flatten"`. Do **not** “fix” via UI `source=flatten` (skips `NO_POSITION`/`OVERSELL`).
- **Symptom paths:** Flatten / Close / `exit_pos` / `%` sells size from portfolio FE rows then gate on positions; `cancel_and_exit` can cancel then `NO_POSITION`; Nova OS flatten on empty `positions()` can skip-sell **and** cancel legs (naked) for tracked symbols.
- **Third source (claim):** `_open_positions` / recovery — flatten iteration + concurrency; kill cancels only, never sells.
- **Failed vs empty:** `IbkrAccountError` fail-closed; validate still surfaces unknown as `NO_POSITION` (need `POSITION_UNAVAILABLE`). FE `useIbkrAccount` last-good portfolio vs live gate.
- **Qty helper gaps:** first matching symbol row only (no sum); no conId/secType key.
- **Rejected:** validate-only→portfolio; UI `source=flatten`; max(caches); FE-only trust.
- **Accepted (plan):** `account.long_qty` / `net_long_qty` on **`ib.positions()`** (+ subscribe/refresh); `/positions` qty from same helper; portfolio PnL join only; wire validate + flatten + preview together.

---

## How to continue improving

> Use the execution subagent to audit trading execution

Or:

> Improve the execution agent — work the next backlog item in `.cursor/agent-memory/execution-memory.md`.

Durable facts get **promoted into `execution.md`**. Run history and open ideas stay **here**.

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [ ] Product (explicit ask): unify long-qty SSOT — `account.long_qty` + UI `/positions` qty from `get_positions()`; portfolio for PnL only; wire validate + flatten + preview; regression tests for portfolio≠positions.
- [ ] Docs/UML: add **close/exit** sequence (UI/`exit_pos` → place+ORDERS_GATE; flatten → place source=flatten + leg cancels).
- [ ] Docs/UML: add cancel sequence (callers → CANCEL_GATE → adapter) to ADR 007 or `docs/trading-execution-validation.md`.
- [ ] Product (explicit ask): `cancel_working_entry` → `source="cancel_working"` for ledger honesty.
- [ ] Product (explicit ask): optional cancel-then-exit helper if widgets need bracket-safe Close (manual path today leaves legs).
- [x] Position qty dual-source / split-brain audit (portfolio UI vs positions gates).
- [x] Close vs Cancel / flatten SSOT audit for Closed Orders widget dispatch.
- [x] First real audit run: pytest + synthetic latency probe; cancel-path SSOT answered.
- [ ] Confirm paper Gateway probe still deferred and documented as such.
- [x] Continuity rule created (execution-continuity.mdc).

### Completed

- [x] 2026-07-18 — Close vs Cancel / flatten SSOT (daddy Closed Orders widget dispatch).
- [x] 2026-07-18 — Cancel/open-order gate audit (daddy dispatch).
- [x] 2026-07-18 — Agent scaffolded via `tools/create_nova_agent.py`.

---

## Run log

Newest first. Keep entries short.

<!-- RUN_LOG_START -->

### 2026-07-20 — Paper "Place an order" confidence audit

- **Scope:** Live `/api/ibkr/status` + ManualOrderTicket → execute → paper pin; Flatten source=manual + long_qty after 40ce60a. Audit-only.
- **Commands:** GET status (paper_armed, connected); pytest `test_execution_service`+`test_ibkr_safety` 49 pass; `test_execution_validate` 8 pass; `agent_contract` PASS. No orders placed.
- **Result:** paper-place-order-confidence-pass — yes for paper while status stays as reported; live needs mode+accounts+LIVE_TRADING_CONFIRMED; auto_live NO-GO.
- **Learning:** spend_status paper_armed is env-derived; hard paper pin still refuses non-DU/DF even if UI looks armed. Self-heal live→paper was active on this host.
- **Files updated:** this memory only (no product code).

### 2026-07-20 — Position qty dual-source / split-brain audit

- **Scope:** Full inventory of long-qty / oversell / flatten size readers; SSOT for parent plan.
- **Commands:** pytest `test_execution_service` + `test_execution_validate` → 19 passed; `agent_contract` PASS. No orders; no product code.
- **Result:** position-qty-dual-source-audit — UI portfolio vs gate/flatten positions(); reject validate-only + UI source=flatten; recommend account.long_qty SSOT + POSITION_UNAVAILABLE.
- **Learning:** `cancel_and_exit` sharpest UX hazard; Nova OS flatten skip-sell+leg-cancel is sharpest safety hazard under dual cache.
- **Files updated:** this memory; agent-execution canvas; task-log `2026-07-20-flatten-position-qty-dual-source-audit.md`.

### 2026-07-18 — Close vs Cancel / flatten SSOT (Closed Orders widget)

- **Scope:** Separate cancel vs position Close vs Nova OS flatten; widget wiring.
- **Commands:** pytest 17 pass; probe synthetic 20 samples SLA pass (~57.9 ms p95); agent_contract PASS.
- **Result:** close-vs-cancel-audit-pass — widget Close → exit_pos/place+ORDERS_GATE; history tab read-only; flatten ≠ per-symbol Close; auto_live NO-GO.
- **Learning:** Manual Close does not cancel bracket legs; flatten does. "no matter what" must not weaken ORDERS_GATE.
- **Files updated:** this memory; canvas; task-log.

### 2026-07-18 — Cancel + open-order CANCEL_GATE audit

- **Scope:** Trace all cancel paths; answer pending vs open/working; gate/SSOT/UML.
- **Commands:** `pytest test_execution_service.py` 17 pass; probe synthetic 20 samples SLA pass (~63.8 ms p95); `agent_contract` PASS.
- **Result:** cancel-path-audit-pass — open/working cancel wired via execute+CANCEL_GATE; sample mock disables cancel; staged reject ≠ broker cancel.
- **Learning:** Probe requires `--confirm-paper-orders` even for synthetic; cancel_working uses source=kill; no cancel UML.
- **Files updated:** `execution.md` probe cmd; this memory; canvas; task-log.

### 2026-07-18 — Agent install

- **Scope:** Meta — scaffold execution via agent contract system.
- **Result:** install
- **Learning:** Follow docs/agent-operations.md remaining human steps.
- **Files updated:** `execution.md`, `execution-memory.md`, registry entry.

<!-- RUN_LOG_END -->
