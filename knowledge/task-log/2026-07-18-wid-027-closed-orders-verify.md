# 2026-07-18 — WID-027 Closed Orders widget verification

- **Status:** completed
- **Agents:** tester (via daddy)
- **Domain:** widgets / trading UI / IBKR orders
- **Related:** `knowledge/task-log/2026-07-18-closed-orders-wid027.md` · WID-027 · ADR 007 place path

## Task

Verify the Closed Orders widget (WID-027) just shipped by widgets: feature slice, registry, backend closed-orders endpoint, Flatten via `closeFullPosition` → place (not cancel), and ORDERS_GATE / auto_live safety.

## Goal

Pass/fail evidence for focused pytest + Vitest + build; confirm Close/Flatten does not bypass spend gates; note live-server reload if needed.

## Why it mattered

Flatten/close must stay on the ADR 007 place path with ORDERS_GATE; Closed Orders must stay read-only history (no cancel). A green unit suite alone is not enough if Flatten is unlocked while `orders_enabled=false`.

## What we changed

- Tester memory run-log + Current snapshot note for WID-027 scoped verify
- This task-log entry (no product code)

## How it works now

- `GET /api/ibkr/orders/closed` filters terminal session trades (Filled/Cancelled/ApiCancelled/Inactive)
- UI: `frontend/src/closed_orders/` + workspace id `closed_orders`
- Flatten: `closeFullPosition` → `placeIbkrOrder` → `POST /api/ibkr/order` → `execution.service.execute` → `assert_orders_allowed` (`ORDERS_GATE`)
- UI also disables Flatten when `spendStatus` is `locked` / `locked_live_unconfirmed`
- `auto_live` remains rejected in `nova_os.control_mode.set_mode`

## Why this approach

Scoped gates first (closed + open-order row + closed_orders Vitest + registry + closeFullPosition), then build, then browser against already-running servers. Did not restart/kill user servers; live 404 on `/orders/closed` attributed to stale uvicorn OpenAPI (TestClient on current code returns 200). Did not place orders. Count mismatches vs widgets claim (Vitest 17 not 21; pytest closed file has 3 tests, plus 2 open-order row = 5 total) reported honestly rather than inflating.

## Verification

- `py -3 -m pytest backend/tests/test_closed_orders.py backend/tests/test_open_orders_row.py -q` → **5 passed**
- `npx vitest run src/closed_orders src/ibkr/closeFullPosition.test.ts src/workspace/registry.test.ts` → **17 passed** (6 files)
- `npm run build` → **PASS**
- TestClient `GET /api/ibkr/orders/closed` → **200** `[]`
- Live `127.0.0.1:8000` OpenAPI lacks `/orders/closed` → **404** until API reload
- Live `/api/ibkr/status`: `orders_enabled:false`, `spend_status:locked`, `live_trading_confirmed:false`
- Browser Trading: CLOSED ORDERS panel + Modules “Closed Orders”; Flatten SPY disabled under ORDERS LOCKED

## Follow-ups

- Restart/reload local uvicorn so live `/api/ibkr/orders/closed` matches code (stale process, not a unit failure)
- Known fleet cracks unchanged: `sv-trading-lock` / Playwright Stock View header — not re-run; not attributed to WID-027

## Keywords

WID-027, closed orders, closeFullPosition, ORDERS_GATE, Flatten, auto_live NO-GO, tester verify
