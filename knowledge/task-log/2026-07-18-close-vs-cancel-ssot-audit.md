# 2026-07-18 — Close vs Cancel SSOT audit (Closed Orders / flatten)

- **Status:** completed
- **Agents:** execution (daddy-orchestrated)
- **Domain:** trading execution / ADR 007
- **Related:** ADR 007 · WID-019 Positions · WID-020/026 Orders · prior cancel audits

## Task

Audit-only: what "Close" means in Nova vs cancel working orders; which gates/SSOT
widgets must use for Close/flatten affordances on a Closed Orders–style surface.

## Goal

Separate cancel vs flatten/exit paths with exact entrypoints; keep `auto_live`
NO-GO; recommend widget wiring without implementing product code.

## Why it mattered

Webull-parity Orders UI may label tabs "Closed" while operators still want a
"Close" / flatten control. Conflating cancel-working with position-exit would
route the wrong gate (CANCEL_GATE vs ORDERS_GATE) or the wrong Nova OS flatten.

## What we changed

- Audit only — no product / execution-pipe code.
- Promoted durable Close vs Cancel facts into `execution-memory.md`.
- Refreshed `agent-execution` canvas path notes + synthetic SLA snapshot.
- This task-log entry + INDEX row.

## How it works now

### Cancel (working / open order)

- SSOT: `execution.service.execute(operation="cancel")` → `CANCEL_GATE`
  (`assert_cancel_allowed`: IBKR_ENABLED + connected).
- Facades: `DELETE /api/ibkr/order/{id}`, `DELETE /api/ibkr/orders?symbol=`,
  hotkeys `cancel_symbol`, executor `_cancel_via_service`.
- Does **not** flatten a filled position.

### Close / exit position (System 2 discretionary)

- SSOT: `execute(operation="place", source="manual")` → `ORDERS_GATE` +
  account/position checks (`NO_POSITION` / `OVERSELL` for SELL).
- Facades: `POST /api/ibkr/order` via `placeIbkrOrder`; UI
  `TickerTradeActionBar` Close; Nova Actions `exit_pos` / `exit_pos_pct`
  (`runNovaAction` → same place path). Handles long→SELL and short→BUY.

### Nova OS deliberate flatten (Automation)

- `POST /api/strategy/executor/flatten` + typed `FLATTEN` token →
  `flatten_positions` → cancel legs (`source=flatten`) + market SELL
  (`execute(place, source="flatten")`). Tracked executor longs only;
  reconciles IBKR real qty. Not the per-symbol widget Close control.

### Closed Orders (history) vs Close button

- WID-020/026 history / "Closed" tabs are **display**; Close belongs on
  **Positions** (WID-019) or reuse Stock View / quick-bar `exit_pos`.
- Sample Working Orders mock must keep mutation handlers undefined.

## Why this approach

- **Chose** three labeled paths over one "Close no matter what" API: cancel,
  manual exit, and Nova OS flatten have different gates, qty sources, and
  protective-leg behavior.
- **Rejected** wiring widget Close to `flatten_positions` — typed token +
  all-tracked-longs semantics, not per-row position close.
- **Rejected** "no matter what" bypass of ORDERS_GATE / PIN / spend —
  cancel is intentionally softer; place/close must remain spend-gated.
- **Rejected** product implementation this turn — audit contract + daddy
  dispatch asked for report-only.

## Verification

- `py -3 -m pytest backend/tests/test_execution_service.py -q` → 17 passed
- `py -3 tools/execution_latency_probe.py --confirm-paper-orders --synthetic --samples 20` → SLA PASS p95 ack ~57.9 ms
- `py -3 tools/agent_contract.py` → PASS

## Follow-ups

- Docs/UML: cancel sequence still open; add **close/exit** sequence
  (UI/hotkeys → place+ORDERS_GATE; flatten → place source=flatten).
- Widgets: put Close on Positions; Closed/history tab read-only.
- Product (explicit ask): optional cancel-then-exit helper for brackets
  (manual Close today does not cancel protective legs).

## Keywords

close, flatten, cancel, exit_pos, ORDERS_GATE, CANCEL_GATE, ADR 007, WID-019, WID-020, auto_live
