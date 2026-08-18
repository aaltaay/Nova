# 2026-08-17 -- Desk recovers quote, charts, and F5 without a hard refresh

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / hotkeys
- **Related:** `CHANGELOG.md` §Desk self-heals quote, charts, and F5 · `PROBLEM_LOG.md` §False Disconnected + hung quote after refresh

## Task

Finish the F5 desk rewrite and recover the stuck Trader on F without asking the operator to hard-refresh or diagnose chips.

## Goal

The running UI applies F5 by itself, does not flash a fake disconnect, seeds the quote if the ticker socket is slow, and keeps retrying timed-out charts.

## Why it mattered

Telling the operator to Ctrl+Shift+R produced a worse screen: yellow Disconnected, "Loading quote for F...", and four red chart timeouts. Gateway was actually up (paper delayed feed). They asked the desk to know its own state.

## What we changed

- sessionStorage last-good `/api/ibkr/status` so a remount does not start as disconnected.
- Account provider only marks last-good stale after a real connected session, not on first paint.
- Stock View hides Disconnected until status is known.
- Ticker WS seeds from GET `/api/ticker/{symbol}` after 2.5s if `initial` never arrives.
- Chart panes retry an empty store up to 8 times (including after a background miss).
- Hotkey dispatcher/profile apply the F1/F2/F5 epoch when the constant changes (HMR / already-open tab).

## How it works now

API up + Gateway delayed means paper IBKR is connected on a delayed/non-entitled feed (Error 10167), not a dead Gateway. Quote can come from REST while the socket is still waiting on a cold snapshot. Charts stay red only while IBKR historical is actually busy; they keep asking. F5 is written into `localStorage` when the desk epoch does not match.

## Why this approach

Did not restart Gateway or the API -- `/api/ibkr/status` was `connected=true` and `GET /api/ticker/F/bars?timeframe=1Min` already returned bars. A hard refresh was the wrong lever: it wiped in-memory status to DEFAULT `connected=false` and stampeded four historicals against an inflight `snapshot_quotes`. Last-good status + HTTP seed + retries fix the operator loop without weakening IBKR gates.

Rejected: auto-reload backend from the header (kills sockets for no reason). Rejected: treating delayed market data as disconnected.

## Verification

- `npx vitest run` on status cache, account bootstrap, ticker HTTP seed, chart retry, hotkey epoch, Stock View header -- 20 passed; plus 27 related header/workspace tests.
- `npm run build` exit 0.
- Live: `GET /api/ibkr/status` connected paper; `GET /api/ticker/F` 200; `GET /api/ticker/F/bars?timeframe=1Min` 200.

## Follow-ups

`ib_cold_inflight=snapshot_quotes` is often busy after hours (hydrate / reprice). Do not treat that as Gateway down. Optional later: ticker WS should send a cache/L1 initial before `reqTickersAsync`.

## Keywords

Disconnected, Loading quote, Chart bars timed out, GATEWAY delayed, F5, desk-ask-bid-epoch, snapshot_quotes
