# 2026-07-19 — Nova OS judgment moved to Stock View dock tab

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / Trader (Stock View) layout
- **Related:** `CHANGELOG.md` §2026-07-19 — Nova OS judgment moved to Stock View dock tab · prior task-log `2026-07-19-trader-nova-os-brain.md`

## Task

Move the Nova OS judgment panel (WAIT/BUY gates, news, ticket) from under the Trader header into the bottom dock tab bar.

## Goal

Charts get the full main column height; judgment is one click away in a dock tab beside Positions / Orders (Today).

## Why it mattered

The always-on header band stole a large vertical slice (gates + news + ticket) and fought the chart grid. User annotated the panel → dock tabs.

## What we changed

- Extended `StockViewDockSurface` with `nova_os` + `STOCK_VIEW_MODULE_NOVA_OS_TITLE`.
- Mounted `TraderNovaOsBrain` inside `StockViewOpenOrdersDock` when that surface is selected; removed it from `StockViewPage` under the header.
- Dock CSS: brain fills the dock body (no 42vh header band).
- Vitest: Nova OS tab switch coverage.

## How it works now

Bottom dock tabs: Positions | Orders (Today) | Nova OS. Surface persists in `nova.stockView.dock.surface`. Decide polling (`NOVA_OS_TRADER_DECIDE_POLL_MS`) runs only while the Nova OS tab is mounted. Still signal-only.

## Why this approach

- **Dock tab vs collapsing header strip:** Tab matches existing Positions/Orders pattern and frees charts by default; a collapsed strip would still reserve chrome and be easy to miss.
- **Mount-on-select vs always-mount-hidden:** Avoids background decide polls when the trader is looking at orders/positions.
- **Rejected:** Separate floating panel — another chrome surface and resize story for no gain over the dock.

## Verification

`npx vitest run src/stock_view/StockViewOpenOrdersDock.test.tsx src/stock_view/TraderNovaOsBrain.test.tsx` — 7 passed. Dock file ≤400 lines.

## Follow-ups

Optional: show live WAIT/BUY chip on the Nova OS tab without opening it (would lift `useNovaOsDecideSymbol` to the dock).

**2026-07-19 (same day):** Dock type bumped in `traderNovaOsBrain.css` (~0.88–0.95rem content) after user reported micro-fonts were unreadable.

## Keywords

nova-os, dock, StockViewOpenOrdersDock, TraderNovaOsBrain, tab, layout, charts
