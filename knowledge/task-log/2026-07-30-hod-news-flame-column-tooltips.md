# 2026-07-30 -- HOD News flame column + calculation tooltips

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo | widgets (display)
- **Related:** `CHANGELOG.md` 2026-07-30 -- HOD table News flame + column calculation tooltips

## Task

Replace/extend HOD columns toward a Warrior-like layout with a news fire symbol, header tooltips for column math, and a maintainable single source of truth for columns.

## Goal

News flame on HOD/Running Up rows (frontend join), honest calculation tooltips, no backend payload change, no sample/live or price-feed mixing.

## Why it mattered

Users need at-a-glance news context on HOD alerts and clear formulas so first-catch Time does not look stale when price/RVOL update.

## What we changed

- Moved `HOD_MOMO_COLUMNS` + new `HOD_MOMO_COLUMN_TOOLTIPS` into `frontend/src/hod_momo/hodMomoColumns.ts` (feature-local; shrunk `chart_api.ts`).
- Extracted shared `NewsCell` from `ScannerTable`.
- Added source-tagged `scannerNewsStore` + `buildNewsBySymbol` + `usePublishScannerNews`.
- Dashboard (live, history-cleared) and SampleDashboard publish unfiltered rows; table gates by live/sample.
- HOD row renders News flame; headers use `title` on `.th-inner`.
- Extracted `HodMomoStrategyFilter` to keep `HodMomoAlertTable` under component size limit.

## How it works now

News is display-time only: `Map<string, string>` of symbol to ISO headline time. `AlertObject` is never mutated. Store retains last map for Trader dock but ignores mismatched source (sample vs live). Time remains first-catch; tooltips document live metric refresh.

## Why this approach

Rejected mounting a second `useScannerData` in `HodMomoProvider` (would open a competing `/ws/scanner` and fight L1 budget). Rejected putting news on backend alerts (heavier, not needed for a display join). Rejected importing `NewsCell` from `ScannerTable` internals (cross-feature drag). Source tag is required because `leaveSampleView` is pushState with no reload. Typed map forbids price/volume mixing.

## Verification

- `npx tsc --noEmit`
- `npx vitest run` on `newsBySymbol`, `scannerNewsStore`, `HodMomoAlertTable.render`

## Follow-ups

- Sample Trader deep-link before sample dashboard visit: News dashes until publish.

## Keywords

HOD Momo, News flame, newest_headline_at, scannerNewsStore, column tooltips, first-catch Time
