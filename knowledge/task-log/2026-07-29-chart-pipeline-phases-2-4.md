# 2026-07-29 — Chart pipeline Phases 2-4: store, lifecycle, grid

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / charts
- **Related:** `CHANGELOG.md` §Phases 2-4 · `PROBLEM_LOG.md` §Chart UI remount · Phase 1 `2026-07-29-chart-bars-phase1-cache.md`

## Task

Finish the chart re-architecture after Phase 1: frontend store, incremental updates, stable instances, capacity cuts, and verification.

## Goal

Opening a ticker / switching Trader tabs no longer remounts four LWC trees, polls hidden panes, or waits on quote detail before historical starts.

## Why it mattered

Backend cache alone could not stop UI storms: remounts, inactive-tab polls, full `setData`, and detailReady serialization still overwhelmed charts.

## What we changed

- `frontend/src/chart/barsStore.ts` + `ensureBars` / `ensureBarsBatch`
- `useChartBars` store-first + incremental tail `update`
- `tickerChartData` day-cached ET offset + `rawBarsToSeries` / `canIncrementalBarsUpdate`
- `useChartInstance` create-once (resize via `applyOptions` only)
- `chartActive` from `StockViewTabs` → page → grid → chart (pause refetch/resize)
- `ChartGrid` batch warm, 3-pane default, 15m opt-in toggle
- Charts mount without `detailReady`; overlays skip paint on unchanged revision
- Tests: barsStore, tickerChartData, ChartGrid, stockViewTerminal gate update

## How it works now

Active tab: ChartGrid batch → store → panes paint (incremental when prefix matches). Hidden tabs keep DOM for L1/L2 but charts do not poll. Maximize does not `chart.remove()`.

## Why this approach

**Required.** Kept inactive tabs mounted (L1/L2/tape hot) but paused chart work only -- unmounting tabs would regress depth/tape. Rejected React Query dependency; a tiny module store matches existing patterns. 15m opt-in preserves the future tape slot without defaulting to four historicals.

## Verification

`npx vitest run` chart + ChartGrid + stockViewTerminal suites (31); `tsc --noEmit`; Phase 1 pytest 18 still green.

## Follow-ups

Optional: indicator Web Worker if profiling still shows jank; IndexedDB persistence for cold start.

## Keywords

barsStore, chartActive, incremental bars, useChartInstance, ChartGrid, detailReady, Phase 2, Phase 3, Phase 4
