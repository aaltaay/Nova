# 2026-07-29 — HOD dock middle-column only (3-column scanner)

- **Status:** completed
- **Agents:** parent
- **Domain:** UI shell / HOD
- **Related:** `CHANGELOG.md` §2026-07-29 -- HOD dock middle-column only · prior `2026-07-29-hod-momo-global-dock.md`

## Task

Keep left scanner rail and right quote panel as full-height side columns; put HOD Momo only in the middle column above the selected scanner (with a title).

## Goal

Three-column Scanner: rail | (HOD dock + titled selected scanner) | quote. Provider still above Trader fork for WS survival.

## Why it mattered

Full-width AppShell dock sat above the whole shell and stole height from the side "kings." User annotated the intended layout clearly.

## What we changed

- Removed full-width `HodMomoDock` from AppShell chrome
- Mounted dock in `DashboardPage` / `SampleDashboardPage` `main-col--scanner-stack`
- Added `SelectedScannerWidget` with registry title
- Trader: dock inside `main-col--trader-stack` only
- Persist keys `v2`; default expanded

## How it works now

Side rails stretch the full scanner height. Middle stacks HOD (collapsible/resizable) over the active scanner/account/watchlist body, which has an explicit title (Gappers, Gainers, …).

## Why this approach

Middle-column mount preserves the three-column contract without a second HOD host. Provider stays at AppShell so Trader still does not tear down the WS. Key bump resets a prior collapsed localStorage that hid the dock after the first ship.

## Verification

`npx tsc --noEmit`; Vitest dock persist + dock + TabNav.

## Follow-ups

Hard refresh (Ctrl+Shift+R) after pull so Vite picks up the CSS/layout.

## Keywords

hod momo, middle column, three column, sidebar, quote panel, selected scanner title
