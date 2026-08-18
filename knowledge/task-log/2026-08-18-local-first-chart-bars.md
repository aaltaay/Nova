# 2026-08-18 -- Local-first chart bars (ADR 012)

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-08-18 -- Local-first chart bars · `PROBLEM_LOG.md` 2026-08-18 -- Chart timeout was the wrong constraint · ADR 012

## Task

Get to the bottom of the recurring "Chart bars timed out -- IBKR historical may be busy" overlay on ticker click (Quote Panel and Trader). Do not patch the scheduler again. Change the architecture so changing symbols is a local read.

## Goal

A click paints immediately from an IBKR-sourced store (or an honest filling state). IBKR historical becomes paced background replenishment. The timeout error class is retired.

## Why it mattered

The operator cannot trade off a red overlay. The same failure kept returning in new forms because every fix (TTL cache, client queue, detached fetch, 8x retry) left the click as a deadline-bound pull on a globally serialized broker resource.

## What we changed

- Added `historical_pacing.py` (60/10 min, 5/2s same contract, 15s identical) and `historical_service.py` (concurrency 3, priority lanes, dedup, background shed).
- Added `bars_store.py` over archive.db `bars_intraday` + `bars_coverage`.
- `chart_bars.fetch_chart_bars` is store-first; it schedules a fill and does not call `run_coro`.
- `hod_momo_surge_seed` hops `on_ib` and uses `priority=background`.
- Ticker WS warms via `schedule_fill` and broadcasts `bars_patch`.
- Deleted `barsFetchQueue.ts` and the 25s abort. AbortError is no longer a user-facing timeout.
- Quote/Trader charts show "Loading IBKR historical…" / "as of …, filling…" instead of the red timeout.
- ADR 012 + `single-market-data-feed.mdc` coverage-metadata exception.

## How it works now

HTTP `/bars` reads SQLite. If IB is ready, a fill is spawned on the IB loop. When bars land they persist and push `bars_patch` (symbol-gated). Today's 5Min/15Min/30Min/1Hour can paint from a 1Min pull. Snapshots still use `cold_slot`; historicals do not. Empty store + Gateway down is still 503. No Alpaca candles.

## Why this approach

**Required.** Serializing historicals was the wrong IB constraint. Raising timeouts or adding another queue would have failed the next time HOD seed or enrichment held the lock. A local store + paced service matches IB's actual rules and makes the next consumer (setups, warm, seed) a priority label instead of a new mutex. Rejected: last-good without coverage (lies), unbounded parallel historicals (pacing violations), tape-only `bars_1m` (Quote Panel never opens T&S).

## Verification

- `py -3 -m pytest tests/test_historical_pacing.py tests/test_historical_derive.py tests/test_bars_store.py tests/test_historical_service.py tests/test_ibkr_bars.py tests/test_ibkr_bars_cache.py tests/test_historical_gate.py tests/test_hod_momo_surge_seed.py tests/test_ibkr_work_class.py -q` -- 62 passed
- `npx vitest run src/chart/barsStore.test.ts src/chart/chartBarsPolicy.test.ts src/chart/barsErrorRetry.test.ts src/chart/requestVersion.test.ts` -- 14 passed

## Follow-ups

- Live soak: rapid scanner clicks + Trader symbol switch during HOD. Confirm API logs show `historical fill` / no `must run on the IB connect-loop` from surge seed.
- Native 5 D 5Min still fills in the background after the derived first paint.

## Keywords

chart bars, historical_service, bars_store, ADR 012, pacing, bars_patch, surge_seed, timeout
