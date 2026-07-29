# 2026-07-29 — Remove Gappers Small Cap sub-tab

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / scanner UI
- **Related:** `CHANGELOG.md` §2026-07-29 -- Remove Gappers Small Cap sub-tab

## Task

Remove the Gappers "Small Cap" sub-tab (and the All Gaps / Small Cap sub-tab bar).

## Goal

Gappers shows the full list only -- no market-cap filter sub-tabs.

## Why it mattered

Operator found the Small Cap filter unused clutter next to the main Gappers table.

## What we changed

- `frontend/src/components/ScannerTabPanels.tsx`: dropped `gapperSubTab` state, `smallCapGappers` filter, sub-tab bar; Gappers panel matches Gainers/Losers (table or empty state).
- Left `SMALL_CAP_MIN` / `SMALL_CAP_MAX` in frontend/backend constants (unused by this UI path).

## How it works now

`activeTab === 'gappers'` always renders `sortedGappers` (watchlist overlay + sort). No client-side $300M to $2B filter.

## Why this approach

Removed the whole sub-tab bar rather than keeping a lone "All Gaps" tab (one tab is noise). Kept tier constants for possible future filters / docs parity instead of a drive-by constants cleanup.

## Verification

Lint clean on `ScannerTabPanels.tsx`; structure matches Gainers panel.

## Follow-ups

Optional: delete unused `SMALL_CAP_*` if still unreferenced.

## Keywords

gappers, small cap, sub-tab, ScannerTabPanels, market_cap filter
