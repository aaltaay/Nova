# 2026-07-19 — Filled / active-fill progress verify (WID-026)

- **Status:** completed
- **Agents:** widgets (daddy dispatch)
- **Domain:** widgets / IBKR order tables
- **Related:** `CHANGELOG.md` §2026-07-19 Filled column tooltips · WID-026 / WID-027 · not WID-015

## Task

User asked (via daddy) about the field for actively trading working orders — “like filled?” — and whether Nova has it; create it if missing.

## Goal

Confirm Filled / Remaining / Average fill + Partially filled + Fill now are complete on Open/Closed surfaces; only polish if already present; do not build TurboTrader (WID-015).

## Why it mattered

After Open/Closed status-matrix sample work, operators need a clear place to see fill progress and act on remaining size while paper-trading — without inventing a second “active trade” product surface.

## What we changed

- Verified end-to-end: API `filled_qty` / `remaining_qty` / `avg_fill_price`, column defaults, Stock View dock `compact={false}`, Fill now wiring, mocks/tests.
- Polish only: header tooltips on Filled / Remaining / Average fill; cell titles `X of Y shares filled` / remaining still working.
- Parity doc note: active fill progress ≠ WID-015 TurboTrader.

## How it works now

**Filled** is the shares-filled-so-far column on Working (Open) and Closed Orders. **Remaining** + **Fill now** are how you act on the unfilled rest (cancel rest → market remainder). Status **Partially filled** when `0 < filled < qty`. Sample preview hides Fill now/Cancel. WID-015 remains a separate missing one-click grid.

## Why this approach

Daddy pre-inspect already pointed at existing columns; inventing another “Active” column would be theater. Tooltips improve discoverability without changing broker math or execution gates. TurboTrader was rejected because the user said “like filled,” not a rapid-entry grid.

## Verification

- Vitest: `orderTableColumns`, `workingOrderCells`, `closedOrderCells`, `WorkingOrdersPanel`, `orderQtyMath`, `fillWorkingOrderImmediately`, `mockWorkingOrders`
- Pytest: `test_open_orders_row`, `test_orders_api_contract`
- No commit/push (user git rule / daddy prefer-ask)

## Follow-ups

- WID-015 TurboTrader only if user explicitly wants a one-click grid (paper-first).
- WID-020 CSV / multi-day History export still open.
- Full tester browser gate optional if parent wants UI screenshot proof.

## Keywords

filled, remaining, avg_fill, Fill now, WID-026, Working Orders, Open Orders, partial fill, widgets
