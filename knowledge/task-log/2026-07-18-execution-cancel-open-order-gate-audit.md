# 2026-07-18 — Execution cancel paths + open-order CANCEL_GATE SSOT audit

- **Status:** completed
- **Agents:** execution (daddy-orchestrated)
- **Domain:** trading execution / ADR 007
- **Related:** ADR 007 · `docs/trading-execution-validation.md` · WID-026 WorkingOrdersPanel

## Task

Audit-only: can Nova cancel pending and open/working orders today; does
open-order cancel have its own gate; is there a single source of truth?

## Goal

Answer the operator question with path evidence (routes, service, adapter,
UI, hotkeys) and name UML/docs gaps — no product code.

## Why it mattered

Stock View Open Orders (WID-026) and Phase G3 hotkeys both surface cancel.
Operators need confidence that cancel is not ad-hoc and that open-order
cancel is gated separately from place/spend.

## What we changed

- Audit only — no product code.
- Updated execution agent verified probe command (`--confirm-paper-orders`
  required even for `--synthetic`).
- Logged findings in `execution-memory.md`; refreshed `agent-execution` canvas
  cancel path + CANCEL_GATE note.

## How it works now

- **Broker cancel SSOT:** `execution.service.execute(operation="cancel")` →
  ledger → `broker_send` → `ibkr.orders.cancel_order` → `ib.cancelOrder`.
- **Cancel gate (own path):** `validate.validate_command` →
  `assert_cancel_allowed` → reason `CANCEL_GATE` (IBKR_ENABLED + connected
  only). Place uses separate `assert_orders_allowed` / `ORDERS_GATE`
  (orders-enabled + live-confirm).
- **UI:** Trading + Stock View → `DELETE /api/ibkr/order/{id}` → `execute`.
  Sample mock dock sets `onCancelOrder=undefined` (UI-only; no broker).
- **Hotkeys G3:** `cancel_symbol` → `DELETE /api/ibkr/orders?symbol=` →
  per-order `execute(cancel)` (not a second broker SDK path).
- **Nova OS:** kill / cancel_working_entry / flatten cancel via
  `_cancel_via_service` → `execute`. Staged tickets are **reject**, not
  broker cancel.
- **auto_live:** still NO-GO.

## Why this approach

- **Chose** code+test trace over implementing a new gate: CANCEL_GATE already
  exists and is distinct from ORDERS_GATE; the gap is documentation/UML and
  ledger `source=` honesty for cancel_working, not a missing cancel API.
- **Rejected** claiming UI “bypasses” execution: thin HTTP to
  `/api/ibkr/order` is the ADR-intended facade; only `ib.cancelOrder` in
  `ibkr/orders.py` is forbidden elsewhere (AST-covered).
- **Rejected** conflating staged-ticket reject with open-order cancel — different
  SSOT layers (confirm queue vs IBKR openTrades).

## Verification

- `py -3 -m pytest backend/tests/test_execution_service.py -q` → 17 passed
- `py -3 tools/execution_latency_probe.py --confirm-paper-orders --synthetic --samples 20` → SLA PASS p95 ack ~63.8 ms
- `py -3 tools/agent_contract.py` → PASS

## Follow-ups

- Docs/UML: sequence diagram for cancel callers → CANCEL_GATE → adapter.
- Ledger: `cancel_working_entry` should pass `source="cancel_working"` (today uses `"kill"`).
- Optional: align hotkey PIN/spend UI gates with bare DELETE cancel UX docs.

## Keywords

cancel, open orders, CANCEL_GATE, ADR 007, WorkingOrdersPanel, hotkeys cancel_symbol, SSOT
