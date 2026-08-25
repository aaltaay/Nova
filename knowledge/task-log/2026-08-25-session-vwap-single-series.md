# 2026-08-25 -- One session VWAP shared by every chart timeframe

- **Status:** completed
- **Agents:** parent (browser verification delegated to the browser subagent)
- **Domain:** widgets / chart UI (continuity-only; no specialist hop)
- **Related:** `CHANGELOG.md` 2026-08-25 -- One session VWAP shared by every chart timeframe; `PROBLEM_LOG.md` 2026-08-25 -- VWAP showed a different value on every chart timeframe

## Task

Investigate why the chart VWAP showed a different value on each timeframe, then make it one line.

## Goal

The orange VWAP tag reads the same dollar value on 10Sec / 1Min / 5Min / 15Min / 30Min / 1Hour / 4Hour for the same symbol at the same moment, anchored at the 09:30 ET open.

## Why it mattered

VWAP is a decision level, not decoration. If the 1-minute pane says $3.87 and the 10-second pane says $3.73, the operator cannot use either one to judge a reclaim or a fail. Measured live on DAIC the five intraday panes spanned $3.73-$3.87 on a $3.88 stock; AIXI spanned $1.22-$1.37, over 11%. A 15Min store caught mid-refill briefly produced $0.61 on that same $3.88 stock.

## Root cause

VWAP was accumulated separately inside each pane from that pane's own bar array, through `VwapMvwapEmaCrossover` in `lightweight-charts-indicators`. That community indicator has **no session anchor**: it resets only when the bar's calendar day changes, then accumulates from whatever bar happens to be first in the array.

Each timeframe holds a different slice of history -- per-timeframe `IBKR_BAR_DURATION` plus the backend's 500-bar trim -- so each one anchored somewhere else:

| Pane | Window | Where today's VWAP actually started |
|---|---|---|
| 10Sec | `14400 S`, 1500 bars | ~4 hours ago (rolling) |
| 1Min | `1 D`, 500 bars | ~500 minutes ago |
| 5Min / 15Min / 30Min / 1Hour / 4Hour | multi-day, 500 bars | 04:00 ET |
| 1Day / 1Week / 1Month | 500 daily bars | resets every bar, so the line was `(H+L+C)/3` |

Two amplifiers on top: per-bar `hlc3` is a proxy for the real volume-weighted price and its error grows with bar size, and the line ignored the live forming candle.

## What we changed

- `frontend/src/chart/vwapSession.ts` (new) -- `sessionVwapPoints` (accumulate) + `sampleVwapOntoBars` (project onto a pane) + `coversSessionOpen` (honesty check)
- `frontend/src/chart/useVwapSourceBars.ts` (new) -- holds the shared `(symbol, '1Min')` bars-store entry for every pane
- `frontend/src/chartIndicators.ts` -- dropped `computeVwapLine` and the `VwapMvwapEmaCrossover` import; `formatVwapAxisTitle` gained a `partial` flag
- `frontend/src/components/TickerChartOverlays.tsx` -- takes the shared source, samples it, skips the series on daily+
- `frontend/src/chart/TickerChart.tsx` -- wires the hook and passes `timeframe`
- `frontend/src/constantGroups/chart_api.ts` -- `CHART_VWAP_SOURCE_TIMEFRAME`, `CHART_VWAP_SESSION_START_SEC`, `CHART_VWAP_SESSION_END_SEC`
- `frontend/src/constantGroups/market_ui.ts` -- `CHART_TIMEFRAME_BAR_LIMITS['1Min'] = 1000`
- `frontend/src/tickerChartData.ts` -- `CHART_PAINT_VISIBLE_BARS['1Min'] = 500`

## How it works now

Every pane reads the same `(symbol, '1Min')` entry from the shared bars store. `sessionVwapPoints` walks that one series accumulating `hlc3 * volume`, resetting each ET day and only inside 09:30-16:00 ET; after the close the final value carries flat, and a zero-volume minute carries the previous value forward. `sampleVwapOntoBars` then gives each pane bar the newest source point that closed inside it, so a 5-minute bar shows the VWAP as of its own close and a 10-second bar steps once per source minute.

Panes cannot drift apart, because they are not computing anything -- they are sampling one series. Bar times are ET wall clock encoded as an epoch (`isoToEtTime`), so UTC getters read ET directly and each bar's DST offset is already folded in.

VWAP is not offered on 1Day / 1Week / 1Month at all. `lightweight-charts-indicators` still owns EMA / RSI / MACD.

## Why this approach

The user picked the frontend shared-series option over a backend-authoritative VWAP, and 09:30 ET over 04:00 ET premarket.

Computing from the finest series and sampling down is what actually kills the bug rather than reducing it. The obvious smaller fix -- add a session anchor to the existing per-pane math -- was rejected because panes would still disagree: `hlc3` on a 1-hour bar is a much worse proxy for the traded average than `hlc3` on a 1-minute bar, so the accumulations diverge even from an identical anchor. Only feeding one bar size into the accumulator removes that error from the comparison entirely.

Rejected a backend-authoritative session VWAP shipped with the bars payload. It would be the better single source of truth (HOD Momo, quote panel, and alerts could share the number) but it needs a new module, a store field, and WS plumbing for a bug that is entirely in the browser. Worth revisiting when a second consumer actually wants the number.

Rejected patching the vendored library. The reset-on-calendar-day behavior is that indicator's design, and Nova needs a broker-comparable RTH anchor.

Rejected drawing `(H+L+C)/3` on daily charts, which is what shipped before. A single-session VWAP has no meaning across months; showing nothing is honest, and TradingView does the same.

Raising the 1Min limit 500 -> 1000 rather than fetching a second narrower series keeps one store entry per (symbol, timeframe) -- `barsStore` keys on that pair and does not include the limit, so two different limits for the same pair would fight. IB already returns `1 D` of extended minutes, so this only stops discarding rows; it is not an extra IBKR request. `CHART_PAINT_VISIBLE_BARS['1Min'] = 500` keeps the visible window exactly as it was so the wider array is invisible to the operator.

Kept the `(partial)` axis suffix instead of silently drawing a mis-anchored line, per the fail-loud rule.

## Verification

- `npx vitest run` -- 163 files / 729 tests pass, including 17 new `vwapSession` cases: 09:30 anchor with premarket excluded, volume weighting (not a bar mean), cross-timeframe equality at shared bar closes, zero-volume carry-forward, 16:00 stop, per-session reset, both DST transition weeks, no cross-day bleed into premarket, 10Sec stepping, daily returns empty
- `npm run build` (`tsc -b && vite build`) -- exit 0
- Live: drove the shipped functions against `/api/ticker/{sym}/bars` for all seven intraday timeframes. DAIC returned `VWAP $3.92` on every one, AIXI `VWAP $1.32` on every one, both matching an independent Python recomputation of the same anchor rules; daily returned no line
- Before/after on the same live data (old per-pane math): DAIC 10Sec $3.73 / 1Min $3.87 / 5Min $3.79 / 15Min $3.76 / 1Hour $3.74, now all $3.92
- Browser (DAIC Trader 2x2 grid): VWAP present on 5Min / 10Sec / 1Min, absent on 1Day, no `(partial)` suffix, no console errors

## Follow-ups

- The VWAP tip can lag 1-2 minutes: L1-rolled 1Min bars carry `volume=0.0` (`backend/ibkr/l1_minute.py`), so they do not move VWAP until the ~30s reconciliation replaces them with real IB minutes. Giving those bars real volume is a backend change and was left out of scope.
- `backend/ibkr/ticks.py` calls `reqMktData` with an empty generic tick list. Adding `"233"` (RTVolume) would surface IBKR's own session VWAP as a live scalar at no extra subscription cost -- a good cross-check, though it carries no history so it cannot draw the series.
- If a second consumer (HOD Momo, alerts) needs the same number, promote this to the backend rather than duplicating the math.

## Keywords

vwap, session vwap, chart, timeframe mismatch, anchor, 09:30 ET, hlc3, lightweight-charts-indicators, VwapMvwapEmaCrossover, bars store, IBKR_BAR_DURATION, bar limit
