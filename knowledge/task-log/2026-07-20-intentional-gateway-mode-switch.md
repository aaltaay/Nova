# 2026-07-20 — Intentional Paper-Live Gateway switch

- **Status:** completed
- **Agents:** parent
- **Domain:** execution / ibkr-ops (IBKR Gateway connection safety)
- **Related:** `CHANGELOG.md` § "Intentional Paper ↔ Live Gateway switch" · `PROBLEM_LOG.md` § "Clicking 'Live' in Stock View did nothing" · `.cursor/plans/live_gateway_switch_731cc270.plan.md`

## Task

User reported clicking "Live" in the Stock View Paper/Live capsule "doesn't work." Implement the attached plan: turn that capsule into a real switch of Nova's target IBKR Gateway port, without ever unlocking live spend.

## Goal

Clicking Live/Paper persists `IBKR_GATEWAY_MODE`, reconnects to the corresponding Gateway port (4001 live / 4002 paper), and either succeeds honestly or fails with an actionable inline error — never a silent no-op and never a silent revert to Paper.

## Why it mattered

The capsule's `window.confirm` copy explicitly said "this control does not switch Gateway ports," so the reported behavior was working exactly as coded — but that is not what an operator expects from a labeled Paper/Live switch, and the existing self-heal (`gateway_heal.py`) would have silently flipped a failed live attempt back to Paper with no explanation, making a real switch attempt look broken even after wiring it up naively.

## What we changed

- `backend/ibkr/gateway_heal.py`: `suppress_self_heal(seconds)` / `self_heal_suppressed()` — a short-lived flag so one intentional switch attempt cannot be silently healed back to paper.
- `backend/ibkr/client.py`: `request_gateway_mode(mode)` — persists + applies `IBKR_GATEWAY_MODE`, suppresses self-heal, disconnects, and polls the background `reconnect_loop`'s result (does not connect itself — `ib_async` does not support concurrent `connectAsync` on one `IB()`). Refuses (disconnects) if a "live" target connects but `broker_account_kind` is not `live`. `_try_connect_alternate_port` now checks `self_heal_suppressed()` before healing.
- `backend/routes/trading.py`: `POST /api/ibkr/gateway-mode` thin route.
- `frontend/src/ibkr/useIbkrStatus.ts`: `refreshIbkrStatusNow()` — a `window` event broadcast so every mounted `useIbkrStatus()` polls immediately instead of waiting up to 5s.
- `frontend/src/stock_view/StockViewTradingChrome.tsx`: capsule calls the new route after `window.confirm`, shows `…` while switching, renders the backend's error text inline (`.sv-capsule__error`) on failure.
- `constantGroups/chart_api.ts`: capsule title copy rewritten to describe the real switch instead of "this control does nothing."
- Tests: `backend/tests/test_gateway_mode_switch.py` (new), additions to `test_gateway_heal.py` and `test_routes_trading.py`; `frontend/src/stock_view/StockViewTradingChrome.test.tsx` (new).
- Docs: `docs/ibc-gateway-setup.md` new "Switching Paper ↔ Live from Nova's UI" section.

## How it works now

`request_gateway_mode` never connects directly — it only mutates env/`.env` and disconnects, then polls `is_connected()` for up to `IBKR_CONNECT_TIMEOUT_SEC + 3s` while the existing background `reconnect_loop` (the sole owner of the `IB()` instance) dials the newly-configured port on its next tick. This keeps a single connection-attempt code path instead of adding a second one that could race the loop. The self-heal suppression window (`IBKR_CONNECT_TIMEOUT_SEC + IBKR_RECONNECT_DELAY_SEC`) covers exactly one such attempt, so a refused live port is reported honestly by the route instead of the loop's existing live→paper self-heal kicking in mid-switch. `IBKR_LIVE_TRADING_CONFIRMED` is never touched by any of this — `ibkr/safety.py` remains the sole gate for live spend, so a successful Live switch still reports `spend_status: locked_live_unconfirmed` until armed separately.

## Why this approach

Considered having the route connect directly (bypassing the loop) for a faster/more deterministic result, but `ib_async`'s `IB()` instance is not designed for concurrent `connectAsync` calls from two code paths, and the existing `reconnect_loop` already re-reads `.env`/env every tick — reusing it avoids a second connection-attempt implementation to keep in sync with paper-pin/kind classification logic in `_accept_connected_session`. Considered making the "refuse paper account on live port" check part of the shared `_accept_connected_session` (used by every background connect, not just the switch route) for symmetry with the existing paper pin, but scoped it to the switch route instead: it is a defensive check for an IBKR-topology edge case that should not happen in practice (Gateway port is tied to which account was used to log in), and changing shared background-connect behavior for an edge case outside what was reported/asked risked affecting live sessions that are already running correctly. The self-heal suppression uses a time-window flag rather than a boolean toggle so a crashed/never-cleared switch attempt cannot permanently disable self-heal.

## Verification

- `pytest backend/tests/test_gateway_mode_switch.py backend/tests/test_gateway_heal.py backend/tests/test_routes_trading.py backend/tests/test_ibkr_client_connect.py -q` → 30 passed.
- Full backend suite `pytest backend/tests -q` → 841 passed, 1 pre-existing unrelated failure (`test_hod_momo_universe.py::test_build_focus_universe_empty_inputs`, fails in isolation too, not touched by this change).
- `npx vitest run src/stock_view/StockViewTradingChrome.test.tsx src/stock_view/StockViewHeader.test.tsx` → 8 passed; full frontend suite → 396 passed.
- `npx tsc -b` shows one pre-existing unrelated error (`TabModuleHost.tsx` / `TradingTabProps.initialSection`, present before this session's changes and reproduced on `git stash`) — not introduced by this task.

## Follow-ups

- Auto-login to Live Gateway / storing credentials and auto-arming `IBKR_LIVE_TRADING_CONFIRMED` remain explicit non-goals (per plan).
- The pre-existing `TabModuleHost.tsx` TS build error is unrelated and out of scope; worth a separate fix.

## Keywords

Paper Live switch, IBKR_GATEWAY_MODE, request_gateway_mode, gateway-mode route, self-heal suppress, StockViewAccountModeCapsule, refreshIbkrStatusNow, broker_account_kind mismatch, live spend lock
