# 2026-08-25 -- Chart filling hint no longer covers the time axis

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / chart UI (continuity-only; no specialist hop)
- **Related:** `CHANGELOG.md` 2026-08-25 -- Chart filling hint no longer covers the time axis · `PROBLEM_LOG.md` 2026-08-25 -- Chart filling hint covered the time axis and TradingView mark

## Task

Stop the chart "filling..." overlay from covering the first time label and the TradingView mark.

## Goal

Time labels stay readable while a store-first historical fill is in flight.

## Why it mattered

On the Quote Panel the bottom-left corner already holds the time axis and the required TradingView logo. The filling string sat on both, so 1:30 PM was unreadable.

## What we changed

- Filling status is a header chip on `TickerChartControls`, not an absolute overlay on `.chart-body`
- CSS lifts `a[href*="tradingview.com"]` above the time axis
- Regression test: filling text is inside `.chart-header`

## How it works now

If bars exist and coverage is still `filling`, the header shows `as of HH:MM ET, filling...`. The plot keeps its left-bottom corner for axis ticks and attribution.

## Why this approach

Moving the chip to the header is one placement, not a stacked overlay that has to guess the time-axis height. Rejected only bumping `bottom` on the old overlay -- that still collides with volume bars and the logo. Rejected hiding the TradingView mark (library license).

## Verification

- `npx vitest run src/components/TickerChartControls.test.tsx` -- 2/2 pass
- `npm run build`
- Browser: Quote Panel chart, confirm filling chip is in the header and 1:30 PM is visible

## Follow-ups

EMA axis tags can still stack when 9/20/50/200 are close in price. That is a separate last-value collision, not this overlay.

## Keywords

chart, filling, overlap, time axis, TradingView, Quote Panel
