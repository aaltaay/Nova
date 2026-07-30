# 2026-07-29 -- Scanner status chrome above GlobalAppBar

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / chrome
- **Related:** `CHANGELOG.md` §2026-07-29 -- Scanner status chrome above GlobalAppBar

## Task

Put the scanner status/actions header above the GlobalAppBar and remove the homepage NOVA STOCK SCANNER brand header.

## Goal

Top strip = market badge + connection pills + reload + sample/history + SYMBOL; then GlobalAppBar; no duplicate brand block on Scanner.

## Why it mattered

Two headers competed: homepage brand + status, then GlobalAppBar. User wanted status as the top chrome only.

## What we changed

- Removed brand/logo from `AppHeader`
- AppShell mount `#nova-scanner-status-slot` above GlobalAppBar
- Live Scanner portals AppHeader into that slot (`portalToTop`)
- Top-chrome CSS strip styling

## How it works now

DashboardPage still owns scanner hooks; AppHeader portals into the shell slot. Trader unmounts Dashboard so the status slot empties (hidden when empty). Sample shell keeps inline status chrome without portal.

## Why this approach

Portal keeps data ownership on DashboardPage without lifting `useScannerData` to AppShell. Rejected lifting scanner hooks -- too large for a chrome move.

## Verification

`tsc --noEmit`; Vitest GlobalAppBar + SampleDashboardPage.

## Follow-ups

Optional: show a compact connection strip on Trader when Dashboard is unmounted.

## Keywords

AppHeader, GlobalAppBar, portal, status chrome, homepage header
