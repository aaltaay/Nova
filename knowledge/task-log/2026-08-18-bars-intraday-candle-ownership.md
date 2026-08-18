# 2026-08-18 -- One candle identity for hist vs L1 1Min

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-08-18 One candle identity · `PROBLEM_LOG.md` 2026-08-18 Volume is not hist ownership · ADR 012 amendment

## Task

Replace the volume=0 UPSERT guard (and the "cheap integrity alarm" idea) with a real ownership model so scanner L1 and IB historical fills cannot fight over the same 1Min candle.

## Goal

One row per `(symbol, timeframe, ts)`. Hist always wins. L1 may only insert or refine a live overlay. Volume is not a lock.

## Why it mattered

The first hist-protect SQL used `WHERE volume = 0 OR excluded.volume > 0`. A red test showed a volume=0 hist candle (the halt / illiquid AH case) jump high from 1.40 to 9.99 on one L1 last. L1 sending volume>0 could buy a hist row the same way. An after-the-fact integrity check would have raised an alarm after Quote/Trader OHLC was already wrong.

## What we changed

- `bars_intraday` unique key is `(symbol, timeframe, ts)`; `init_db` migrates legacy `(..., source)` uniques by copying `ibkr` first, then other sources into gaps.
- `ARCHIVE_SOURCE_IBKR_L1` tags live overlay rows. Hist writes always tag `ibkr` and replace.
- Live upsert lives in `bars_store.write_live_batch`; the write queue no longer owns fighting SQL.
- HTTP `/bars` still reports feed `source=ibkr`.

## How it works now

L1 flushes `source=ibkr_l1`. If that minute has no row, it inserts. If the row is already live, it refines high/low/close. If the row is hist, the `WHERE source = ibkr_l1` clause skips. A later hist fill overwrites the overlay and retags `ibkr`. Squeeze and charts still read one series.

## Why this approach

Rejected: a live `/api/integrity` check on OHLC drift. That is a detector, not a lock -- the hangover would still ship until someone looked. Rejected: keep volume as ownership. IB hist minutes can be volume=0, so the predicate is false. Rejected: two tables or two rows per minute with a read-time coalesce. The unique key already wanted one candle; two identities under the same ts would make `/bars` LIMIT drop history and double-paint. Split `source` plus a single-ts unique is the lock the schema was missing. Two-table overlay is the same merge with more moving parts.

## Verification

`py -3 -m pytest backend/tests` -- 1237 passed. `py -3 -m pytest tools` -- 191 passed, 3 failed (pre-existing: warrior transcript provenance, `test_sync_agent_surfaces` security canvas counts; not this change). Frontend Vitest 697 passed. `npm run build` exit 0. `doc_invariants` OK.

Focused: `test_l1_does_not_clobber_zero_volume_hist`, `test_l1_volume_cannot_buy_a_hist_row`, `test_hist_fill_replaces_live_minute`, `test_migrate_legacy_source_unique_keeps_hist`, `test_intraday_drain_opens_one_connection`.

Live 90s soak after API restart: 87,028 closed `ibkr` 1Min candles, 0 same-volume OHLC edits, 0 source flips; `ibkr_l1` 472 to 479; `ib_loop_lag_ms` last=3.1 max=46.4 wedged=false.

## Follow-ups

Existing `archive.db` migrates on API start (hist copy first, then other sources). No integrity alarm was added on purpose. Pre-change L1 minutes were written as `source=ibkr`; those volume=0 rows are grandfathered as hist until a chart fill overwrites them -- accepted, no retag.

## Keywords

bars_intraday, candle unique, ibkr_l1, l1_minute, hist ownership, ADR 012
