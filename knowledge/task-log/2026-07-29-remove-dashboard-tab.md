# 2026-07-29 -- Remove Dashboard tab; Gappers homepage

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / scanner UI
- **Related:** `CHANGELOG.md` §2026-07-29 -- Remove Dashboard tab; Gappers is homepage

## Task

Remove the Dashboard tab; make Gappers the scanner homepage.

## Goal

No Dashboard in TabNav; first paint shows Gappers; config remains in Settings.

## Why it mattered

After Settings absorbed exchange/Alpaca config, Dashboard was only a pointer page and stole the default tab.

## What we changed

- Dropped `dashboard` from `TAB_MODULE_IDS` / `NOVA_MODULES`
- `DEFAULT_ACTIVE_TAB = 'gappers'`
- Deleted `DashboardTab.tsx`; removed host branch in `TabModuleHost`
- Updated e2e baseline + registry/visibility tests

## How it works now

Scanner shell opens on Gappers. Settings gear owns configuration. Mode auto-switch still prefers Gainers (RTH) / Afterhours / Gappers without a Dashboard special case.

## Why this approach

Delete the tab entirely rather than hide it -- no dead registry id, no Modules-menu zombie. Kept `DashboardPage` as the scanner shell name (layout host), only removed the tab module.

## Verification

Vitest registry + moduleVisibility; `tsc --noEmit`.

## Follow-ups

None.

## Keywords

dashboard, gappers, homepage, TabNav, DEFAULT_ACTIVE_TAB
