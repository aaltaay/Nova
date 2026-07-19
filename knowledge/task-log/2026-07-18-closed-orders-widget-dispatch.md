# 2026-07-18 — Daddy dispatch: Closed Orders WID-027 + Close SSOT

- **Status:** completed
- **Agents:** daddy | widgets | execution | tester
- **Domain:** widgets | execution
- **Related:** WID-027 · WID-020 · WID-026 · WID-019 · ADR 005 · ADR 007 · specialist logs `2026-07-18-closed-orders-wid027.md`, `2026-07-18-close-vs-cancel-ssot-audit.md`, `2026-07-18-wid-027-closed-orders-verify.md`

## Task

User asked daddy to invoke the Webull widgets agent and add a Closed Orders widget (Webull-style) with full close-position affordances, implemented in isolation for future hide / move / drag-drop.

## Goal

Ship an isolated Closed Orders surface with correct Cancel vs Close SSOT wiring; verify gates; leave exact NEXT for export / dock polish.

## Why it mattered

Operators need filled/cancelled history next to Working Orders, plus Flatten that cannot invent a second broker path or unlock `auto_live`. Isolation matters because workspace modules will move/hide independently.

## What we changed

- **widgets:** New **WID-027** (`partial`) — `frontend/src/closed_orders/` feature slice + registry `closed_orders`; `GET /api/ibkr/orders/closed`; Positions Flatten via `closeFullPosition` → `placeIbkrOrder`. WID-020 narrowed to CSV/multi-day export; map/memory/canvas/CHANGELOG updated.
- **execution (audit):** Documented Cancel ≠ Close ≠ Nova OS flatten; Close = place + ORDERS_GATE (`exit_pos` / `placeIbkrOrder`); Closed/history read-only for mutations.
- **tester:** Focused pytest/Vitest/build PASS with notes (reload uvicorn for live closed-orders route).

## How it works now

- **Closed Orders (WID-027):** Session filled/cancelled display; Modules hide/show; not a Cancel/Close mutation surface.
- **Working Orders (WID-026):** Cancel via DELETE / `CANCEL_GATE`.
- **Positions Flatten (WID-019):** Full market exit via place / `ORDERS_GATE` (same path as hotkeys exit) — not typed Nova OS `FLATTEN`.
- **auto_live:** Still NO-GO.

## Why this approach

- **Parallel widgets + execution, then tester:** UI needed map+slice; Close wiring needed SSOT audit without asking execution to ship product code.
- **Rejected:** Baking Closed Orders into StockViewPage/TradingTab forever; putting Close on history rows; calling Nova OS `flatten_positions` for per-symbol Positions Close; inventing a broker path that bypasses ADR 007.
- **Isolation:** ADR 005 feature slice + workspace registry so hide/move/drag-drop can land later without a monolith extract.

## Verification

- pytest closed + open-order row: 5 passed
- vitest closed_orders + closeFullPosition + registry: 17 passed
- `npm run build`: PASS
- Browser: CLOSED ORDERS panel + Modules toggle; Flatten disabled under ORDERS LOCKED
- Live API 404 until uvicorn reload (TestClient 200)

## Follow-ups

1. Reload local API so live `/api/ibkr/orders/closed` matches code.
2. WID-020 CSV / multi-day History export.
3. Optional Stock View closed-orders dock.
4. Optional docs: close/exit + cancel sequence UML (execution backlog).
5. Bracket-safe Close (cancel legs then exit) = separate product ask — not a gate bypass.

## Keywords

daddy, widgets, WID-027, closed orders, flatten, closeFullPosition, ADR 007, ORDERS_GATE, CANCEL_GATE, isolation, workspace registry
