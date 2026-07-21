# 2026-07-20 — Shared money formatter (formatMoney)

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / trading UI
- **Related:** `CHANGELOG.md` §2026-07-20 Shared money formatter · `knowledge/task-log/2026-07-20-fractional-share-qty-display.md` (formatShareQty precedent)

## Task

User asked whether Nova's trading tables share a single source of truth. Audit found the dollar formatter (`fmt`/`fmtDollar`) copy-pasted identically in 5 files; extract it into one shared utility, mirroring `formatShareQty`.

## Goal

One `formatMoney(n, decimals)` used everywhere a `$` total is rendered in Positions / Orders / trade bar / header, with the 5 duplicate local copies deleted.

## Why it mattered

Duplicated formatting logic is a silent-drift risk: a future fix to rounding or currency display applied to one copy would miss the other four. Same class of issue `formatShareQty` fixed for qty display.

## What we changed

- Added `frontend/src/utils/formatMoney.ts` (+ Vitest) — `$` + `toLocaleString`, configurable decimals (default 2), `'—'` for null/non-finite.
- Removed local `fmt`/`fmtDollar` from `PositionsPanel.tsx`, `workingOrderCells.tsx`, `closedOrderCells.tsx`, `TickerTradeActionBar.tsx`, `StockViewHeader.tsx`; all now import `formatMoney`.
- Left `quoteFormat.ts`'s `fmtPrice` untouched — different scope (per-share quote price, no thousands separator).

## How it works now

`formatMoney(n, decimals = 2)` is the single source for `$`-with-thousands-separator formatting. 2-decimal calls (default) cover price/value columns; `formatMoney(n, 0)` covers account-total badges (Net Liq / Buying Power).

## Why this approach

- **Extract, don't merge tables:** considered unifying the three cell-renderer functions (`renderPositionCell`/`renderWorkingOrderCell`/`renderClosedOrderCell`) or folding Executor/Journal tables into the IBKR order-table system, but their column sets and row types (`IbkrPosition` vs `IbkrOrder` vs `ClosedOrder`, plus a wholly separate Nova OS automation-preview/journal domain) diverge enough that a shared renderer would need a switch over the union of all columns — more indirection, no real duplication removed. Rejected as over-engineering relative to the actual DRY gap.
- **Single `decimals` param over two functions:** avoids a second near-duplicate (`formatMoneyWhole`) for the 0-decimal account-badge case.
- **Left `fmtPrice` alone:** it already serves a distinct, correctly-scoped need (no thousands separator for per-share quote prices); conflating it with `formatMoney` would blur two different formatting intents.

## Verification

`npx vitest run src/utils/formatMoney.test.ts src/utils/formatShareQty.test.ts src/ibkr/workingOrderCells.test.tsx src/closed_orders/closedOrderCells.test.tsx` — 25 passed. `npm run build` (frontend) — clean, no orphaned imports.

## Follow-ups

None required. If a real second use for merging cell renderers or Executor/Journal into the order-table system appears later, revisit then — not before.

## Keywords

formatMoney, fmtDollar duplication, single source of truth, PositionsPanel, workingOrderCells, closedOrderCells, TickerTradeActionBar, StockViewHeader, formatShareQty precedent
