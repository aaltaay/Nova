# 2026-07-22 — Closed Orders Time Filled column

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / trading UI
- **Related:** `CHANGELOG.md` 2026-07-22 entry · plan `closed_orders_time_filled_ed4bddb5.plan.md`

## Task

Add a dedicated "Time Filled" column to Closed Orders, sourced from IBKR's real
fill clock (`Trade.fills[].execution.time`), without touching the existing
audit-grade "Time Placed" (`submitted_at`) column or Working Orders.

## Goal

- Backend `extract_trade_times` exposes a third `filled_at` value (real fill
  clock only, `None` when never filled).
- Closed Orders table shows Time Filled as the new first column; Time Placed
  stays second and unchanged.
- Working Orders columns untouched (non-goal).
- pytest + Vitest green; browser-verified rendering.

## Why it mattered

Users could see when an order was *placed* but not when it actually *filled*.
Time Placed intentionally never crawls on fills (2026-07-19 decision), so the
real fill moment — which IBKR already reports per-fill — was invisible in the
UI. This was flagged while investigating an unrelated user question about a
live Flatten order and a fractional-share Ford order, which surfaced that the
UI had no way to show "when did this actually fill."

## What we changed

- `backend/ibkr/order_times.py`: `extract_trade_times` now returns
  `(submitted_at, updated_at, filled_at)` instead of a 2-tuple. `filled_at` is
  `_to_iso(max(fill_times))` when fills exist, else `None` — it never falls
  back to log/cancel time (that stays `updated_at`'s job).
- `backend/ibkr/orders.py`: `_trade_to_order_row` adds `"filled_at"` to the
  public JSON row; fixed the other 2-tuple unpack call site.
- `backend/tests/test_order_times.py`: updated the existing fill-times test
  for the 3-tuple, added a new "no fills → filled_at is None" test.
- Frontend: `IbkrOrder.filled_at` type; `ClosedOrderColumnId` gains
  `'filled_at'` (Working Orders type untouched); `CLOSED_COLUMN_META.filled_at`
  (label "Time Filled"); `DEFAULT_CLOSED_ORDER_COLUMNS` puts `filled_at` first;
  `ORDER_TABLE_COLUMNS_STORAGE_KEY` bumped `v4`→`v5` so existing saved layouts
  pick up the new column instead of silently missing it; `orderFilledIso` /
  `orderFilledTimeTitle` helpers in `orderDisplay.ts`; render case in
  `closedOrderCells.tsx`; sort case + desc-first default in `orderTableSort.ts`
  + `ORDER_TABLE_DATA_SORT_KEYS`; `mockClosedOrders.ts` fixtures updated with
  realistic `filled_at` (set for filled/partial rows, `null` for zero-fill
  cancels/failures).
- Updated/added tests: `orderTableColumns.test.ts`, `orderTableSort.test.ts`,
  `closedOrderCells.test.tsx`.

## How it works now

`filled_at` is a pure derivation of the fill list only — if `trade.fills` is
empty, `filled_at` is `None` regardless of what the order log says. This keeps
"Time Filled" honest: a straight cancel or rejection shows `—`, a
partial-fill-then-cancel still shows the real fill timestamp (not blank),
matching how "Filled" qty already works for those rows. The column lives only
on `ClosedOrderColumnId` — Working Orders never had a "did this fill" concept
in the same sense (an open order can still be working) so it was intentionally
not added there. `DEFAULT_CLOSED_ORDER_COLUMNS` orders `filled_at` before
`time` so the more actionable (and more often-empty-for-cancels) fill time is
the first thing a user's eye hits, while Time Placed remains the fixed,
non-crawling audit anchor immediately after it.

## Why this approach

- **New column, not a repurposed field** — the alternative (turning "Time
  Placed" itself into "whichever is more recent") was explicitly rejected
  earlier (2026-07-19 CHANGELOG) because it made the audit trail crawl on
  every fill tick. Keeping both columns lets each answer one question
  precisely instead of one column trying to answer two.
- **`filled_at` derived only from fills, never from log/cancel time** — the
  temptation was to reuse `updated_at` (which already falls back to last log
  time) directly as "Time Filled," but that would silently show a cancel
  timestamp as if it were a fill, which is a factually wrong claim for a
  zero-fill cancelled order. Keeping `filled_at` fill-only means `—` is an
  honest signal, not a formatting gap.
- **Storage-key bump over silent reorder** — column order is drag-persisted
  in localStorage; without bumping the version, `normalizeColumnOrder` would
  append the new column at the *end* of every existing user's saved layout
  (since it wasn't in their saved list), burying "Time Filled" instead of
  showing it first as designed. Bumping `v4`→`v5` (the same pattern used for
  prior column-order changes) resets to the new default for everyone once,
  which is a one-time, low-cost disruption versus a permanently-buried column.

## Verification

- `py -3 -m pytest backend/tests/test_order_times.py backend/tests/test_open_orders_row.py backend/tests/test_orders_api_contract.py` — 21 passed.
- Full backend suite: 850/851 passed; the one failure
  (`test_hod_momo_universe.py::test_build_focus_universe_empty_inputs`) was
  confirmed pre-existing and unrelated by stashing this diff and re-running —
  identical failure on `master`.
- `npx vitest run` (frontend): 415/415 passed, including new coverage for the
  Time Filled column, sort key, and default column order.
- Browser check: opened the running dev app, searched AAPL, opened Trader,
  enabled the Closed Orders sample preview. Time Filled rendered as the first
  column with correct ET times for Filled/partial-cancel rows and `—` for
  zero-fill Cancelled/Inactive rows; Time Placed unchanged.

## Follow-ups

Companion fix for "ORDERS (TODAY) empty despite an open position" (warm
`reqCompletedOrdersAsync` after connect, honest working+closed badge count,
symbol-aware empty-state copy) is the second half of the same plan and is
tracked/shipped separately.

## Keywords

closed orders, time filled, time placed, submitted_at, updated_at, filled_at,
extract_trade_times, IBKR fill clock, order table columns, column storage key
version bump
