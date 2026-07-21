# 2026-07-19 — Stock View Positions dock (WID-019)

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / ibkr trading UI
- **Related:** `CHANGELOG.md` §2026-07-19 Stock View Positions · WID-019

## Task

Add a Stock View table for current IBKR positions (holdings), alongside the existing Orders (Today) dock.

## Goal

Operator can open Stock View and see open positions (qty, avg cost, mkt, P&L, Flatten when armed) without leaving for the Trading tab.

## Why it mattered

Orders (Today) covered working/filled history; positions were only on Trading tab. Day-trading Stock View needs holdings in the same bottom strip.

## What we changed

- Dock tabs: **Positions** | **Orders (Today)**; surface persists in `nova.stockView.dock.surface`.
- Reused `PositionsPanel` with `compact` / `hideTitle` (no nested Working Orders / account strip in dock).
- `StockViewPage` wires account `positions` / `summary` / Flatten refresh into the dock.
- Dock mounts even when ticker WS detail is not ready (charts/rail still gated).
- Vitest + Playwright coverage for Positions surface.

## How it works now

Same IBKR account poll as Trading tab (`useIbkrAccount`). Bottom dock switches surfaces; Positions shows all open positions (not symbol-filtered). Flatten uses existing Close path (ADR 007 / paper gates). `auto_live` remains NO-GO.

## Why this approach

- **Reuse PositionsPanel** instead of a second table — one column-order store, Flatten, side tinting.
- **Dock surface, not a third full-page tab** — matches Webull-style Orders strip and keeps chart focus.
- **Decouple dock from ticker detail** — positions are account data; waiting on `/ws/ticker` hid the whole strip and flaked e2e when backend was slow/absent.
- Rejected: duplicating Trading-tab account strip in the dock (noise); filtering positions to open symbol only (operator needs full book).

## Verification

- `npx vitest run src/stock_view/StockViewOpenOrdersDock.test.tsx src/stock_view/stockViewTerminal.test.tsx`
- `npm run test:e2e:orders` (Open + Closed + Positions) — 3 passed

## Follow-ups

None required. Optional: symbol-highlight filter chip later if operators want “this ticker only.”

## Keywords

positions, WID-019, Stock View, dock, PositionsPanel, compact, IBKR account
