# 2026-07-19 — Orders Time Placed audit-grade timestamps

- **Status:** completed
- **Agents:** parent
- **Domain:** execution / widgets / frontend
- **Related:** `CHANGELOG.md` §2026-07-19 Orders Time Placed (audit-grade)

## Task

Rename the Orders **Time** column to **Time Placed**, and make place timestamps audit-safe (broker-authoritative, no fill-time drift).

## Goal

Operators and auditors see a stable place time that does not crawl on fills; machine-readable UTC ISO stays on `<time dateTime>`; Nova logs a structured place audit line.

## Why it mattered

Filled/Cancelled rows previously showed last activity under a generic “Time” header — wrong for “when did I place this?” and unsafe for audit reviews.

## What we changed

- Column label/tooltips → **Time Placed** (Working + Closed)
- Closed table Time cell uses `submitted_at` (same as Working)
- `formatOrderDateTime` shows ms when ISO has a fractional second
- Backend: `remember_nova_placed` / `resolve_submitted_at` / `IBKR_ORDER_AUDIT` on place
- Sort by Time Placed = `submitted_at` for both modes
- Recency highlight still uses fill/cancel activity

## How it works now

1. On `placeOrder`, Nova records wall-clock UTC (µs) keyed by `order_id`.
2. Row `submitted_at` = IBKR `trade.log[0].time` if present, else Nova stamp.
3. UI formats Eastern for humans; `dateTime` keeps the UTC ISO unchanged.
4. Hover can still show last activity when it differs from place time.

## Why this approach

Broker log is the exchange-side truth for place/ack. Nova wall clock covers the race where IB has not yet populated `trade.log`. Rejected: using `Date.now()` in the browser (clock skew), or showing fill time as “Time Placed.” Rejected renaming columns to two fields in this pass — hover covers last activity without cluttering the dock.

## Verification

- `pytest tests/test_order_times.py tests/test_open_orders_row.py` — 12 passed
- Vitest order display/cells/sort/panels — 36 passed

## Follow-ups

In-memory Nova place stamps die on API restart; persist to execution store/DB if multi-day offline audit of pre-broker-log gaps is required.

## Keywords

Time Placed, submitted_at, audit, order_times, IBKR_ORDER_AUDIT, fractional seconds
