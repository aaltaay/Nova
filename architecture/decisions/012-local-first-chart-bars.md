# ADR 012 -- Local-first chart bars + paced IBKR historicals

**Status:** Accepted · **Date:** 2026-08-18
**Builds on:** [[010-ib-loop-isolation]] · [[005-frontend-feature-slices]]
**Incident:** Recurring "Chart bars timed out -- IBKR historical may be busy" (PROBLEM_LOG 2026-07-29, 2026-08-17, Quote Panel 2026-08-18)

## Context

Nova treated IBKR historicals as "one request at a time" and put that mutex on the same `cold_slot` as `snapshot_quotes` and completed-orders. A ticker click became a 25s-deadline pull behind HOD surge seed, enrichment snapshots, and other panes.

IB's documented limits are the opposite of that model: 50 simultaneous historical requests, 60 per 10 minutes, 6+ same-contract per 2 seconds, identical request within 15 seconds. Nova enforced a concurrency constraint IB does not have, and did not enforce the rate constraint it does. Every scheduling patch (TTL cache, client queue, detached fetch, 8x retry) left the click as a synchronous dependency of the broker.

## Decision

1. **Store-first HTTP.** `GET /api/ticker/{sym}/bars` reads `bars_store` (archive.db `bars_intraday` + coverage). It does not wait for `reqHistoricalData`. Empty store + IB ready returns 200 with `coverage.filling=true`. Empty store + Gateway down is still 503. No Alpaca fallback.

2. **Paint archived IBKR bars with coverage.** The UI may show last IBKR bars immediately plus `as of …, filling…`. This is an explicit exception to "never serve last-good" -- last-good here is IBKR-sourced, labeled, and never mixed with Alpaca.

3. **One paced service.** `ibkr/historical_service.py` is the only production scheduler of `reqHistoricalData`. Token bucket for IB's three rate rules. Bounded concurrency 3. Priority `open_chart` > `warm` > `background`. **Send rule (amended 2026-08-18):** `reqHistoricalData` is never sent while `wait_seconds > 0` beyond IB's short same-contract (2s) / identical-request (15s) windows. `background` and `warm` shed on any wait. `open_chart` sleeps only a short window; a 10-minute-bucket wait is rescheduled via `call_later` on the IB loop (never sleep-then-send, which starved L1 ticks). Cross-caller dedup (chart, surge seed, setups, warm). Shed/defer/reschedule log at INFO. `/bars` and the ticker WS skip `schedule_fill` when the stored series is complete and fresh.

4. **Derive today's coarse panes from 1Min.** A 1Min / 1 D pull paints today's 5Min / 15Min / 30Min / 1Hour. Native longer spans still fetch in the background.

5. **Push fills.** Successful fetches persist and broadcast `bars_patch` on `/ws/ticker/{symbol}` with a `msg.symbol` gate. The client serial queue and 25s abort are deleted.

6. **Historicals leave `cold_slot`.** Snapshots and completed-orders keep the cold lock. Chart fills no longer wait behind them.

## Consequences

- A click is a local read. First paint is store or an honest filling state, not a timeout overlay.
- Surge seed hops onto the IB loop via `on_ib` and uses `priority=background` so it cannot steal an open chart.
- `historical_gate.historical_slot` remains a test/compat facade over `cold_slot`. Production chart paths must not acquire it.
- `auto_live` remains NO-GO. This ADR does not touch orders.

## Rejected alternatives

- Another timeout / retry / queue patch on the existing pull (the 2026-07-29 and 2026-08-17 class).
- Serving expired in-memory TTL without coverage (lies about freshness).
- Parallel unbounded `reqHistoricalData` (trips pacing, Error 162).
- Using archive tape `bars_1m` as the only store (Quote Panel never opens T&S).
- Sleep-then-send for long pacing debt (2026-08-18 Gainers freeze): a 333s 10-min-bucket wait became `sleep(16)` + send, saturating the shared IB socket and starving `reqMktData` L1 ticks.

## Related

- `backend/ibkr/historical_service.py`
- `backend/ibkr/historical_pacing.py`
- `backend/bars_store.py`
- `backend/chart_bars.py`
- `.cursor/rules/single-market-data-feed.mdc`
