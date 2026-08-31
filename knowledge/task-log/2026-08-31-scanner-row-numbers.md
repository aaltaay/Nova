# 2026-08-31 -- Scanner row numbers

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / scanner UI
- **Related:** `CHANGELOG.md` 2026-08-31 scanner tables show a # row number · problem_log=n/a · deferred_log=none

## Task

Add a row-number column to every scanner table except HOD Momo / Running Up.

## Goal

Visible 1-based `#` on Gappers, Gainers, Losers, After Hours, Large Cap, Catalysts, and Watchlist. Dock alert tables stay Time-first with no `#`.

## Why it mattered

The operator needs to call out a row by number ("look at row 3") on the ranked scanners. HOD / Running Up are alert docks, not ranked IB scans, so numbering them would fight their Time-first layout.

## What we changed

- Shared `ScannerRowNumHeader` / `ScannerRowNumCell` in `ScannerTable.tsx`, used by Catalysts and Watchlist.
- Constants `SCANNER_ROW_NUM_LABEL` / `SCANNER_ROW_NUM_TITLE` in `market_ui.ts`.
- Narrow `#` column CSS in `scanner-l2.css`.
- Vitest for display indexing and "not sortable".

## How it works now

`#` is the 1-based index of the currently displayed list after client sort and exchange filters. It is not IB `rank` and clicking the header does not sort. HOD Momo / Running Up still use `hodMomoColumns.ts` with no `#`.

## Why this approach

Display index beats IB rank here: after the operator sorts by volume, "row 3" still means the third visible row. Putting `#` in `SCANNER_COLUMNS` would make it sortable and would show a jumping IB rank after other sorts, which is a different feature. A dedicated first column keeps that door closed. Shared header/cell helpers avoid three copy-pasted `<th>#</th>` blocks.

Rejected: numbering HOD/Running Up (explicitly excluded). Rejected: Signals / Decision / Journal (those are not ranked scanners).

## Verification

`npx vitest run src/components/ScannerTable.test.tsx` (pass). `npm run build` exit 0. Live UI: Gappers 1-19, Gainers 1-50, Losers 1-50, Large Cap 1-48, Catalysts 1-2, Watchlist 1-58. HOD/Running Up still News/Time/Symbol with no `#`.

## Follow-ups

If the operator later wants IB rank that stays glued to the symbol after sort, add a separate Rank column -- do not overload `#`.

## Keywords

scanner, row number, gappers, gainers, watchlist, catalysts, hod momo
