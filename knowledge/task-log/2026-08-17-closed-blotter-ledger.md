# 2026-08-17 -- Orders Today reads the execution ledger

- **Status:** completed
- **Agents:** parent
- **Domain:** execution (continuity-only; no specialist hop)
- **Related:** `CHANGELOG.md` §2026-08-17 -- Orders (Today) overlays the execution ledger · `PROBLEM_LOG.md` §2026-08-17 -- Orders (Today) showed ledger fills as 0 / 0 / 0 · persist-audit canvas · ADR 007

## Task

Point Orders (Today) at the execution ledger for Nova-placed fills so the table shows a real id and qty instead of IB completed-order replay zeros.

## Goal

`GET /api/ibkr/orders/closed` returns healed Nova rows (client `order_id` or `permId`, payload/fill qty). IB-only fills stay on the list, labeled `ib_recovered`. No new database. No journal P/L.

## Why it mattered

The operator did not care about rewriting this morning's IVF history in place. They needed tomorrow's (and any later) Nova fills to show a real id on the desk. The ids were already on disk after the recording pass; the blotter was the remaining lie.

## What we changed

- `execution/closed_blotter.py` -- `overlay_closed_orders` matches ledger place/bracket rows onto IB closed rows.
- `execution/store_facts.py` -- `list_session_placed` (this session, no benchmarks).
- `routes/trading.py` -- closed route overlays after the IB read; still 503 if IB is down.
- `ibkr/order_rows.py` -- include `perm_id` from `order.permId`.
- Closed-orders UI -- `formatClosedOrderId` shows session id, else permId, else `--`.

## How it works now

IB remains the live session list. After that read, Nova overlays its own ledger for the current 04:00 ET session. Match order: `permId`, then client `order_id`, then symbol+side when IB's id is 0. Leftover ledger fills (IB dropped them) are appended. TWS-only trades do not get a fake Nova id.

## Why this approach

- **Overlay on the existing closed endpoint**, not a second poll. The UI already hits `/api/ibkr/orders/closed` every 5s.
- **Keep IB required.** A disconnect still 503s. Last-good UI cache stays. We did not pretend the ledger is a second live book for open orders.
- **Do not start from ledger-only.** That would hide TWS / other-clientId fills. Label those `ib_recovered` instead.
- **Rejected:** hosted Postgres; inventing journal P/L from a single fill; a new Activity page in this pass.

## Verification

```text
py -3 -m pytest backend/tests/test_closed_blotter.py backend/tests/test_orders_api_contract.py backend/tests/test_closed_orders.py backend/tests/test_open_orders_row.py backend/tests/test_execution_store_facts.py -q
npx vitest run src/closed_orders/formatClosedOrderId.test.ts src/closed_orders/closedOrderCells.test.tsx
```

33 pytest passed. 10 Vitest passed.

## Follow-ups

- Journal-on-close (not a single fill).
- Activity / trail UI (gates, requested vs sent).
- Optional last-good closed list when IB is down.

## Keywords

Orders Today, closed_orders, overlay_closed_orders, Order ID 0, permId, execution_ledger
