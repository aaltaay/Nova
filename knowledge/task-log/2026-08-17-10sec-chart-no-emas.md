# 2026-08-17 -- 10-Second chart defaults to no EMAs

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets
- **Related:** `CHANGELOG.md` §2026-08-17 -- 10-Second chart defaults to no EMAs · `PROBLEM_LOG.md` n/a

## Task

Hide moving-average lines on the 10-second Trader chart.

## Goal

10Sec opens without 9/20/50/200 EMAs. Other panes unchanged. Operator can still turn EMAs on.

## Why it mattered

The 10s pane is for tape-speed price action. Four EMA lines sit on top of clicks and drawings.

## What we changed

`CHART_GRID_PANE_INDICATORS['10Sec'] = ['vwap']` instead of falling through to `CHART_DEFAULT_INDICATORS` (emas + vwap).

## How it works now

Grid pane defaults are per timeframe. 10Sec is VWAP only. The EMAs toolbar button still works.

## Why this approach

Rejected removing the EMAs control (some days you still want them). Rejected also killing VWAP (one session line, not the four the operator marked). Rejected a special-case hide in the overlay renderer -- the pane-default table is already the SSOT.

## Verification

`npx vitest run src/components/ChartGrid.test.tsx` -- 3 passed.

## Follow-ups

Refresh Trader if the 10s pane was already mounted with EMAs on.

## Keywords

10Sec, EMA, chart overlays, CHART_GRID_PANE_INDICATORS
