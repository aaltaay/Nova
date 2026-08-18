# 2026-08-18 -- Chart bars local-first (ADR 012)

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-08-18 -- Chart bars are store-first · `PROBLEM_LOG.md` 2026-08-18 -- Chart timeout was the wrong architecture · ADR 012

## Task

Get to the bottom of the recurring Quote Panel / Trader "Chart bars timed out -- IBKR historical may be busy" overlay. Do not patch another timeout. Change the architecture so a ticker click paints a graph.

## Goal

A click is a local read. IBKR historical becomes paced background replenishment. The timeout error class is retired.

## Why it mattered

The operator clicks a gainer and expects candles. Instead the chart started on a red timeout, then sometimes recovered. The same class came back from Trader 2x2, wedges, and symbol switches. Trust in the desk depends on that first paint.

## What we changed

- Added `historical_pacing.py` (60/10min, 5/2s same contract, 15s identical).
- Added `historical_service.py`: concurrency 3, priority lanes, dedup, derive-from-1Min, `bars_patch`.
- Added `bars_store.py` on `archive.db` (`bars_intraday` + `bars_coverage`).
- `chart_bars.fetch_chart_bars` is store-first; it no longer blocks on `run_coro`.
- `ibkr/bars.py` no longer takes `historical_slot`.
- Surge seed hops via `on_ib` and uses background priority.
- Ticker WS warms 1Min/5Min/1Day through the service.
- Deleted `barsFetchQueue.ts` and the 25s abort / timeout string.
- Chart UI shows "Loading IBKR historical…" or `as of HH:MM, filling…` instead of a dead-end error.
- ADR 012 + feed MDC coverage rule.

## How it works now

`GET /bars` reads SQLite and returns `{bars, coverage}`. If IB is ready it schedules a fill and returns immediately (empty + `filling` on a cold symbol). The service sends at most 3 historicals at once, sheds background work, and persists + broadcasts when IB answers. Today's 5Min pane can paint from a 1Min pull while the native 5 D fetch is still out. Alpaca is never a candle source.

## Why this approach

Serialization was the wrong IB constraint. Another queue or a longer timeout would fail the next time `snapshot_quotes` or surge seed held the slot. A local store plus a rate budget matches how IB actually works and matches the click UX (paint now, fill in). Rejected: serving unlabeled stale TTL, unbounded parallel historicals, and using tape-only `bars_1m` (Quote Panel has no T&S).

## Verification

- `py -3 -m pytest tests/test_historical_pacing.py tests/test_historical_derive.py tests/test_bars_store.py tests/test_historical_service.py tests/test_ibkr_bars.py tests/test_ibkr_bars_cache.py tests/test_historical_gate.py tests/test_hod_momo_surge_seed.py tests/test_ibkr_work_class.py -q` -- 62 passed
- `npx vitest run src/chart/barsStore.test.ts src/chart/chartBarsPolicy.test.ts src/chart/barsErrorRetry.test.ts src/chart/requestVersion.test.ts` -- 14 passed

## Follow-ups

- Live soak: rapid scanner clicks + Trader symbol switch during HOD.
- Compact `bars_intraday` in archive maintenance if the table grows.

## Keywords

chart bars, ADR 012, historical_service, bars_store, bars_patch, pacing, coverage, timeout
