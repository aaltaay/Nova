# 2026-08-25 — Exchange filter fail-open + IB primaryExchange passthrough

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed (frontend scanner UI + IBKR roster admission)
- **Related:** `CHANGELOG.md` 2026-08-25 entry · `PROBLEM_LOG.md` 2026-08-25 — Exchange filter blanked the scanner desk

## Task

User reported "no gainers/losers/gappers" premarket. Investigate why the desk was empty and fix it.

## Goal

The scanner desk shows every row the backend has for the active table, regardless of whether that row's listing exchange is known yet. A client-side filter must never be the reason a real mover disappears without an on-screen explanation.

## Why it mattered

Two independent failures stacked on the same morning. The first (IB Gateway 2FA never completed, 03:40-08:53 ET) was already loud in `daily-start.log` and is not a code bug. The second was silent: once IB connected, the backend was correctly pushing 31 gappers and 50 gainers over `/ws/scanner`, but the UI rendered exactly 1 row and gave no indication why. A trader watching the desk had no way to tell "the feed is dead" from "the filter ate my rows" -- both look identical (empty table, no error banner). That ambiguity is exactly what `single-market-data-feed.mdc` rule 4 (fail loud, not quiet) exists to prevent, and the existing exchange filter violated it silently for a year: it defaulted to NASDAQ-only and dropped every row whose exchange it did not recognize.

## What we changed

- `backend/exchanges.py`: added `normalize_ib_exchange()` mapping IB's raw `contract.primaryExchange` (plus known aliases like `ISLAND` -> `NASDAQ`) onto the same option set the frontend filter understands. Returns `None` for anything unrecognized -- never a guess.
- `backend/ibkr/scanner_stream.py`: `_symbols_from_rows` now returns `(symbols, exchange_map)` instead of just symbols, reading `contract.primaryExchange` off the same IB scan row we already read the symbol from (zero extra IB calls). Threaded through `_on_batch` -> `_pending_hydrate` -> `_hydrate_pending` -> `commit_table`.
- `backend/ibkr/scanner_hydrate.py`: `stub_row()` and `hydrate_rows()` accept an optional `exchanges` map. A new stub gets its exchange for free; an existing row backfills an unknown exchange but a known exchange is never overwritten.
- `frontend/src/hooks/useExchangeFilter.ts`: extracted the filter predicate into an exported pure function `filterRowsBySelection()` and changed its logic to fail open -- a row is only dropped when its exchange is **known** and **not selected**. A null/empty/unrecognized exchange is always kept.
- `frontend/src/constantGroups/market_ui.ts`: `SCANNER_EXCHANGE_DEFAULTS` changed from `['NASDAQ']` to all `SCANNER_EXCHANGE_OPTIONS`.
- `frontend/src/pages/DashboardPage.tsx` + `frontend/src/styles/settings-workspace.css`: added a visible "N rows hidden by exchange filter" banner on the active scanner tab whenever the filter actually removes rows, so a future narrower selection cannot silently blank the desk again.
- Backend tests: `backend/tests/test_exchanges.py` (normalize cases), new `backend/tests/test_scanner_stream_exchange.py` (`_symbols_from_rows` ranking + exchange map + alias + unknown-venue drop), `backend/tests/test_scanner_session_adr008.py` (hydrate stub/backfill/no-overwrite), fixed the 2-tuple `_pending_hydrate` literal in `backend/tests/test_market_data_op_metrics.py` to the new 3-tuple shape.
- Frontend tests: rewrote `frontend/src/hooks/useExchangeFilter.test.ts` to import the real `filterRowsBySelection` (it previously re-implemented the buggy predicate locally, so it could never catch this regression) and assert fail-open + all-exchanges-default.

## How it works now

IB's scanner API mostly does **not** populate `contract.primaryExchange` on raw scan rows (confirmed live: only 2 of 81 rows across Gappers+Gainers carried it after the fix landed -- one from the existing Alpaca-populated ticker-detail path, one genuinely new from IB). So the backend passthrough is a real but marginal improvement, not the fix. The fix that actually matters is the frontend: `filterRowsBySelection` only excludes a row when its exchange is both known and deselected, and the default selection is now every option, so a fresh install or a fresh localStorage profile can never blank the desk just because IBKR admission hasn't attached a listing exchange yet. If a user narrows the filter later (e.g. NASDAQ only) and that hides real rows, the new banner says exactly how many and where to fix it (Settings > General), instead of a quiet empty table.

## Why this approach

Considered tightening the filter's data source instead (e.g. blocking IBKR discovery until every row has an exchange). Rejected: that reintroduces the exact "wait for a cold round trip before admitting a row" anti-pattern that the 2026-08-24 outage (`PROBLEM_LOG.md`) already fixed via names-first admission -- ADR 010 decision 5 is explicit that admission must never depend on enrichment. Considered leaving the NASDAQ-only default and only fixing fail-open: rejected because a *known*, non-NASDAQ row (real NYSE/AMEX/ARCA movers) would still vanish by default with no visible cause, which is the same silent-hide failure mode one layer down. Doing both (fail-open predicate + all-exchanges default) means the filter can only ever narrow what a user explicitly asked to narrow, and the new hidden-count banner makes even that explicit narrowing visible instead of silent. Extracting `filterRowsBySelection` as an exported pure function was necessary because the pre-existing test file re-implemented the filter logic inline -- it was testing a copy of the bug, not the real code, so it could pass forever while the real filter stayed broken.

## Verification

- `py -3 -m pytest -q` (backend, excluding a pre-existing unrelated `tools` import collection error in `test_execution_latency_regressions.py`): 1289 passed.
- `npx vitest run` (frontend): 707 passed, 1 pre-existing flake (`htkFormat.test.ts` dynamic-import timeout under full-suite load; passes in isolation, unrelated to this change).
- `npm run build`: clean.
- Live verification: restarted the local API, reconnected to IB Gateway (already logged in), reprobed `/ws/scanner` directly and confirmed `roster_replace` carries 31 gappers / 50 gainers. Loaded the app in-browser: nav badges went from `Gappers 1` / `Gainers 1` to `Gappers 31` / `Gainers 50`, full roster renders with only AMIX/BDRX showing an exchange chip (the two IB actually supplied), confirming fail-open renders unknown-exchange rows correctly.

## Follow-ups

- IB's scanner API rarely populates `primaryExchange` on scan rows. If per-row exchange labels matter more going forward, the real source is a qualified-contract lookup (like `ibkr/listing_flags.py` already does for the detail panel), not the scan result -- that would cost an extra IB round trip per new symbol and was out of scope here since the filter no longer depends on it for correctness.
- The `IBKR discovery bridge failed (ibkr): TimeoutError` + `run_coro timed out after 25.0s` warnings repeating every ~30s in `api-console.log`, and `/api/ibkr/status` being polled ~14,000 times in a 30k-line log window, were observed during investigation but are out of scope for this fix (told to the user, not fixed).

## Keywords

exchange filter, SCANNER_EXCHANGE_DEFAULTS, filterRowsBySelection, fail open, blanked desk, primaryExchange, normalize_ib_exchange, scanner_hydrate, scanner_stream, single-market-data-feed, hidden rows banner, IB Gateway 2FA, gappers empty, gainers empty
