# 2026-08-25 -- Chart VWAP axis shows dollar amount

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / chart UI (continuity-only; no specialist hop)
- **Related:** `CHANGELOG.md` 2026-08-25 -- Chart VWAP axis shows dollar amount

## Task

Show the VWAP dollar amount on the chart's right price axis so it can be read without hovering.

## Goal

The orange VWAP axis tag reads `VWAP $X.XX` from the last computed VWAP point, not the bare word `VWAP`.

## Why it mattered

The dashed VWAP line was labeled, but the only way to read its price was to park the crosshair on it. That is too slow while watching a live 1-minute tape.

## What we changed

- `formatVwapAxisTitle` / `vwapAxisTitleFromLine` in `frontend/src/chartIndicators.ts`
- After each VWAP `setData`, `TickerChartOverlays` applies that string as the LineSeries `title`
- Unit tests for the formatter

## How it works now

lightweight-charts draws the series `title` on the price scale and that text replaces the numeric last-value. Nova therefore puts the last VWAP plot value into the title (`VWAP $78.52`). EMA tags stay name-only.

## Why this approach

Putting the dollars in `title` is the only way to change the orange tag the operator pointed at. Flipping `lastValueVisible` alone would still show `VWAP` because the title wins. A second HUD overlay would duplicate the axis and drift from the line. Rejected adding EMA dollar tags in the same pass -- not asked, and four extra numbers would crowd the last price.

## Verification

- `npx vitest run src/chartIndicators.test.ts` -- 8/8 pass
- `npm run build` (`tsc -b && vite build`) -- exit 0
- Browser: NVDA Trader chart, VWAP on; orange axis tag showed `VWAP $212.18`

## Follow-ups

EMA axis tags are still names only. Do not add dollars there unless asked.

## Keywords

vwap, chart, axis, lightweight-charts, title, overlay
