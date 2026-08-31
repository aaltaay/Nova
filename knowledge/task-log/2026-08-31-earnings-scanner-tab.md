# 2026-08-31 — Earnings scanner tab (Finnhub calendar, 1c layout)

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / frontend scanner tabs
- **Related:** `CHANGELOG.md` 2026-08-31 "Earnings tab (Finnhub calendar, day bands + BEFORE OPEN/AFTER CLOSE)" · `DEFERRED_LOG.md` D-008 (pre-existing, unrelated) · `.cursor/rules/single-market-data-feed.mdc` (Earnings carve-out added)

## Task

User attached a wireframe (design exploration "1c": day-grouped stream with BEFORE OPEN / AFTER CLOSE lanes, Today/Tomorrow/This week/This month range chips) and asked for a new "Earnings" scanner tab matching that layout. Same rule as every other scanner: clicking a ticker opens Trader immediately.

## Goal

- A left-rail Earnings tab visually close to the 1c wireframe.
- Calendar data limited to what a real, already-integrated API actually returns -- no invented implied-move/IV/surprise-% formula.
- Ticker click follows the existing ADR 011 row-vs-ticker contract (blue ticker button opens Trader; card body only selects the Quote Panel symbol).

## Why it mattered

The user was explicit: "we don't need to invent an algorithm... just use what these APIs are able to offer... this is not standalone software, this is a small feature." The risk was building a bespoke options-pricing feature on top of a free calendar API that has no options chain, which would mean fabricated numbers on a trading desk -- a domain-safety problem, not just a UX one.

## What we changed

**Backend**
- `backend/earnings_calendar.py` -- Finnhub `/calendar/earnings` fetch, single widest-window ("month") cache with 15 min TTL, disk snapshot (`schema_version`, owner-documented per persisted-state.mdc) so a restart doesn't block on Finnhub, and day/lane grouping (`build_earnings_view`) that slices the cached rows per range without a second network call.
- `backend/earnings_enrich_hooks.py` -- single-flight background thread that warms the yfinance fundamentals cache for the current day's symbols only (mirrors `mover_enrich_hooks.py`'s coalescing pattern; avoids the 2026-08 Yahoo-socket pile-up class of bug).
- `backend/fundamentals.py` -- added `company_name` (`longName`/`shortName`) to the dict already built from the existing `yf.Ticker(symbol).info` call -- no new network path.
- `backend/routes/earnings.py` + `backend/app_routers.py` -- thin `GET /api/earnings?range=` route.
- `backend/constants_scanner.py`, `.env.example` -- `FINNHUB_API_KEY`, TTL, window, and lane-preview constants (no magic numbers).

**Frontend**
- `frontend/src/earnings/` -- `EarningsPanel.tsx` (range chips + error/empty states), `EarningsDayBand.tsx`, `EarningsLane.tsx` (truncate + "+N more"), `EarningsCard.tsx` (ticker button + name/sector/mcap + EPS est/actual), `useEarningsCalendar.ts` (own poll, not folded into `useScannerData.ts`).
- `frontend/src/types/earnings.ts`, `frontend/src/constantGroups/features.ts` (range labels, session labels, poll cadence, no-key message).
- Registry wiring: `workspace/registry.ts` (`earnings` tab, `feedDeps: ['none']`), `workspace/scannerTabs.ts`, `scanner/scannerNavIcons.tsx`, `components/TabModuleHost.tsx` (renders `EarningsPanel` directly, not through `ScannerTabPanels`).
- `pages/SampleDashboardPage.tsx` -- passes `sampleMode` so the fixtures-only sample dashboard never mounts the real fetch.

## How it works now

Earnings is a **calendar metadata tab**, architecturally the same class as Catalysts/Large Cap in the sense that it is not IBKR-scanner-driven, but unlike either of those it has **zero** feed dependency (`feedDeps: ['none']`) -- no `/ws/scanner` price patches, no L1 subscriptions, no HOD Momo admission. `GET /api/earnings` always serves from one shared cached Finnhub fetch (the month window); range switching in the UI is a client-visible `?range=` query but a cache-hit server-side unless the TTL has expired. Company name / sector / market cap come from the yfinance fundamentals cache at **read time only** (cache-only lookup, mirroring `mover_enrich_view.decorate_rows`) -- a cold cache just shows a dash until the background warm thread fills it in, never a blocking per-row Yahoo call on the request path. Missing `FINNHUB_API_KEY`, an HTTP failure with no stale snapshot, or an unknown `schema_version` on disk all return a loud `error` string in the payload -- an empty `days` list is never silently treated as "no earnings this week." Ticker click behavior is a plain-div reimplementation of the `SelectableTableRow` row-vs-ticker split (a `<tr>`-based component cannot be reused in a card grid), so the blue `SymbolSelectButton` is still the only element that calls `onOpenTrading`.

## Why this approach

- **Finnhub over a second Yahoo call:** yfinance has no calendar-range earnings endpoint (only a single symbol's next/last date), so a calendar tab needs a second data source regardless. Finnhub's free tier covers exactly the fields the wireframe needs (date, session, EPS/revenue estimate+actual) with one HTTP call per TTL window instead of one call per symbol.
- **Cache the widest window once, slice in memory:** avoids a Finnhub call per range chip click (today/tomorrow/week all nest inside month) -- important on a free-tier rate limit, and it means switching range chips feels instant after the first load.
- **Cache-only fundamentals decoration + background single-flight warm, not a blocking per-row Yahoo fetch:** a "This week" range can span 60-120+ symbols; fetching each synchronously in the request path would make the tab feel broken. The existing `mover_enrich_hooks.py` single-flight pattern was already proven against exactly this failure mode (a 2026-08 incident where uncoalesced warms stacked hundreds of Yahoo sockets) -- reusing it instead of inventing a new concurrency primitive.
- **No `<tr>` reuse for cards:** `SelectableTableRow` renders a `<tr>`, which is invalid outside a `<table>` and unreliable with flex/grid card layout. Rather than force a table layout onto card lanes (fighting the wireframe's actual visual intent), the row-click contract was reimplemented as a plain div with the same event semantics.
- **Explicitly not implementing implied move / IV / surprise-%:** the wireframe shows these, but they require an options chain. The user pre-empted this with "if... you are not able to do it cleanly, then don't do it" -- so v1 ships only Finnhub's real EPS estimate/actual fields, labeled as such, with implied-move/IV named as an explicit non-goal in code comments and the rule update, not silently dropped.
- **Rejected: folding Earnings into `useScannerData.ts` / `ScannerTabPanels`.** Both are already near their line-count ceiling and are wired to `/ws/scanner` + `useScannerPriceStream`'s `SCANNER_TABS` set, which drives real IBKR L1 budget. Earnings has no L1 subscription at all; adding it to that machinery would either be dead code or an accidental door to streaming hundreds of calendar symbols through the scanner L1 pool.

## Verification

- `py -3 -m pytest backend/tests/test_earnings_calendar.py backend/tests/test_earnings_enrich_hooks.py backend/tests/test_routes_earnings.py -q` -- 16 passed.
- `py -3 -m pytest -q` (full backend suite, from `backend/`) -- 1472 passed, 1 failed. The 1 failure is `test_mover_columns.py::test_decorate_rows_attaches_earnings_window`, reproduced identically on a clean `git stash` of this session's changes (pre-existing order-dependent test-isolation flake, already tracked as `DEFERRED_LOG.md` D-008) -- not caused by this change.
- `npx vitest run` (frontend) -- 177 test files / 855 tests passed, including new `src/earnings/EarningsCard.test.tsx`, `EarningsLane.test.tsx`, `EarningsPanel.test.tsx`, and an added case in `workspace/registry.test.ts` asserting `feedDeps: ['none']` and `tabUsesScannerPricePatch('earnings') === false`.
- `npm run build` -- exit 0, no TypeScript errors.
- Not yet done: a live browser click-through (open Earnings tab, switch range chips, click a ticker, confirm Trader replaces the active tab per ADR 011) -- backend requires a live `FINNHUB_API_KEY` to show real rows; recommended as the next verification step before calling this fully desk-verified.

## Follow-ups

- No implied move / IV / options-derived metrics -- would need a real options-chain integration; not parked as a bug, just out of v1 scope by explicit user direction.
- No filter rail, calendar-month grid (wireframe 1b), or ranked trade-board (wireframe 1d) -- only 1c shipped.
- Live browser verification of the ticker-click-opens-Trader path with a real Finnhub key is still outstanding (see Verification).

## Keywords

earnings, Finnhub, calendar, EPS, BMO, AMC, scanner tab, registry, ADR 011, single-market-data-feed, mover_enrich_hooks, single-flight
