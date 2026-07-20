# ADR 007 — Centralized trading execution path

**Status:** Accepted · **Date:** 2026-07-17

## Context

Nova had a single IBKR broker adapter (`ibkr/orders.py`) but fragmented entry points: manual `/api/ibkr/order`, Nova OS `place_from_ticket`, flatten, and kill-switch cancels. Manual place skipped risk/concurrency/idempotency. Broker acknowledgment was not measured — local `orderId` assignment was treated as success. Before expanding the platform, we need one measured path that can answer whether safe architecture still meets a p95 ≤250 ms receive→ack budget (paper only; no live orders in this phase).

## Decision

1. **One service:** `backend/execution/service.py` exposes `execute(command) -> ExecutionReceipt`. Strategies, agents, scripts, and UI routes never call the broker SDK directly.
2. **One adapter:** Only `ibkr/orders.py` (implementing `ports.execution.ExecutionPort`) may call `ib.placeOrder` / `ib.cancelOrder`.
3. **Same path for paper and live:** Only Gateway account/port/credentials and safety gates differ. `auto_live` remains rejected.
4. **Stages are timed:** request received → validation → ledger persist → broker send → first real broker ack → fill (fill reported separately from the ack SLA).
5. **Idempotency + lock:** SQLite unique `idempotency_key` plus an asyncio lock prevent duplicate broker sends and same-symbol conflicts.
6. **Replace is price-only:** side/symbol/qty immutable; implemented as IBKR modify via `placeOrder` on an existing order id.

## Consequences

- Thin HTTP routes and executor facades delegate to `execute()`.
- Local `PendingSubmit` / assigned order id is **not** acknowledgment; first non-PendingSubmit `orderStatus` (or `execDetails` when status is skipped) is.
- Paper proves structural/API latency; IBKR paper fills are simulated and do not prove live slippage.
- Live one-share probes require a separate explicit user approval phase.

## Broker long qty SSOT (2026-07-20)

Anti-short / flatten sizing and Positions **qty** share one API: `ibkr.account.long_qty(symbol)` backed only by `ib.positions()` (sum same-symbol longs; raise `IbkrAccountError` on read failure). `GET /api/ibkr/positions` takes qty from that cache and joins mark/PnL from `ib.portfolio()` — never invents a long from portfolio-only rows. Validate maps read failure → `POSITION_UNAVAILABLE` (not `NO_POSITION`). UI Flatten stays `source="manual"` (anti-short on); Nova OS flatten place stays `source="flatten"` (reconcile via `long_qty` is the gate). Account summary reads raise on failure so LMT BUY cannot skip BuyingPower (`BUYING_POWER_UNKNOWN`).

## Rejected alternatives

- Separate paper vs live code paths
- Full order FSM / message bus before latency proof
- Blocking account-summary network refresh on every place (use cached account values; fail closed if incomplete)
- Validate/flatten qty from `ib.portfolio()` alone (false-allow short if portfolio high/stale)
- UI Flatten tagged `source="flatten"` to skip anti-short
