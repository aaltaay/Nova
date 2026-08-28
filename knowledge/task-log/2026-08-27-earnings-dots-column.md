# 2026-08-27 -- Earnings dots column on day-trade scanners

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-08-27 Earnings dots · `PROBLEM_LOG.md` 2026-08-27 Large Cap last-report countdown

## Task

Add an Earnings column to Gappers / Gainers / Losers / Afterhours that shows three dots for the day before, the earnings day, and the day after, sourced from Yahoo the same way float already is. Leave HOD Momo and Running Up alone.

## Goal

A trader can scan a table and see which names have earnings around now, and hover a dot to read the date and before-open / after-close timing.

## Why it mattered

Earnings move these names. The quote panel already showed a date, but the scanner tables did not, so the operator had to open tickers one by one. A leftover party-badge design from 2026-07-15 never shipped (constants and CSS only).

## What we changed

- New `backend/earnings_window.py`: ET calendar offset and BMO/AMC session from a Yahoo epoch.
- `fundamentals.py` now stores `earnings_ts`, `earnings_estimated`, and `earnings_next_date`. Dropped the dead `earningsDate` lookup.
- `mover_enrich_view.decorate_rows` attaches the scanner fields at serialize time (does not mutate frozen rosters).
- `large_cap_metrics.build_row_metrics` counts down from `earnings_next_date`.
- Frontend `EarningsDots` + `SCANNER_COLUMNS` entry after Symbol. Orphan `EARNINGS_TODAY_*` constants and `.symbol-earnings-party` CSS removed.

## How it works now

Yahoo `.info` has two clocks: `earningsTimestamp` is the event of record (today / yesterday / tomorrow for the dots); `earningsTimestampStart` is the next scheduled date (Large Cap countdown). The existing 15-minute yfinance cache and mover roster-commit warm thread already fetch this. No new endpoint, no new IB work, no HOD column.

## Why this approach

A dedicated `/api/earnings-today` batch (the 2026-07-15 sketch) would have added a second Yahoo path and a 25-symbol cap. Decorating at read time reuses the cache that already fills float / short interest / market cap. Three dim dots (not an em-dash) keep column width stable so the widget reads as one control. Offset is a number so the existing sorter groups in-window names without a custom comparator.

Rejected: emoji on the ticker button (hides timing), a countdown like Large Cap on day-trade tables (wrong grain for a same-day catalyst), and a new fetch loop modeled on news (news is Alpaca text; this is already in yfinance `.info`).

## Verification

- `py -3 -m pytest tests/test_earnings_window.py tests/test_mover_columns.py tests/test_large_cap_metrics.py tests/test_fundamentals_dates.py -q` -- 45 passed
- `npx vitest run src/components/EarningsDots.test.tsx src/components/SelectableTableRow.test.tsx` -- 10 passed
- `npm run build` -- exit 0
- Live `/api/afterhours`: ESTC, GAP, AFRM `earnings_day_offset=0` session `amc`; `/api/movers` OKTA `-1`
- Browser After Hours: Earnings header, 50 dot widgets, 3 lit center dots; HOD Momo headers have no Earnings column

## Follow-ups

Gappers had 0 rows at 21:51 ET (frozen empty). The column is on `SCANNER_COLUMNS` so it appears when that roster has names. Yahoo sometimes sets `isEarningsDateEstimate=True` with no timestamp; those rows stay dim with "No earnings date".

## Keywords

earnings, yfinance, earningsTimestamp, earningsTimestampStart, decorate_rows, EarningsDots, scanner column, BMO, AMC
