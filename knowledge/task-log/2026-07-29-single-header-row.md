# 2026-07-29 — Single header row (scanner chrome into GlobalAppBar)

- **Status:** completed
- **Agents:** parent
- **Domain:** UI shell
- **Related:** `CHANGELOG.md` §2026-07-29 -- Single header row

## Task

Merge the two top header rows (status chrome portal + GlobalAppBar) into one header without removing information.

## Goal

One 40px bar containing brand/nav, scanner status (mode + chips + history + lookup + theme), and account cluster.

## Why it mattered

Two stacked rows wasted vertical space above the three-column scanner.

## What we changed

- `GlobalAppBar` gained an optional middle scanner block (`GlobalAppBarScanner`)
- `ScannerBarBridge` + `scannerBarBridge` external store publish live scanner status
- `DashboardPage` mounts the bridge; `AppHeader` portal no longer renders on Scanner
- Sample: `GlobalAppBar` receives fixture scanner props from `SampleShell`
- Removed `SCANNER_STATUS_SLOT_ID` mount from AppShell
- Theme toggle lives in GlobalAppBar right cluster

## How it works now

Scanner publishes; GlobalAppBar subscribes. Trader shows GlobalAppBar without the scanner block. Sample shows fixture mode/chips/history/lookup in the same single bar.

## Why this approach

A bridge store avoids lifting `useScannerData` into AppShell (keeps Dashboard the scanner owner) while still rendering chrome in one component. External store + `useSyncExternalStore` avoids context re-renders for the whole app on every scanner tick.

## Verification

`npx tsc --noEmit`; Vitest dock persist + dock + TabNav + AppErrorBoundary.

## Follow-ups

`AppHeader.tsx` can be slimmed to the `MarketMode` type + history formatter once nothing imports its UI.

## Keywords

global app bar, header merge, scanner status, one header row
