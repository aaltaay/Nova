# 2026-08-26 -- Trader chart hist loading soak

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `DEFERRED_LOG.md` D-003 · ADR 012 · PROBLEM_LOG 2026-08-17 Trader 2x2 timeout · PROBLEM_LOG 2026-08-18 Gainers freeze after chart-fill · `architecture/decisions/012-local-first-chart-bars.md`

## Task

Soak why Trader panes sit on "Loading IBKR historical..." (10-Second and Full Day on MSS) while 5-Minute and 1-Minute already paint. Learn only -- no product patch this session.

## Goal

A cold agent can name the bottleneck, the evidence, and the highest-leverage fixes without re-probing IB.

## Why it mattered

Opening a ticker is the desk. Two of four chart quadrants staying black for minutes feels like the whole app is broken even when L2, tape, and two other panes are live.

## What we changed

No runtime code. Parked the diagnosis as D-003. This entry is the soak narrative.

## How it works now

HTTP `/bars` is store-first (ADR 012). If `bars_store` already has candles, the pane paints in ~10-400ms. If the store is empty, the UI shows "Loading IBKR historical..." and `historical_service` queues a real `reqHistoricalData`. That send is capped at 3 at a time and 60 per 10 minutes. IB extra-restricts bar sizes of 30 seconds or less.

Trader grid is 5Min + 10Sec + 1Day ("Full Day") + 1Min. 1Min/5Min often have leftover store rows (L1 overlay + old derives), so they paint immediately. 10Sec is never warmed (`IBKR_BARS_WARM_TIMEFRAMES` is 1Min/5Min/1Day) and asks IB for 4 hours of 10-second bars (`14400 S` / ~1440 candles). Full Day is 5 years of daily bars. Empty name + empty store = overlay until a token is free and the pull finishes.

Large Cap (ADR 014) schedules a background 1Day fill for every roster name on commit. That spray can consume the 60/10-min bucket. Open-chart fills then reschedule instead of sending. The overlay stays up even though Gateway is green.

## Why this approach

Soak before patch, because this class has already been "fixed" several times (25s abort, serial cold slot, sleep-then-send) and those patches starved L1 or cancelled the heavy panes. The live evidence said IB hist itself is fast when it runs (`ibkr.historical_bars` p50 ~331ms, max ~1.9s). The wait is queue/budget, not a slow candle decoder.

Rejected this session: raising `IBKR_HISTORICAL_MAX_CONCURRENT` (IB allows 50; the real ceiling is 60/10 min -- more concurrency would empty the bucket faster). Rejected another client timeout overlay (ADR 012 deleted that on purpose). Rejected Alpaca candles (single-feed rule).

Highest-leverage next patches, in order: (1) stop Large Cap from burning hist tokens for names the operator is not charting; (2) give empty panes `open_chart` and already-painted stale panes `warm`; (3) paint 10Sec from tape/L1 immediately and hist-fill the 4h window in the background. `keepUpToDate` for 10Sec is a later option (IB supports it at 5s+).

## Verification

Live `GET /api/ticker/MSS/bars` while Trader showed the overlay: 10Sec n=0 filling=true (~95ms), 1Day n=0 filling=true (~7ms), 1Min n=1500 stale as_of 14:15Z, 5Min n=145 derived_from 1Min as_of 2026-08-18. `/api/metrics/ops` `ibkr.historical_bars` count=60 error_count=10 last_sample_age ~448s (bucket full, no send for ~7.5 min). `ibkr.snapshot_quotes` p95 ~25s. HTTP loop max_lag 43741ms; IB loop last ~7-12ms not wedged. Later same process: 10Sec n=1441, 1Day n=500. AAPL 1Day was already settled (n=500 filling=false); AAPL 10Sec store as_of 2026-08-18.

## Follow-ups

D-003. Do not implement until the operator asks. Do not sleep-then-send long pacing waits (2026-08-18 Gainers freeze). Blast-radius verify scanner L1 if hist send rules change.

## Keywords

10Sec, 1Day, Full Day, Loading IBKR historical, ADR 012, historical_service, pacing 60/10min, Large Cap 1Day backfill, bars_store, open_chart, MSS
