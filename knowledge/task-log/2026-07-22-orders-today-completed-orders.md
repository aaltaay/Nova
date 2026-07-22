# 2026-07-22 — Warm completed orders + Orders Today badge/empty honesty

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / IBKR orders UI
- **Related:** `CHANGELOG.md` §2026-07-22 Orders (Today) completed-orders warm · `PROBLEM_LOG.md` §2026-07-22 completed-orders hang · companion to Time Filled column

## Task

Fix ORDERS (TODAY) looking empty despite an open position by warming IBKR completed orders after connect, and make the Orders badge + empty-state copy match symbol-filtered reality.

## Goal

Closed Orders means “completed orders IBKR will give this account session,” not “only fills this API socket witnessed live.” Badge and empty copy stay honest. No live trades placed during verification.

## Why it mattered

Positions warmed via `reqPositionsAsync` every connect; Closed Orders had no equivalent `reqCompletedOrdersAsync` warm-up. A position opened before reconnect (or via TWS) showed under Positions while Orders (Today) stayed empty — product mismatch with the tab title.

## What we changed

- `backend/ibkr/account.py`: `refresh_completed_orders_cache()` — single-flight + `asyncio.wait_for` timeout (`IBKR_COMPLETED_ORDERS_TIMEOUT_SEC`)
- `backend/ibkr/client.py`: call warm-up at both post-connect sites (alongside positions)
- `backend/ibkr/orders.py`: `closed_orders_async` one-shot warm when first read is empty; infer `filled_qty=qty` when status is `Filled` but IBKR left fill counters at 0
- `backend/routes/trading.py`: `GET /orders/closed` → `closed_orders_async`
- Frontend: dock badge = working + real closed via `ordersTodayBadgeCount`; `OrdersTodayView` empty gate uses symbol-filtered closed rows; split empty copy; dock persist helpers extracted for file-size

## How it works now

On IBKR connect, Nova asks Gateway for completed orders (`apiOnly=False`) once under a lock+timeout; ib_async folds them into `ib.trades()`, so `closed_orders()` keeps its existing filter/sort/limit. A late UI poll that still sees empty triggers one more warm. Badge never counts closed *sample* rows. Empty message distinguishes “Gateway has nothing yet” vs “nothing for this symbol/filter.”

## Why this approach

- Stay on the existing IBKR trades path (no second ledger) — `reqCompletedOrdersAsync` already merges into `ib.trades()`.
- Hard timeout is mandatory: Read-Only / wedged Gateway made the warm hang and blocked reconnect + `GET /orders/closed`.
- Infer filled qty only for `status == "Filled"` with zero counters — completed-order callbacks often omit fill fields; do not invent fills for cancels.
- Badge lifted into `ordersTodayBadgeCount` so dock and filters share one count invariant.

## Verification

- pytest: `test_closed_orders.py`, `test_ibkr_account.py` (incl. timeout + single-flight) green
- Vitest: `orders_today/*`, `StockViewOpenOrdersDock.test.tsx` green
- Live: warm log `completed-orders cache refreshed after connect`; `GET /api/ibkr/orders/closed` returns promptly (empty when IBKR has no session completed orders — remaining fractional IBKR position may predate today)
- **No live orders placed**

## Follow-ups

If a same-day fill still missing after R/W API is confirmed, inspect Gateway completed-order retention for that account — not a Nova empty-list disguise.

## Keywords

reqCompletedOrdersAsync, closed_orders_async, Orders Today, badge, empty state, Read-Only, IBKR_COMPLETED_ORDERS_TIMEOUT_SEC
