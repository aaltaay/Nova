# 2026-08-17 -- Scanner dock pills for roster tables

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / UI shell
- **Related:** `CHANGELOG.md` §2026-08-17 -- Scanner dock pills for Gappers / Gainers / Losers / AH / Catalysts

## Task

Add the other scanners next to HOD Momo / Running Up in the top dock so Trader can open Gappers, Gainers, Losers, After Hours, and Catalysts without leaving the desk.

## Goal

Same dock row, more pills. Clicking a roster pill expands the dock and shows that table. Scanner data stays alive across Scanner | Trader.

## Why it mattered

Trader only had HOD / Running Up chrome. The IBKR roster tables lived on the Scanner left rail, which unmounts with DashboardPage when Trader is shown. The operator could not watch Gappers while charting.

## What we changed

- Extended dock modes with Gappers / Gainers / Losers / AH / Catalysts
- Lifted `useScannerData` into `ScannerDataProvider` on AppShell
- Dock reads live rows (or sample fixtures) via `useScannerDockRows`
- Roster mode hides HOD Clear / Configure
- Selecting a roster pill sets L1 `activeTab` so that table stays streamed

## How it works now

HOD Momo and Running Up still partition the HOD alert feed. The pills after the divider are IBKR roster tables from the same `/ws/scanner` owner that Dashboard used to mount alone. Trader and Scanner share that owner, so opening Trader no longer tears down roster fetch. Former Momo stays a chip inside HOD Momo -- it is not a separate dock scanner.

## Why this approach

- **Lift the feed, do not remount Dashboard.** Keeping DashboardPage hidden under Trader would mount two docks and a second HOD table. A provider above the fork matches HodMomoProvider.
- **Roster pills, not more HOD partitions.** "Other scanners" in Nova are Gappers / Gainers / Losers / AH / Catalysts. Former Momo is strategy #1 inside HOD, and sample fixtures already misuse id 1 as "HOD Break".
- **Optional roster source.** Tests without a feed still see only HOD / Running Up. Sample uses fixtures and never opens live WS.
- Rejected putting Gappers only on the Scanner rail -- that is invisible in Trader, which is where the ask was pointed.

## Verification

- `npx vitest run` hod_momo + scanner + sample dashboard + wiring + TabNav -- 51 passed
- `npx tsc --noEmit` exit 0
- `npm run build` exit 0

## Follow-ups

- Watch column in the dock uses an empty overlay on live (full watchlist stays on the Scanner Watchlist tab)
- Dock does not switch the Scanner main-column tab -- two tables can be visible at once on Scanner
- Former Momo as its own pill is still available if wanted later (needs sample fixture id cleanup)

## Keywords

scanner dock, gappers, gainers, losers, after hours, catalysts, trader, HodMomoDock, ScannerDataProvider
