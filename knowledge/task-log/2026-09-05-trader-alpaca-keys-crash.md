# 2026-09-05 -- Trader crash on missing Alpaca keys

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-09-05 Trader crash · `PROBLEM_LOG.md` 2026-09-05 -- Trader toUpperCase · `DEFERRED_LOG.md` none (D-009 is a different empty-snapshot path)

## Task

Fix the Trader pane crash `Cannot read properties of undefined (reading 'toUpperCase')` on a fresh clone with empty Alpaca keys.

## Goal

Clicking Trader opens Stock View (SPY by default) without the red error boundary, and IBKR can still supply the quote when APCA keys are missing.

## Why it mattered

The desk header stayed up (IBKR connected, Net Liq painted) but Trader was unusable. A missing news/listing key should not take down the whole trading view.

## What we changed

- `ticker_detail.ticker_alpaca_required_error` -- IBKR discovery does not block on missing APCA keys.
- REST `build_ticker_detail` and `/ws/ticker` use that gate. Non-ibkr discovery still errors, but the payload now includes `symbol`.
- `tickerDetailFromWsInitial` rejects error-only WS `initial` messages so they never become `detail`.
- `StockViewPage` only calls `.toUpperCase()` when `detail.symbol` is a string.

## How it works now

Scanner prices and ticker snapshots are IBKR-only. Alpaca keys are optional metadata (news / listing). A WS `initial` without a usable `symbol` + `snapshot` is a failed fetch, not a quote object. Trader can paint IBKR last while news stays empty.

## Why this approach

Rejected "just guard `.toUpperCase()` in StockViewPage." That stops the red box but leaves Trader on "No quote data" forever, because the socket still sent a fake initial and the REST path still returned `{error}` with no snapshot.

Rejected "require the user to paste Alpaca keys." Discovery is IBKR. Forcing Alpaca for a quote violates the single-feed rule.

Shared `ticker_alpaca_required_error` so REST and WS cannot drift. Frontend parse is defense in depth for any future error-only payload.

## Verification

- `py -3 -m pytest backend/tests/test_ticker_detail_ibkr_no_alpaca.py backend/tests/test_ticker_ibkr_snapshot.py -q` -- 7 passed
- `npx vitest run src/hooks/tickerStreamHttp.test.ts` -- 4 passed
- `npx tsc -b` and `npm run build` -- exit 0
- After API restart: `GET /api/ticker/SPY` returned `symbol=SPY` and last `769.45`; `/api/ibkr/status` `connected=true` `session_state=ready`; `/api/afterhours` 50 live rows
- Browser: Trader opened SPY with quote $769.45, charts, Level 2/T&S mounting. No error boundary.

## Follow-ups

News/listing stay empty until APCA keys are in `.env` (D-001 family). D-009 (cold snapshot empty while bars work) is a different path and stays open. 10-Second pane may still sit on Loading while hist fills (D-003).

## Keywords

Trader, toUpperCase, API keys not configured, Alpaca, ticker WS, StockViewPage, SPY
