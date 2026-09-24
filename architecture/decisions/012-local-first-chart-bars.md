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

**Amendment (2026-08-18):** Scanner L1 last prices roll into live 1Min overlay rows in the same `bars_intraday` store (`ibkr/l1_minute.py` -> write queue). That is not a second historical scheduler. Live minutes do not stamp `bars_coverage`; a streamed tip is not a finished hist fill, so `store_series_complete` + fresh coverage still gates skip-fill. A completed minute is flushed when the next print arrives *or* when the L1 batch heartbeat sees `now` past that minute -- quiet names do not wait for another trade.

**Amendment (2026-08-18, candle ownership):** One candle identity: `UNIQUE(symbol, timeframe, ts)`. Hist fills write `source=ibkr` and always replace. L1 writes `source=ibkr_l1` and may only insert or refine a live row (`WHERE source = ibkr_l1`). Volume is not a lock -- IB hist minutes can be volume=0. HTTP `/bars` still reports feed `source=ibkr`. HOD Squeeze seed and chart 1Min then share bars Nova already paid for with `reqMktData`. Legacy DBs migrate at `init_db` by copying `ibkr` rows first, then other sources into gaps. Pre-change L1 minutes were tagged `ibkr` (the old enqueue default); those grandfathered volume=0 rows stay hist until a chart fill overwrites them -- accepted, no retag.

4. **Derive today's coarse panes from 1Min.** A 1Min / 1 D pull paints today's 5Min / 15Min / 30Min / 1Hour. Native longer spans still fetch in the background.

5. **Push fills.** Successful fetches persist and broadcast `bars_patch` on `/ws/ticker/{symbol}` with a `msg.symbol` gate. The client serial queue and 25s abort are deleted.

**Amendment (2026-09-11, 10Sec first paint):** Trader already receives IBKR AllLast prints through `/ws/ibkr/tape/{symbol}`. The first symbol-gated print seeds the client's empty 10Sec bar store immediately, and later prints update that provisional candle while the paced historical fill remains authoritative. A late empty `/bars` response cannot erase a client-side tape candle. Empty+filling panes use a self-scheduling capped retry loop whose continuation does not depend on React rendering; unchanged empty responses therefore cannot turn recovery into a one-shot request.

**Amendment (2026-09-23, prints that set a price):** A tape-built candle takes only the prints that move the consolidated high / low / last. The operator saw PLTR's 10Sec pane grow wicks $2-3 under the market that no other chart showed: FINRA prints tagged `4 W` (derivatively priced, average price) and `4 I` / `I` (odd lots) were reported for volume, and Nova painted them as prices. IBKR's own TRADES bars leave them out, so the historical part of the pane was clean and the tape-built tip was not. One pure rule, `backend/sale_conditions.py`, decides from IBKR's `unreported` flag and the sale-condition codes (codes in `constants_tape.py`). It covers every candle built from prints: the client 10Sec bar, `ibkr/tape_10sec`, the archive 1m builder, the recorder's bar buckets and a capture replay's print-built candles. Volume follows the same prints, because IBKR's bars count them the same way. Checked against IBKR's 10-second bars for AAPL, GRML, IMCC, DAIC and MEDS: the worst high / low miss fell from $8.50 to $0.18, and the median volume ratio went from 1.14-1.27 to 1.00. The live tip every pane paints from `trade_update` reads IBKR's Last (tick 4). It no longer reads `ticker.last`, which ib_async also overwrites from RTVolume (unreported trades included) and from every AllLast print on the one Ticker it keeps per contract. Time & Sales still shows every print.

**Amendment (2026-09-23, #535, operator decision):** A Session Record replay builds every candle from its prints and never draws the bar buckets the recorder stored beside them. Recordings made before the amendment above stored buckets built from every print, so drawing them brought the wicks back (GRML 2026-09-22: 82 of 480 one-minute candles, a low of 13.19 where trades bottomed at 15.43), and after #511 a practice order would not fill at a price the chart showed. One path for every recording keeps the chart and the fills on the same prints; the recorder still writes its buckets as part of the recording.

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
- Volume=0 as the hist lock (2026-08-18): IB historical minutes can be volume=0, so L1 still rewrote OHLC.
- A live integrity alarm on hist-OHLC drift: that detects a hangover after charts already painted it. Candle identity is the lock.

## Related

- `backend/ibkr/historical_service.py`
- `backend/ibkr/historical_pacing.py`
- `backend/bars_store.py`
- `backend/ibkr/l1_minute.py`
- `backend/archive/write_queue.py`
- `backend/chart_bars.py`
- `frontend/src/chart/barsStore.ts`
- `frontend/src/chart/chartBarsStuckRetry.ts`
- `.cursor/rules/single-market-data-feed.mdc`
