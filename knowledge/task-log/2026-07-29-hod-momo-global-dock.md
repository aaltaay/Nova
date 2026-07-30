# 2026-07-29 — HOD Momo global AppShell dock

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / UI shell (HOD surface)
- **Related:** `CHANGELOG.md` §2026-07-29 -- HOD Momo global AppShell dock

## Task

Put the HOD Momo scanner on top of every page, collapsible/expandable with a middle/bottom resize bar, with sound architecture so the feed survives Scanner and Trader.

## Goal

Single stream owner above the Scanner/Trader fork; one UI (dock); rail focuses dock without a second full-page table; collapse/height persist; sample fixtures work without live WS.

## Why it mattered

HOD hooks lived only in `DashboardPage`, so opening Trader tore down the WebSocket. Full-page HOD tabs also fought the new left rail. Traders need HOD visible while in Stock View.

## What we changed

- Added `HodMomoProvider` / `HodMomoFixtureProvider` + shared `HodMomoContext`
- Added `HodMomoDock` (collapsed strip + expanded body + horizontal `ResizeHandle`)
- Persist helpers `hodMomoDockPersist` (`nova.hodMomo.dock.collapsed` / `heightPx`)
- Wired dock into live `AppShell` stack and SampleShell
- Rail `focusDock` + `railHighlight`; removed `TabModuleHost` HOD mount
- Integrity banner ownership: expanded HOD tab / dock only (dropped from `ScannerTabPanels`)
- Shell flex budget via `.nova-app-stack` / `.nova-app-branch`

## How it works now

`HodMomoProvider` owns `useHodMomoStream` + config once at AppShell. Dock sits after GlobalAppBar / attention strip. Default collapsed. Expanding shows `HodMomoSection` for `dockMode`. Left-rail HOD/Running Up calls `focusDock` and highlights the rail item while main-col keeps the last non-dock tab (usually Gappers). Trader no longer unmounts the HOD stream.

## Why this approach

- **Provider above fork** beats lifting hooks only into Dashboard -- Trader survival was the hard requirement.
- **Dock focus vs second table** avoids double mount / double WS and matches "HOD on every page" without blanking Gappers.
- **heightPx + horizontal ResizeHandle** instead of `useResizableHeight` -- that hook is a parent-% split for Stock View rail, wrong model for shell chrome.
- **Default collapsed** so first open of Trader is not half-crushed.
- **Fixture provider in SampleShell** because sample early-returns before live AppShell (cannot share the live provider mount).

Rejected: floating popup, separate HOD websocket, keeping full-page HOD host alongside dock.

## Verification

- `npm test -- --run src/hod_momo/hodMomoDockPersist.test.ts src/hod_momo/HodMomoDock.test.tsx src/components/TabNav.test.tsx`
- `npx tsc --noEmit`

## Follow-ups

- Dock-aware `HodMomoAlertTable` viewport height so a short dock does not nest a 30-row virtualizer scroll.
- Detached Stock View window dock (explicitly out of v1).

## Keywords

hod momo, running up, dock, AppShell, collapsible, resize, rail focus, WebSocket survival
