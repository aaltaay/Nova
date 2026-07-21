# 2026-07-19 — Closed Orders recent completion highlight

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / closed_orders (WID-027)
- **Related:** `CHANGELOG.md` § Closed Orders: highlight just-completed rows · WID-027

## Task

Highlight Closed Orders that completed within the last minute so extremely recent fills/cancels stand out while actively trading.

## Goal

Rows with completion time in `[now − 60s, now]` show a clear amber pulse; class drops after the window; sample preview can demonstrate it.

## Why it mattered

During paper practice, new closed rows blend into the table; a short “just finished” cue makes it obvious what just hit without scanning timestamps.

## What we changed

- `closedOrderRecency.ts` — pure `isClosedOrderRecent(activityIso, nowMs, windowMs)`
- `ClosedOrdersPanel` — 5s tick + `ibkr-order-row--recent` / `data-recent`
- `closedOrders.css` — amber pulse over buy/sell tint
- Constants: `CLOSED_ORDERS_RECENT_HIGHLIGHT_MS` (60s), tick, tooltip copy
- Sample mock row `9008` frozen at build time for preview
- `SelectableTableRow` — `hintPrefix` + `dataRecent`

## How it works now

Completion clock = `orderActivityIso` (`updated_at` then `submitted_at`). If age ∈ [0, 60s], row pulses amber. Panel re-evaluates every 5s so the highlight clears without a data poll. Sample 9008 is stamped once when mocks are built (toggle sample to refresh).

## Why this approach

- Reused activity ISO already shown in the Time column — no new broker field.
- Pure predicate + tick beats CSS-only (class would stick after 60s) and beats poll-only (up to 5s stale clear is OK; poll alone could leave highlight until next fetch).
- Rejected permanent “NEW” badge — user asked for a one-minute window.
- Rejected relative mock timestamps on every render — Time column must not crawl; freeze-at-build for demo row only.

## Verification

`npx vitest run src/closed_orders/closedOrderRecency.test.ts src/closed_orders/ClosedOrdersPanel.test.tsx src/closed_orders/mockClosedOrders.test.ts` — 12 passed.

## Follow-ups

None required. Commit when user asks.

## Keywords

closed orders, recent highlight, updated_at, WID-027, ibkr-order-row--recent
