# 2026-07-18 — Working Orders panel (Webull WID-026)

- **Status:** completed
- **Agents:** widgets (daddy-orchestrated)
- **Domain:** widgets / trading UI
- **Related:** `CHANGELOG.md` §2026-07-18 Working Orders · WID-026 · WID-020

## Task

Research Webull's post-order / working-orders UI and map a Nova equivalent;
ship a thin panel if clearly scoped without unlocking `auto_live`.

## Goal

Operators see order status (columns + lifecycle) after placing an IBKR order,
aligned with Webull Orders → Working, without Webull data or live-gate changes.

## Why it mattered

After place, Nova only showed a ticket text line and a thin Open Orders table
buried in PositionsPanel — easy to miss from Stock View. Webull keeps a dedicated
Orders widget with Working / history paths.

## What we changed

- Documented S17 + Working Orders column map in `docs/webull-widget-parity.md`
  (WID-026; WID-020 narrowed to history/export).
- Extended `backend/ibkr/orders.open_orders` with filled/remaining/avg fill.
- Added `frontend/src/ibkr/WorkingOrdersPanel.tsx`; wired Trading highlight +
  Stock View rail card under Trade.
- Vitest + pytest without live order placement.

## How it works now

- **Primary:** Trading tab account column always shows Working Orders when
  connected; just-placed `order_id` is highlighted after refresh.
- **Secondary:** Stock View rail shows a compact Working Orders card for the
  open symbol when working rows exist (or a highlight id is set).
- Data: `GET /api/ibkr/orders` from IBKR `openTrades` only. Cancel remains
  enabled; modify/history/export deferred. `auto_live` untouched.

## Why this approach

- **Chose** enrich open-orders API + dedicated panel over a new history service:
  IBKR already exposes fill progress on open trades; history needs a separate
  contract (WID-020) and must not block the post-place UX gap.
- **Rejected** a global Orders drawer for v1 — Trading is already the Account
  analogue; Stock View only needs symbol-scoped status after place.
- **Rejected** Webull scrape / screenshots with credentials — public FAQ S15/S17
  + inferred columns from IBKR fields meet the evidence contract.
- **Rejected** order modify — Webull has it; Nova safety prefers cancel-only
  until history exists (map already says history before edit).

## Verification

- `py -3 -m pytest backend/tests/test_open_orders_row.py -q`
- `npm run test -- --run src/ibkr/WorkingOrdersPanel.test.tsx src/stock_view/stockViewTerminal.test.tsx`
  (from `frontend/`)

## Follow-ups

- WID-020: Today's / filled / cancelled history + CSV export.
- Optional place-confirmation toast (Webull toggle exists; Nova has ticket confirm).
- Order time column if IBKR exposes a stable timestamp on the trade row.

## Keywords

working orders, WID-026, Webull Orders, post-place, open_orders, filled_qty, Stock View rail
