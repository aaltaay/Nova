# 2026-07-19 — Orders (Today) Webull-style segmented dock

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / orders_today (WID-026 / WID-027)
- **Related:** `CHANGELOG.md` § Orders (Today) Webull-style segmented dock · WID-026 / WID-027

## Task

Implement the Webull-style **Orders (Today)** view with segmented filters: Working | Filled | Canceled | Partial Filled | All.

## Goal

Stock View footer uses one session title and the contiguous filter bar from the user’s screenshot, instead of separate Open / Closed tabs.

## Why it mattered

While actively trading, switching Open vs Closed tabs hid half the session story. One “Orders (Today)” strip matches Webull muscle memory.

## What we changed

- New `frontend/src/orders_today/` slice (`OrdersTodayFilters`, `OrdersTodayView`, filter helpers)
- `StockViewOpenOrdersDock` retitled to Orders (Today); persists `nova.stockView.ordersToday.filter`
- `ClosedOrdersPanel` supports `hideFilters` + controlled `statusFilter`
- Cancelled closed filter no longer includes partial cancels (Partial Filled owns them)
- E2E + dock tests updated; parity doc + CHANGELOG

## How it works now

Segment picks which tables render: Working/All/Partial → working panel (symbol-filtered); Filled/Canceled/Partial/All → closed panel with mapped status filter. Sample previews still available when Gateway has no rows.

## Why this approach

- Reused WorkingOrdersPanel + ClosedOrdersPanel (actions stay on working only) instead of a risky one-table rewrite.
- Contiguous segmented CSS matches the reference; title is Orders (Today) like Webull.
- Rejected keeping Open/Closed tabs with filters nested inside — user asked for this exact chrome.
- Deferred single merged All table (follow-up) to ship the UX bar cleanly first.

## Verification

Vitest `orders_today` + dock + closed filter tests; `npm run test:e2e:orders` (2 passed).

## Follow-ups

Optional unified All table; WID-020 CSV. Commit when user asks.

## Keywords

orders today, webull, segmented filter, WID-026, WID-027, stock view dock
