# 2026-08-17 -- Scanner Trader keeps tape subscribed

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-08-17 -- Scanner | Trader keeps tape subscribed · `PROBLEM_LOG.md` 2026-08-17 -- T&S resubscribe on Scanner | Trader

## Task

Explain and stop Time & Sales "Resubscribing in 10s" every time the operator switches Scanner and Trader, even with Gateway/API up and an open IB session.

## Goal

Scanner | Trader is a view switch. Open tick-by-tick and Level 2 stay subscribed. The 15s IB same-instrument guard is not tripped by that nav.

## Why it mattered

The red T&S error looked like a dead feed. It was self-inflicted: we cancelled a live `reqTickByTickData` just to show the scanner, then IB refused the immediate resubscribe. Open net does not waive that broker rule.

## What we changed

- Host window: `traderViewActive` + hidden `nova-trader-desk-slot` so `StockViewTabs` stays mounted across Scanner.
- Scanner / Account / Working leave the desk via `showScannerView`, not `closeTraderView`.
- `closeTraderView` remains last-tab X, detached close, and empty-desk cleanup.
- Hidden trader pauses chart polls (`chartActive`) but keeps tape/L2 hooks.
- `tape_stream.unsubscribe` lingers 16s before `cancelTickByTickData`; remount reuses `_tickers`.
- Feed rule: do not unmount Trader to show Scanner.

## How it works now

Tabs in session storage mean "desk exists." `traderViewActive` means "desk is on screen." IB tick-by-tick is refcounted plus linger. Last viewer close does not immediately cancel. A subscribe during linger is a no-op reuse. After linger, cancel is recorded and the 15s guard applies for a true new subscribe.

## Why this approach

Keeping the React tree mounted is the only way to keep the frontend WebSockets open without a new session protocol. Linger is the backstop for StrictMode remounts and last-tab reopen, not the primary Scanner path. Rejected: raising the guard (IB still rejects). Rejected: a second tick-by-tick request (same 15s rule). Rejected: expanding linger to depth in this pass (L2 was still painting). Did not restart the live API; linger lands on the next API process start. Frontend view-switch works after a hard refresh on the current Vite session.

## Verification

- `py -3 -m pytest tests/test_ibkr_tape_stream.py -q` -- 8 passed
- `npx vitest run src/components/GlobalAppBar.test.tsx src/workspace/traderOpen.test.tsx src/workspace/workspaceWiring.test.ts src/components/GlobalWorkingMenu.test.tsx` -- 25 passed
- `npm run build` -- tsc + vite exit 0

## Follow-ups

- Linger needs an API process start to load; do not kill a live desk to pick it up mid-session.
- Last-tab X still tears down; linger covers a fast reopen after that.
- Depth has no 15s twin; leave it unless a similar cancel race shows up.

## Keywords

Resubscribing, Time & Sales, reqTickByTickData, traderViewActive, tape linger, Scanner, Trader
