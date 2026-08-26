# 2026-08-26 -- Chart drawing delete and wick-accurate placement

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / chart (continuity-only for drawing keys)
- **Related:** `CHANGELOG.md` 2026-08-26 Delete key removes the selected chart drawing · `PROBLEM_LOG.md` 2026-08-26 Delete key does not remove a selected chart line

## Task

User could select a vertical line but laptop Delete did not remove it. Horizontal, vertical, cross, and trend anchors also snapped to candle closes instead of wick highs/lows.

## Goal

Unmodified Delete or Backspace removes the selected drawing, and drawing anchors follow the exact cursor price. Order hotkeys that use Shift/Ctrl+Backspace stay untouched.

## Why it mattered

A selected line you cannot erase is dead weight on a live tape. Close-only placement also prevents marking the actual support/resistance extremes traders use.

## What we changed

- Added `chartDrawingKeys.ts` with `shouldDeleteSelectedDrawing`.
- `useChartDrawingManager` listens on window keydown and calls `DrawingManager.removeDrawing` for the selected id.
- Added `chartInteractionConfig.ts`; the price chart uses `CrosshairMode.Normal`.
- Toolbar X tooltip now says Delete/Backspace removes the selected line.

## How it works now

The drawing library owns selection. Nova removes its selected id for plain Delete/Backspace. Normal crosshair mode leaves the click at the cursor Y, so `series.coordinateToPrice(point.y)` can resolve wick highs/lows or any in-between price.

## Why this approach

The library has no built-in delete key. Tracking selection ourselves would drift, so `getSelectedDrawing()` stays the SSOT. For placement, changing the upstream crosshair mode removes the close snap for every drawing tool without inventing custom OHLC snapping rules. Rejected: forcing anchors to high/low based on candle color; that would still prevent arbitrary placement and misunderstands wick direction.

## Verification

- `npx vitest run src/chart/chartInteractionConfig.test.ts src/chart/chartDrawingKeys.test.ts src/components/TickerChartControls.test.tsx` -- 11 passed
- `npm run build` -- tsc + vite exit 0
- Live browser: DAIC 1m loaded with no chart error. A horizontal line placed near $5.90 while the candle close was about $5.68, proving free cursor placement. The test line was cleared afterward. Unit test covers `removeDrawing('verticalline-1')` on Delete.

## Follow-ups

None unless a future Delete Nova Action is added -- then this handler must stay in front and only fire when a drawing is selected.

## Keywords

chart, drawing, wick, tail, candle close, CrosshairMode, Magnet, Normal, VerticalLine, Delete, Backspace
