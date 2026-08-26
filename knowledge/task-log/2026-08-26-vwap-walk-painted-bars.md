# 2026-08-26 -- VWAP walks with painted chart bars

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed (chart overlays; continuity-only, done in-session)
- **Related:** `CHANGELOG.md` 2026-08-26 -- VWAP did not walk with painted chart bars; `PROBLEM_LOG.md` 2026-08-26 -- VWAP did not walk with painted chart bars

## Task

Debug why session VWAP was not walking alongside the painted candles.

## Goal

The orange VWAP line occupies the same bar times as the candles on 10Sec / 1Min / 5Min, including the live forming bar, without giving up the 09:30 ET session anchor.

## Why it mattered

VWAP is a decision level. If the candles have already printed two or three new bars and the orange line is still sitting on a closed 1Min time, the operator cannot tell whether price is holding or failing VWAP on the bar they are actually trading.

## What we changed

- `frontend/src/chart/vwapSession.ts` -- `vwapSourceForPane` plus `extendToTime` on `sampleVwapOntoBars`
- `frontend/src/chart/vwapSession.test.ts` -- 10Sec intra-minute walk, live-tip extend, 09:30 head-merge
- `frontend/src/chart/useChartLiveTrade.ts` -- `liveTipTime` when a new bucket opens
- `frontend/src/chart/TickerChart.tsx` / `TickerChartOverlays.tsx` -- splice pane bars and extend the line

## How it works now

Closed minutes still come from the shared 1Min store, so a 10Sec pane that only holds four hours of tape still anchors at 09:30. Once the 10Sec window starts, those 10Sec bars (real volume) feed the accumulator, so the line changes on every painted 10Sec candle. Tape can still invent a candle the store does not have yet; that gets one carried-forward point at the live tip time. 5Min and slower panes keep one VWAP point per painted candle from closed 1Min. Daily+ still has no session VWAP.

## Why this approach

Recomputing VWAP from each pane's own full window was how 10Sec / 1Min / 5Min drifted by 14 cents on 2026-08-25 -- different anchors, not different bar sizes. Keeping 1Min as the session head and only splicing pane bars inside the visible sub-minute window preserves the open and lets 10Sec walk. Plotting raw 1Min points on a 10Sec chart would insert extra times into the lightweight-charts scale and shove the candles apart. Extending with a single live-tip point (no fake volume) is honest: we do not have tape volume on that print, but the line must still reach the rightmost candle.

Rejected putting 10Sec volume into the 1Min store. That store is hist + L1 minutes (ADR 012); mixing tape volume there would fight hist fills. Rejected tick-by-tick VWAP: no extra IB generic tick, and it would disagree with the 1Min session series on purpose.

## Verification

- Failing tests first: `vwapSourceForPane` missing, live tip stayed at 09:32 instead of 09:33
- `npx vitest run src/chart src/chartIndicators.test.ts` -- 18 files / 123 passed
- `npm run build` (`tsc -b && vite build`) exit 0
- Live CRE `/api/ticker/CRE/bars`: merged 10Sec VWAP changed on 11 of the last 12 tens (old sampling was flat for six candles)
- API connected, IBKR `session_state=ready`; Vite already on `:5173`

## Follow-ups

1Min forming-bar *value* can still lag while L1 overlay minutes carry `volume=0` until hist reconciliation. This change only lines the overlay up in time with the painted bars.

## Keywords

vwap, 10Sec, live tip, painted bars, session VWAP, vwapSourceForPane, extendToTime
