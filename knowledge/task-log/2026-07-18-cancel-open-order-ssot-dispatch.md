# 2026-07-18 — Cancel open-order gate SSOT dispatch (execution + hotkeys)

- **Status:** completed
- **Agents:** daddy | execution | hotkeys
- **Domain:** execution | hotkeys
- **Related:** specialist logs `2026-07-18-execution-cancel-open-order-gate-audit.md`, `2026-07-18-hotkeys-cancel-ownership-audit.md` · ADR 007 · WID-026

## Task

User asked: can we cancel pending/open (working) orders; ensure open-order cancel has its own gate; confirm single source of truth (UML review).

## Goal

Audit-only daddy dispatch answering cancel capability, gate ownership, UML gaps, and one safe next step — no product code.

## Why it mattered

Stock View Open Orders (WID-026) and hotkeys both cancel; user needed confidence that broker cancel is not ad-hoc and that open/working cancel has a dedicated gate separate from place.

## What we changed

- Daddy parallel dispatch: `execution` + `hotkeys` (audit-only).
- Aggregate verdict for parent; no `backend/` / `frontend/` product edits from daddy.
- Specialists updated their own memories + task logs.

## How it works now

- **Broker SSOT:** all cancels → `execution.service.execute(operation="cancel")` → ledger → `broker_send` → `ibkr.orders.cancel_order`.
- **Cancel gate (own):** `validate.assert_cancel_allowed` / reason `CANCEL_GATE` (enabled + connected). Separate from place `ORDERS_GATE`.
- **UI row ✕:** `DELETE /api/ibkr/order/{id}` (Trading + Stock View when not sample mock).
- **Hotkeys:** only `cancel_symbol` → `DELETE /api/ibkr/orders?symbol=` (orchestration over same `execute`); panel cancel stays outside dispatcher.
- **Sample mock orders:** cancel disabled.
- **auto_live:** NO-GO.

## Why this approach

Parallel audit of execution (ADR 007 / gates) and hotkeys (Nova Action ownership) without implementers — avoids write conflicts and answers SSOT before any wiring change. Rejected routing panel ✕ through `runNovaAction` (keyboard dispatcher ≠ broker SSOT). Rejected inventing a second cancel path.

## Verification

- Execution: `pytest backend/tests/test_execution_service.py` 17 passed; latency probe SLA PASS; agent_contract PASS.
- Hotkeys: code/docs read (no product change).

## Follow-ups

1. **Docs (one step):** add cancel sequence UML to ADR 007 or `docs/trading-execution-validation.md` (UI / hotkeys / kill → `execute(cancel)` → `CANCEL_GATE` → adapter).
2. Optional product: ledger `source="cancel_working"` honesty; shared client cancel helper for PIN/spend parity (execution policy, not hotkeys ownership).

## Keywords

cancel, open orders, CANCEL_GATE, ADR 007, execute(cancel), WorkingOrdersPanel, cancel_symbol, WID-026, SSOT, daddy dispatch
