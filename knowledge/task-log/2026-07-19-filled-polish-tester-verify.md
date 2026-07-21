# 2026-07-19 — Tester verify: Filled polish (tooltips) Open/Closed Orders

- **Status:** completed
- **Agents:** tester (daddy dispatch after widgets)
- **Domain:** widgets / Open·Closed Orders
- **Related:** `knowledge/task-log/2026-07-19-filled-active-trade-verify.md` · widgets polish (tooltips only)

## Task

Verify widgets’ Filled discoverability polish (header/cell `title` tooltips) does not regress Open/Closed Orders rendering or column contracts.

## Goal

Scoped Vitest + cheap pytest orders L2 green; Filled cell values and tooltip titles asserted; no commit/push; report for daddy.

## Why it mattered

Tooltip-only changes can still break cell HTML or column meta contracts. Open/Closed Orders are execution-adjacent UI — regressions must be caught before ship.

## What we changed

- No product code. Tester run + task-log + tester-memory run-log entry only.

## How it works now

Filled / Remaining / Average fill columns already existed. Widgets added `title` on column meta + cell HTML (`N of M shares filled`, remaining working). Tests assert both numeric cell text and `title=` strings.

## Why this approach

Scoped orders pyramid slice (L1 Vitest panels/cells/columns + L2 API contract) is enough for title-only polish — no layout claim, so browser optional. Full Vitest/Playwright fleet not re-run (known Stock View WIP cracks unrelated). Did not place/cancel orders.

## Verification

- Vitest (6 files): `workingOrderCells`, `closedOrderCells`, `orderTableColumns`, `WorkingOrdersPanel`, `ClosedOrdersPanel`, `StockViewOpenOrdersDock` → **34 passed**
- Vitest: `orderQtyMath.test.ts` → **8 passed**
- Pytest L2: `test_orders_api_contract`, `test_open_orders_row`, `test_order_times`, `test_closed_orders` → **12 passed**
- Browser: skipped (servers up 5173/8000; no layout change claimed)
- Safety: no order POST/DELETE

## Follow-ups

- None for this polish. Fleet Stock View header cracks remain out of scope.

## Keywords

tester, filled, tooltip, workingOrderCells, closedOrderCells, orderTableColumns, Open Orders, Closed Orders
