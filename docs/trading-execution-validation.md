# Trading execution validation (ADR 007)

> **Date:** 2026-07-17  
> **Scope:** Centralize every broker mutation behind one measured path; prove safety and paper/synthetic latency. **No live orders.**  
> **ADR:** `architecture/decisions/007-centralized-trading-execution.md`  
> **Canvas:** `agent-execution.canvas.tsx`

## Verdict: **Continue** (architecturally ready for a separately approved one-share live probe)

| Criterion | Result |
|-----------|--------|
| Single entry path (`execution.service.execute`) | Pass |
| Duplicate / concurrent idempotency | Pass (unit) |
| Account / risk / live-unconfirmed gates | Pass (unit) |
| Persist-before-send | Pass (unit) |
| Callback ack ≠ `PendingSubmit`; fill correlation | Pass (unit) |
| Reconnect telemetry handlers attach once per IB instance | Pass (unit) |
| Slow ack cannot hold the send lock / block urgent cancel | Pass (unit) |
| Cross-boot monotonic deltas excluded after schema migration | Pass (unit) |
| Paper/live same code path; only gates/credentials differ | Pass (unit) |
| AST: no production `placeOrder`/`cancelOrder` outside adapter | Pass |
| Synthetic p95 receive→ack ≤ 250 ms | **Pass** (56.0 ms @ 20 place + 20 cancel rows) |
| Paper Gateway p95 | Not run this session (needs logged-in paper Gateway + `--confirm-paper-orders`) |
| Live fill / slippage parity | **Not claimed** — IBKR paper fills are simulator-based |

**Still NO-GO for `auto_live`.** This proof does not unlock live money.

## Before / after path map

| Caller | Before | After |
|--------|--------|-------|
| Manual UI `POST /api/ibkr/order` | `ibkr.orders.place_order` (bypassed risk) | `execute(place, source=manual, skip_risk)` |
| Manual cancel | `orders.cancel_order` | `execute(cancel)` |
| Price replace | Missing | `PATCH /api/ibkr/order/{id}` → `execute(replace)` |
| Staged approve / auto_paper | `place_bracket_order` via executor | `execute(bracket)` + idempotency key |
| Kill / cancel-working / flatten | Direct cancel/place | `execute` with `source=kill\|flatten` |

## Stage latency (synthetic, 2026-07-23)

Command: `py -3 tools/execution_latency_probe.py --confirm-paper-orders --synthetic --samples 20`

| Stage | p50 (ms) | p95 (ms) | max (ms) |
|-------|----------|----------|----------|
| Validation | 21.8 | 23.9 | 25.4 |
| Broker sent | 31.7 | 34.5 | 37.4 |
| Broker ack | 52.6 | **56.0** | 57.2 |
| Send → synthetic fill | 32.4 | 35.4 | 37.4 |
| Ack → synthetic fill | 11.9 | 13.3 | 14.2 |

SLA target: p95 ack ≤ 250 ms (excludes fill). Every probe run has a unique
idempotency prefix, so old benchmark rows cannot enter the current summary.

## Process-local operation metrics

- `GET /api/metrics/ops` exposes bounded p50/p95/p99/max/count/error-count
  snapshots from `metrics.op_metrics`.
- Measurements use `perf_counter_ns` only, remain in memory, and issue no new
  broker or network requests.
- Market-data operations and inbound HTTP/WebSocket timing are intentionally
  left for their owning instrumentation slice; the endpoint reports only
  operations that have actually recorded samples.

## How to re-run paper Gateway probe

1. Log into IB Gateway **paper**, `spend_status=paper_armed`, `IBKR_LIVE_TRADING_CONFIRMED` unset.
2. `py -3 tools/execution_latency_probe.py --confirm-paper-orders --samples 50`
3. Probe cancels non-marketable 1-share limits; aborts if live confirmed.

## Limits

- Paper acknowledgment latency ≠ live exchange ack or fill quality.
- Manual place still skips Nova OS risk/concurrency (IBKR safety + account gates only) — intentional for the ticket UI.
- Fill poll (10s) remains a reconciliation backstop; primary fill mark is `execDetails` / `Filled` → ledger.

## Position qty + BuyingPower (2026-07-20)

| Check | Behavior |
|-------|----------|
| Long qty SSOT | `account.long_qty` ← `ib.positions()` only |
| Manual SELL / UI Flatten | `source=manual` → validate anti-short; unavailable → `POSITION_UNAVAILABLE`; verified flat → `NO_POSITION` |
| Nova OS flatten | Reconcile via `long_qty`; place `source=flatten` skips validate anti-short; abort on raise (no cancel-without-sell) |
| `/api/ibkr/positions` qty | From positions SSOT; MTM/PnL join from portfolio; no portfolio-only invent |
| Priced BUY + summary fail | Refuse `BUYING_POWER_UNKNOWN` (no fail-open) |
