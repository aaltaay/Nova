# 2026-07-29 — Chart bars Phase 1: IBKR TTL cache + batch + warm

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / charts
- **Related:** `CHANGELOG.md` §2026-07-29 -- Chart bars Phase 1 · `PROBLEM_LOG.md` §2026-07-29 -- Chart historical stampede

## Task

Ship Phase 1 of the chart pipeline re-architecture: stop the IBKR historical stampede when opening a ticker or loading the Trader 2x2 grid.

## Goal

Identical `(symbol, timeframe)` bar requests coalesce and hit a short TTL cache; batch + WS warm reduce duplicate Gateway round-trips. Failures stay loud (no stale last-good).

## Why it mattered

Charts timed out under normal Trader use because four panes (plus Quote Panel) each called IBKR historical through one serial lock with no cache.

## What we changed

- Added `backend/ibkr/bars_cache.py` (TTL + single-flight + metrics counters).
- Wired `fetch_bars_async` through cache; uncached path in `_fetch_bars_uncached`.
- `GET /api/ticker/{symbol}/bars/batch` + `chart_bars.fetch_chart_bars_batch`.
- Ticker WS (ibkr) fires `warm_symbol_bars` for `1Min/5Min/15Min/1Day`.
- Constants: `IBKR_BARS_CACHE_TTL_*`, `IBKR_BARS_CACHE_MAX_KEYS`, `IBKR_BARS_WARM_TIMEFRAMES`.
- Tests in `backend/tests/test_ibkr_bars_cache.py`.

## How it works now

Cache key `(symbol, timeframe)`. Intraday TTL 20s, daily family 15min. Expired = miss (never returned). Concurrent misses share one in-flight Future on the IB loop. Empty/error results: only successful payloads are stored; HTTP 503 on miss stays a hard error.

## Why this approach

**Required.** Rejected stale-on-503 (user: do not present old data as current). Rejected frontend-only coalesce (Gateway still pays for 4 serial historicals without a server cache). Single-flight lives on the IB event loop because `run_coro` fans many threads into that loop -- a sync-only lock would not coalesce the async historical calls.

## Verification

`py -3 -m pytest tests/test_ibkr_bars_cache.py tests/test_ibkr_bars.py -q` -- 18 passed.

## Follow-ups

Phase 2/3: frontend bars store, incremental `series.update`, stable chart instances, pause hidden-tab refetch, decouple ChartGrid from `detailReady`.

## Keywords

chart bars, bars_cache, single-flight, batch bars, warm_symbol_bars, IBKR historical, TTL
