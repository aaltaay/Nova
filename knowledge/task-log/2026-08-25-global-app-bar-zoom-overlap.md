# 2026-08-25 -- Global app bar no longer overlaps on zoom

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / market-feed chrome
- **Related:** `CHANGELOG.md` § Global app bar wraps on zoom · `PROBLEM_LOG.md` § Global app bar overlaps when zoomed

## Task

The header smashed into itself when the operator zoomed: MARKET CLOSED on Scanner/Trader, lock on BP, Account/Working/Settings cramped.

## Goal

Neighbors keep their own boxes at typical zoom (125% of 1920 = 1536 CSS px) and at a 1100 CSS px window.

## Why it mattered

A zoomed desk is a normal trading setup. Overlapping chrome hides session state and makes the lock / Settings unclickable.

## What we changed

- Replaced the shrinking nowrap flex row with a three-column grid.
- Below 1680px, scanner status (mode, Desk, lookup) moves to its own row.
- Removed the flex spacer that stole scanner width.
- Split menus + breakpoints into sibling CSS files so the base sheet stays under 400 lines.
- Dock tabs `flex-shrink: 0` with a wrapping bar so LIVE/Clear cannot sit on HOD Momo.

## How it works now

Wide desk: brand+nav | scanner | account cluster. Zoomed / laptop: brand+nav and account stay on row 1; scanner gets row 2. BP / Day P&L / Net Liq still hide on the old width schedule. Nothing uses overflow to paint on a neighbor.

## Why this approach

Rejected "overflow: hidden + shrink" -- that only clipped Look Up to "Look" and still looked broken. Rejected always-two-rows -- wastes a strip on a 1920@100% desk. 1680px is the break because 1920 at 125% zoom is 1536, which must already be two rows.

## Verification

- `npx vitest run src/components/GlobalAppBar.test.tsx` -- 13 passed (includes no-spacer + Market Closed).
- agent-browser `getBoundingClientRect` at 1100 and 1536: trader/mode, cluster/lock, Account/Settings all `hit: false`; Look Up width ~79px (full label).
- 1800px stays one row (`sameRow: true`, barH 45).

## Follow-ups

Hard-refresh if Electron is serving a cached bundle. Do not commit unless asked.

## Keywords

global-app-bar, zoom, overlap, header, dock tabs
