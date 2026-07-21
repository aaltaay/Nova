# 2026-07-19 — Rename Stock View window to Trader

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / frontend
- **Related:** `CHANGELOG.md` §2026-07-19 Rename Stock View window to Trader

## Task

Rename the user-facing “Stock View” window/label to “Trader.”

## Goal

Operators see **Trader** on the open button, window title, document title, header brand, and double-click tooltips — without renaming internal modules or the `?view=stock` URL contract.

## Why it mattered

Product naming: the detached terminal is a trading desk, not a read-only stock page.

## What we changed

- `STOCK_VIEW_TITLE` / `STOCK_VIEW_OPEN_LABEL` / `STOCK_VIEW_OPEN_TITLE` → Trader
- Header brand restored: Nova / Trader
- Electron child title `Nova — Trader`
- Table/row tooltips + Quote Panel button/title
- Playwright baseline + workspace-context string expectations

## How it works now

Internal code stays `stock_view` / `StockView*` / `openStockView` / `?view=stock`. All operator-facing copy comes from the constants (or tooltips that mirror them) and says Trader.

## Why this approach

Renamed the display constants only — no folder/API rename — so URL bookmarks, localStorage keys, and IPC (`nova:openStockView`) stay stable. Rejected a full `TraderPage` rename as high churn for a label change.

## Verification

`npm run test -- --run src/stock_view src/components/SelectableTableRow src/utils/stockViewNav.test.ts` — 25 passed.

## Follow-ups

Commit/push when requested (user commit rule). Docs/Obsidian that still say “Stock View” can be updated opportunistically.

## Keywords

Trader, Stock View, STOCK_VIEW_TITLE, rename, window title, widgets
