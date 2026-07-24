# Trading execution validation (ADR 007)

> **Date:** 2026-07-24
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
| Browser/backend clock domains never cross-subtracted | Pass (unit + route) |
| Partial → complete fill evidence + side-aware slippage | Pass (unit) |
| Bracket target/stop cannot alter parent entry metrics | Pass (unit) |
| `execDetails` / `orderStatus` / reconciliation provenance | Pass (unit) |
| Cancel/replace reused orderId cannot reuse an earlier ack | Pass (unit) |
| Paper/live same code path; only gates/credentials differ | Pass (unit) |
| Mixed synthetic/paper benchmark aggregate SLA suppressed | Pass (unit) |
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
- The endpoint also includes a bounded `execution` snapshot identical to
  `GET /api/ibkr/execution-latency`. Execution populations are segmented by
  paper/live/benchmark-paper/benchmark-synthetic class, operation, source,
  fill provenance, and bracket leg.
- `mixed_population` is computed from normalized population, not mode/source.
  When populations mix, aggregate distributions are labeled
  `aggregate_scope=mixed_diagnostic_only`, `aggregate_warning` is populated,
  and aggregate `sla_pass` is null. Each `segments.population.*.sla` owns its
  single-population verdict and reports insufficient samples explicitly.

## End-to-end measurement contract (2026-07-24)

Optional manual-order and replace bodies accept:

```json
{
  "reference_price": 10.05,
  "client_timing": {
    "action_wall_ms": 1784870000000.0,
    "action_performance_ms": 1250.25,
    "request_wall_ms": 1784870000012.0,
    "request_performance_ms": 1262.25
  }
}
```

Cancel routes accept the same four values as headers:
`X-Nova-Action-Wall-Ms`, `X-Nova-Action-Performance-Ms`,
`X-Nova-Request-Wall-Ms`, and `X-Nova-Request-Performance-Ms`.

- Browser action → request is computed only from the two browser
  `performance.now()` values.
- Backend ingress → validation/persist/send/ack/first fill/complete fill/
  handler-response-ready is computed only from same-boot `perf_counter_ns`.
- Browser and backend monotonic clocks are never subtracted. The paired wall
  observation is labeled `latency_usable=false` because it includes wall-clock
  offset plus transport.
- `measurement.frontend_render` remains `not_measured_by_backend`, owner
  `widgets`. Account → Latency now records request-dispatch → response and
  response → second-animation-frame locally in the same browser
  `performance.now()` domain; it does not write a browser paint timestamp into
  the backend or manufacture a cross-host monotonic duration.
- The backend response mark means handler response-ready, not socket flush,
  paint, or user-visible render. There is no existing execution WebSocket
  emission hook, so no WS timestamp is invented.

`GET /api/ibkr/execution/{execution_id}` returns bounded `fill_evidence`,
`first_fill`, and `complete_fill`. Each evidence row may include:

- `provenance`: `execDetails`, `orderStatus`, or `reconciliation_poll`
- `leg_role`: `single`, `parent`, `target`, `stop`, or legacy/other role
- `evidence_side`, `reference_source`, and `aggregate_eligible`
- `fill_state`: `partial` or `complete`
- `exchange_ts_utc` when IBKR supplied an aware timestamp
- backend callback wall/perf stamps
- price, shares, cumulative/remaining shares, average fill
- requested/reference price and BUY/SELL side-aware slippage per share, total,
  and bps
- exchange→callback wall observation only when non-negative, with an explicit
  clock-sync limitation; invalid/negative values carry an exclusion reason

Evidence is capped at 64 observations per execution. Latency APIs cap reads at
500 executions and return p50/p95/p99/max/count/error-count, sample sufficiency,
and excluded counts/reasons. Legacy/cross-boot/negative values stay stored but
do not enter monotonic distributions.

For brackets, the parent entry is BUY with the entry reference; target and stop
legs are SELL with their own known target/stop references. Child evidence is
returned for audit and under `segments.fill_leg`, but `aggregate_eligible=0`:
it cannot set parent ack/fill stages, become `first_fill`/`complete_fill`, or
enter parent fill/slippage/provenance aggregates. Evidence migrated without
leg identity is marked `legacy_unknown` and excluded rather than inferred.

No broker request, subscription, or polling cadence was added. Reconciliation
provenance is attached only while mapping already-cached `Trade.fills`.

Verification after maintainer correctness fixes: focused
execution/order/metrics run **102 passed**; complete backend suite
**974 passed**; changed-file Ruff and agent contract passed. No paper/live
latency probe or order-producing command was run.

Frontend verification: focused body-outcome/dashboard Vitest **39 passed**;
complete frontend **458 passed**; ESLint and production build/typecheck passed. The
dashboard uses deterministic populated payloads in
`frontend/src/execution_latency/testFixtures.ts`; browser verification is a
tester handoff after the local API is restarted.
The current frontend renders `aggregate_warning`, suppresses mixed aggregate
SLA, assigns Pass/Fail/Insufficient only to population rows, and displays
`segments.fill_leg` slippage with child target/stop legs labeled excluded from
parent aggregates. Account and Stock View cancel failures use Nova's danger
alert and always refresh account polling afterward. All sibling features
consume timing/dashboard contracts through `execution_latency/index.ts`.
Place, per-order cancel, and cancel-all parse the JSON result before completing
browser timing. Outcome is successful only when HTTP transport succeeds and
`body.ok !== false`; handled HTTP 200 rejections, non-2xx responses, malformed
JSON, and network failures complete as browser errors. Flatten, Fill now, and
Nova Actions delegate to those same clients and therefore inherit the rule.

## How to re-run paper Gateway probe

1. Log into IB Gateway **paper**, `spend_status=paper_armed`, `IBKR_LIVE_TRADING_CONFIRMED` unset.
2. `py -3 tools/execution_latency_probe.py --confirm-paper-orders --samples 50`
3. Probe cancels non-marketable 1-share limits; aborts if live confirmed.

## Limits

- Paper acknowledgment latency ≠ live exchange ack or fill quality.
- Manual place still skips Nova OS risk/concurrency (IBKR safety + account gates only) — intentional for the ticket UI.
- Fill poll (10s) remains a reconciliation backstop; primary fill mark is `execDetails` / `Filled` → ledger.
- Browser wall clocks and IBKR exchange timestamps require external clock
  synchronization before wall observations can be interpreted as transport
  delay.

## Position qty + BuyingPower (2026-07-20)

| Check | Behavior |
|-------|----------|
| Long qty SSOT | `account.long_qty` ← `ib.positions()` only |
| Manual SELL / UI Flatten | `source=manual` → validate anti-short; unavailable → `POSITION_UNAVAILABLE`; verified flat → `NO_POSITION` |
| Nova OS flatten | Reconcile via `long_qty`; place `source=flatten` skips validate anti-short; abort on raise (no cancel-without-sell) |
| `/api/ibkr/positions` qty | From positions SSOT; MTM/PnL join from portfolio; no portfolio-only invent |
| Priced BUY + summary fail | Refuse `BUYING_POWER_UNKNOWN` (no fail-open) |
