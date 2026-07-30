# 2026-07-29 -- Webull-style left scanner rail

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / scanner UI
- **Related:** `CHANGELOG.md` §2026-07-29 -- Webull-style left scanner rail

## Task

Move horizontal scanner tabs to a Webull-like left rail.

## Goal

Icon+label vertical nav for Gappers…Watchlist; Account/Settings remain on GlobalAppBar.

## Why it mattered

Horizontal tab bar consumed vertical space and did not match the Webull desktop pattern the user wants.

## What we changed

- `ScannerSideNav` replaces horizontal `TabNav` UI
- `scannerNavIcons` + `scanner-side-nav.css`
- Dashboard + Sample shell: rail sibling of `main-col`
- e2e/Vitest updated

## How it works now

`.nova-shell` = left rail | main content | quote panel. Registry `listTabModules()` drives items; visibility filter unchanged; count badges cap at 99+.

## Why this approach

Only real Nova tabs (no fake Webull Markets/Screener stubs). Kept Account/Settings on GlobalAppBar to avoid undoing the prior chrome move. Portal status chrome unchanged.

## Verification

Vitest TabNav/ScannerSideNav + scannerNavIcons + SampleDashboard + registry; `tsc --noEmit`.

## Follow-ups

Optional hamburger collapse; optional Trader-side compact rail.

## Keywords

scanner, side nav, Webull, TabNav, Gappers
