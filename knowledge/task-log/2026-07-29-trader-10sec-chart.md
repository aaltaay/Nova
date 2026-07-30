# 2026-07-29 -- Trader 10-Second chart (4h history + live)

- **Status:** completed
- **Agents:** parent
- **Domain:** hotkeys-adjacent / Trader charts (market-feed chart path)
- **Related:** `CHANGELOG.md` §2026-07-29 -- Trader 4th pane: 10-Second chart

## Task

Replace the temporary 15-Minute optional 4th Trader pane with a 10-Second chart that has as much history as a single safe IBKR request can deliver, then continues from the live trade stream.

## Goal

Default-on 4th grid pane (`10Sec`): ~4h of IBKR 10s bars on first open, then live tip updates every ~10s from ticker WS trades, with minimal new machinery and no small-bar pacing storms.

## Why it mattered

The 4th chart disappeared after the grid was cut to 3 panes for load. The user wants 10s resolution for tape-style timing, with maximum history, without a background recorder or multi-request backfill that fights IBKR's <=30s bar pacing rules.

## What we changed

- Backend: `"10Sec"` in `CHART_TIMEFRAMES`; `IBKR_BAR_SIZE`/`DURATION` = `"10 secs"` / `"14400 S"`; `IBKR_10SEC_FETCH_BARS = 1500`; warm set dropped `15Min` and never warms `10Sec`; `fetch_bars_async` clamps 10Sec limit so the cache stores the full window.
- Frontend: `timeframeSeconds` parses `Sec`; seconds-aware axis/crosshair; session highlight includes `Sec`; `CHART_TIMEFRAME_BAR_LIMITS` + `ensureBars(..., limit)`; ChartGrid optional panel = 10-Second, default ON, batch warm excludes 10Sec; no `CHART_REFETCH_SEC['10Sec']`.

## How it works now

Open Trader tab → three default panes batch-warm → 10s pane independently fetches `/bars?timeframe=10Sec&limit=1500` → paints ~4h → WS `trade_update` buckets into 10s candles via `tradeBucket` / `useChartLiveTrade`. Hidden tabs pause via `chartActive`. Failures stay loud on that pane only.

## Why this approach

- **Single 4h request** (official IBKR step-size table allows `14400 S` with `10 secs`) beats chunked backfill (holds the historical lock, pacing risk) and beats a recorder (complexity + only 3 Trader symbols matter).
- **No poll / no keepUpToDate** -- live tip from existing WS path; avoids small-bar identical-request rules.
- **Clamp + per-pane limit** -- default `CHART_DEFAULT_BARS=500` would have silently cut 4h to ~83 min; backend clamp stores full payload, frontend asks for 1500.
- **Sec parse was mandatory** -- without it, live append would draw 1-minute candles on the 10s pane.
- Rejected: multi-hour chunked history, DB recorder for non-open symbols, putting `10Sec` in the standalone dropdown (blast radius).

## Verification

- `pytest backend/tests/test_ibkr_bars.py backend/tests/test_ibkr_bars_cache.py` (+ bars/chart filter suite)
- Vitest: tickerChartData, chartTimeFormat, sessionHighlight, barsStore, ChartGrid, stockViewTerminal / chart/*
- `npm run build`

## Follow-ups

- Manual Gateway check: 2-3 Trader tabs, confirm ~4h paint + tip updates; watch for Error 162 pacing.
- If 4h is slow on this Gateway, drop `IBKR_BAR_DURATION["10Sec"]` to `"7200 S"` (constant only).

## Keywords

10Sec, 10-second chart, ChartGrid, IBKR historical, 14400 S, tradeBucket, barsStore, Trader View
