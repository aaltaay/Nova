# 2026-07-20 — IBKR disconnect foresight: sticky intent + port diagnostics

- **Status:** completed
- **Agents:** parent (implement) · [Daddy](4f185dc0-cf57-4c56-bc0a-9841c4fc2c29) (audit)
- **Domain:** ibkr-ops · widgets · docs
- **Related:** `CHANGELOG.md` §2026-07-20 IBKR disconnect foresight · `PROBLEM_LOG.md` §Disconnected while Gateway green

## Task

Harden Nova so “Gateway green / Nova Disconnected” (and silent heal-back after a failed Live switch) cannot trap operators without a clear, durable path — without ever auto paper→live or unlocking spend.

## Goal

Root-cause fix for connection-state split-brain: sticky status-visible intent, refused-only heal, port diagnostics on `/api/ibkr/status`, actionable UI + docs/MDC accuracy.

## Why it mattered

Users logged into Live Gateway while Nova still targeted Paper saw bare Disconnected; self-heal correctly refuses paper→live, but a timed suppress after intentional Live could expire and silently flip back to Paper. Same class of bug as flatten dual-source qty — multiple writers, no SSOT for “what are we trying to reach.”

## What we changed

- `gateway_heal.py` — sticky `intentional_gateway_mode` (replaces suppress timer); clear stale `_last_heal` on preferred connect; connect outcome fields on status
- `client_connect.py` — extracted attempt/heal connect; heal only on `"refused"`
- `client.py` — atomic `_set_session`; `wake_reconnect_loop` / interruptible sleep; `set_intentional_mode` on switch
- `port_diagnostics.py` — TCP probe + `disconnect_hint` for status
- Frontend — `disconnectCopy.ts`, Stock View warn/CTA, gateway-mode 404 restart hint, mode-aware empty IBKR copy
- `ibkr-gateway-login-warning.mdc` + `docs/ibc-gateway-setup.md` — heal asymmetry documented

## How it works now

User clicks Live → persist mode + sticky intentional live → wake reconnect. Heal cannot run while intentional is set. If 4001 refuses and intentional is clear, heal may go paper. If Nova is paper and only 4001 listens, status `disconnect_hint=paper_port_refused_live_listening` and UI offers Switch to Live. Never auto paper→live; never touch `IBKR_LIVE_TRADING_CONFIRMED`.

## Why this approach

- **Sticky intent over longer timer:** a timer still forgets user intent; sticky state is the same SSOT move as `long_qty` on `positions()`.
- **Refuse-only heal:** timeout often means clientId/wedge on a live Gateway that *is* up — healing to paper then is wrong.
- **Probe-only alternate port:** diagnose without attaching an IB session to the “wrong” account.
- **Rejected:** auto paper→live (unsafe); keeping suppress seconds as the product API (still a band-aid).

## Verification

- `pytest backend/tests/test_gateway_heal.py test_gateway_mode_switch.py test_port_diagnostics.py` (+ status hint in `test_routes_trading`)
- Vitest `disconnectCopy.test.ts`, `StockViewTradingChrome.test.tsx` (404 + CTA)

## Follow-ups

- Restart local API after pull so `/api/ibkr/gateway-mode` is loaded
- Optional: surface `gateway_self_heal` + port numbers on header Gateway chip (P1)
- Pre-existing: some `test_routes_trading` place-order happy-path failures (unrelated)

## Keywords

disconnect, port mismatch, sticky intent, self-heal, disconnect_hint, gateway-mode, 4001, 4002, paper pin
