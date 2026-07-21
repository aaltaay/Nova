# 2026-07-20 — Fractional share qty display in trading tables

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / trading UI
- **Related:** `CHANGELOG.md` §2026-07-20 fractional qty · `PROBLEM_LOG.md` §2026-07-20 Positions Qty 0 · Webull S6

## Task

Show fractional share quantities in Nova trading tables the way Webull does, so leftover IBKR lots (e.g. 0.0642) do not render as Qty **0**.

## Goal

One shared formatter for share qty across Positions, Working/Closed Orders, executor/journal tables, and related Pos/flatten copy — whole shares stay compact; fractions keep up to trade-sizing decimals.

## Why it mattered

Live account showed POSITIONS (1) with IBKR Qty **0** while API had `qty: 0.0642` / ~$5.88 market value. Looked like a ghost row and hid a real (tiny) position.

## What we changed

- Added `frontend/src/utils/formatShareQty.ts` (+ Vitest)
- Wired into Positions, Working Orders, Closed Orders cells; Executor/Journal tables; trade bar Pos / flatten confirms
- Documented in `docs/webull-widget-parity.md` (S6)

## How it works now

`formatShareQty` uses `toLocaleString` with `minimumFractionDigits: 0` and `maximumFractionDigits: TICKER_TRADE_QTY_DECIMALS` (4). Same precision as dollar/% sizing in the order ticket. Never force 0 decimals on share columns.

## Why this approach

- **Shared util** over per-table `fmt(n, 4)` — one place for Webull-style trim (100 → "100", 0.0642 → "0.0642").
- **Reuse `TICKER_TRADE_QTY_DECIMALS`** instead of a new constant — display and sizing stay aligned; Webull’s >0.00001 floor is stricter but 4dp covers IBKR fractionals we see.
- **Rejected** always showing 4 fixed decimals (noisy for whole-share day trades) and hiding zero-looking rows (would hide real fractionals).

## Verification

`npx vitest run src/utils/formatShareQty.test.ts src/ibkr/workingOrderCells.test.tsx src/closed_orders/closedOrderCells.test.tsx` — 21 passed.

## Follow-ups

Refresh UI to confirm live IBKR row shows `0.0642`. Optional: raise display decimals to 5 if IBKR ever returns finer lots.

## Keywords

fractional shares, formatShareQty, Positions Qty 0, Webull S6, TICKER_TRADE_QTY_DECIMALS, IBKR leftover
