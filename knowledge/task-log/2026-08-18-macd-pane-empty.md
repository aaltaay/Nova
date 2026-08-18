# 2026-08-18 -- MACD pane empty with toggle on

- **Status:** completed
- **Agents:** parent
- **Domain:** charts / quote panel (continuity-only; fixed in-session)
- **Related:** `CHANGELOG.md` 2026-08-18 -- MACD pane renders · `PROBLEM_LOG.md` 2026-08-18 -- MACD pane empty

## Task

MACD was toggled on for SNDQ on the quote chart and the pane stayed blank.

## Goal

MACD histogram + MACD/signal lines visible under the price chart when the toolbar toggle is on.

## Why it mattered

The operator could not read momentum on the open ticker. The label and toggle said MACD was on, which is worse than an off switch.

## What we changed

- `computeMacdPane` / `computeRsiPane` keep one slot per price bar; warmup NaN becomes whitespace instead of dropping points.
- Oscillator paint waits for series refs and only records the paint key after `setData`.
- Quote/panel fill height remasures when oscillator panes mount.
- `.chart-body` clips overflow; `.chart-oscillators` does not shrink.

## How it works now

Price and oscillator charts share the same logical indices. Turning MACD on shrinks the price canvas so it cannot cover the pane. A later tick cannot skip paint because the first attempt ran before the pane chart existed.

## Why this approach

Rejected "only CSS overflow" -- that would unmask a canvas still showing the wrong window after warmup drop. Rejected "only pad MACD" -- the quote slot still lets a 340px price canvas sit on top of a 110px pane. Both layers were required. Did not move MACD onto the price pane (TradingView-style overlay) because the product already has a dedicated oscillator host.

## Verification

- `npx vitest run src/chartIndicators.test.ts src/chart/oscillatorPaint.test.ts src/chart/measureChartFillHeight.test.ts` -- 12 passed (alignment test was red first: 17 MACD points on 50 bars).
- `npm run build` -- `tsc -b && vite build` exit 0.
- Browser `http://localhost:5173` SNDQ 1m, MACD on: pane 110x796, price body 157px, MACD canvas sampled 2501 non-dark pixels.

## Follow-ups

Full Day / daily bars still skip non-numeric times in `rawBarsToIndicatorBars` (overlays and oscillators). Separate from this 1m quote-panel bug.

## Keywords

MACD, RSI, oscillator, quote panel, whitespace, fill height
