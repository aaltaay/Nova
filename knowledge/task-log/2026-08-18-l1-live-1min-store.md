# 2026-08-18 -- Scanner L1 live 1Min into bars_intraday

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed | hod-momo
- **Related:** `CHANGELOG.md` 2026-08-18 Scanner L1 rolls live 1Min · ADR 012 amendment

## Task

Roll scanner L1 into `bars_intraday` so streamed names keep a live 1Min series for Squeeze and charts without IB historicals.

## Goal

Store-only HOD seed reads bars Nova already paid for with `reqMktData`, not only bars a chart click fetched.

## Why it mattered

HOD stopped calling `reqHistoricalData`. Without a live writer, the store stayed stale unless the operator had opened a chart. That made "store-only" incomplete.

## What we changed

- `ibkr/l1_minute.py`: in-memory 1Min OHLC from L1 last; flush on minute roll via write queue.
- `scanner_l1.on_l1_quote` calls `on_last` (all streamed names, not only HOD active).
- `enqueue_intraday_bar` writes `bars_intraday` and does not stamp coverage.
- Missing coverage row now synthesizes `filling=true` so live-only bars cannot skip a hist fill.

## How it works now

Every streamed L1 last updates the current minute in RAM. When the clock rolls -- next print *or* the L1 flush heartbeat -- the completed minute is enqueued and drained off the IB loop into the same table hist fills use. Squeeze seed's 15-minute recency filter then sees those bars. Charts read them too. Hist fills still run until a real coverage row says the series is complete and fresh.

## Why this approach

Do not reuse tape `bars_1m` (Quote Panel never opens T&S; ADR 012 rejected that). Do not write SQLite from the IB callback (that wedged the desk). Do not mark live minutes as a finished fill (that would skip morning hist after 60 AH minutes). One store, two writers, coverage still owned by hist.

## Verification

`py -3 -m pytest backend/tests/test_l1_minute.py backend/tests/test_scanner_l1.py backend/tests/test_archive_write_queue.py backend/tests/test_bars_store.py backend/tests/test_hod_momo_surge_seed.py` -- 40 passed, including `test_elapsed_minute_flushes_without_next_print`.

Live (API restart 2026-08-18 17:41 ET): IBKR connected; 35 volume=0 `1Min` rows at the just-closed minute; `hod_surge_after_seed` pass; surge ready 25/42.

## Follow-ups

Quiet names no longer wait for a later print: `flush_elapsed` on the L1 batch heartbeat persists a minute once `now >= minute_ts + 60`. The still-open current minute stays in RAM until it closes.

## Keywords

l1_minute, bars_intraday, scanner L1, squeeze seed, ADR 012, write queue
