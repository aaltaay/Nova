# ADR 007 — Centralized trading execution path

**Status:** Accepted · **Date:** 2026-07-17

## Context

Nova had a single IBKR broker adapter (`ibkr/orders.py`) but fragmented entry points: manual `/api/ibkr/order`, Nova OS `place_from_ticket`, flatten, and kill-switch cancels. Manual place skipped risk/concurrency/idempotency. Broker acknowledgment was not measured — local `orderId` assignment was treated as success. Before expanding the platform, we need one measured path that can answer whether safe architecture still meets a p95 ≤250 ms receive→ack budget (paper only; no live orders in this phase).

## Decision

1. **One service:** `backend/execution/service.py` exposes `execute(command) -> ExecutionReceipt`. Strategies, agents, scripts, and UI routes never call the broker SDK directly.
2. **One adapter:** Only `ibkr/orders.py` (implementing `ports.execution.ExecutionPort`) may call `ib.placeOrder` / `ib.cancelOrder`.
3. **Same path for paper and live:** Only Gateway account/port/credentials and safety gates differ. `auto_live` remains rejected.
4. **Stages are timed:** request received → validation → ledger persist → broker send → first real broker ack → fill. Fill is reported separately as send→fill and ack→fill, outside the ack SLA.
5. **Idempotency + lock:** SQLite unique `idempotency_key` plus an asyncio lock prevent duplicate broker sends and same-symbol conflicts. The lock covers reservation, validation, and the synchronous broker send only; broker acknowledgment waiting happens after release so a slow order cannot block urgent cancel/flatten sends.
6. **Replace is price-only:** side/symbol/qty immutable; implemented as IBKR modify via `placeOrder` on an existing order id.
7. **Monotonic clock scope is explicit:** each execution row stores the process boot/session identifier that produced its `perf_counter_ns` stamps. Ack/fill callbacks and latency rollups only combine stamps from the same identifier; migrated legacy rows without one are retained but excluded from monotonic deltas.
8. **End-to-end clocks stay in their domains:** optional browser evidence carries paired wall-clock and `performance.now()` stamps for the user action and request dispatch. Backend ingress carries paired UTC wall-clock and `perf_counter_ns` stamps. Nova may compute browser action→dispatch only from the two browser monotonic stamps, and backend ingress→validation/persist/send/ack/fill/response only from same-boot backend monotonic stamps. Browser and backend monotonic values are never subtracted. A browser-dispatch→backend-ingress wall delta is exposed only as clock-offset-plus-transport uncertainty, never as latency.
9. **Fill evidence is provenance-preserving:** bounded per-execution observations distinguish `execDetails`, `orderStatus`, and existing reconciliation-poll evidence. Each observation records callback receipt time, broker execution time when supplied, partial/complete state, price/size, and side-aware slippage when a reference price exists. Callback and poll evidence are not interchangeable, legacy values are not invented, and negative/cross-boot deltas are excluded with reasons.
10. **Metrics populations are explicit:** paper, live, benchmark/synthetic, operation, source, and fill provenance remain separately labeled in rollups. Percentiles always include sample counts and insufficiency state. Read APIs return bounded rows/segments and no account identifiers, secrets, or unbounded broker identifiers.
11. **Mixed populations cannot produce an aggregate SLA verdict:** normalized population (`live`, `paper`, `benchmark_paper`, `benchmark_synthetic`, or `unknown`) is the mixing authority. When more than one population is present, aggregate distributions remain available only as explicitly mixed diagnostics and aggregate `sla_pass` is null; dashboards must use the population segments for verdicts.
12. **Bracket legs retain identity:** parent, target, and stop watches carry their actual side, leg role, and known leg reference. Child-leg evidence remains auditable but is not eligible to update the parent execution's ack/fill stages or enter parent-entry fill/slippage aggregates. Unknown leg attribution is excluded rather than inferred.

## Consequences

- Thin HTTP routes and executor facades delegate to `execute()`.
- Local `PendingSubmit` / assigned order id is **not** acknowledgment; first non-PendingSubmit `orderStatus` (or `execDetails` when status is skipped) is.
- Paper proves structural/API latency; IBKR paper fills are simulated and do not prove live slippage.
- Live one-share probes require a separate explicit user approval phase.
- The browser/UI owner may add the optional client timing payload and render-complete stamp later. The backend contract deliberately stops at response-ready or an existing server event-emission hook; it does not pretend to measure frontend render or subtract clocks across hosts.
- Execution telemetry reuses existing IBKR callbacks and reconciliation loops. It does not add broker requests or increase polling cadence.

## Broker long qty SSOT (2026-07-20)

Anti-short / flatten sizing and Positions **qty** share one API: `ibkr.account.long_qty(symbol)` backed only by `ib.positions()` (sum same-symbol longs; raise `IbkrAccountError` on read failure). `GET /api/ibkr/positions` takes qty from that cache and joins mark/PnL from `ib.portfolio()` — never invents a long from portfolio-only rows. Validate maps read failure → `POSITION_UNAVAILABLE` (not `NO_POSITION`). UI Flatten stays `source="manual"` (anti-short on); Nova OS flatten place stays `source="flatten"` (reconcile via `long_qty` is the gate). Account summary reads raise on failure so LMT BUY cannot skip BuyingPower (`BUYING_POWER_UNKNOWN`).

## Rejected alternatives

- Separate paper vs live code paths
- Full order FSM / message bus before latency proof
- Blocking account-summary network refresh on every place (use cached account values; fail closed if incomplete)
- Validate/flatten qty from `ib.portfolio()` alone (false-allow short if portfolio high/stale)
- UI Flatten tagged `source="flatten"` to skip anti-short
