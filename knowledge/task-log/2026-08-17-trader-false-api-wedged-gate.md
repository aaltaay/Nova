# 2026-08-17 -- Trader click flashed a false API_WEDGED gate

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / ibkr-ops / frontend
- **Related:** `CHANGELOG.md` §2026-08-17 -- Trader open no longer fake-blocks · `PROBLEM_LOG.md` §2026-08-17 -- Trader click flashed Trading prerequisites

## Task

Fix Paper/Live looking like a no-op, then explain and stop the Trading prerequisites modal that appeared the moment Trader was pressed.

## Goal

Trader can open without a fake "API hung" overlay. Paper/Live shows the configured target. Desk is not told to Start API on a probe timeout.

## Why it mattered

The operator clicked Live, then Trader, and got a full-screen block that said the API was a hung process. Gateway was green in the same modal. That is the ADR 010 failure mode again: a slow probe treated as a dead PID.

## What we changed

- `buildTradingPrerequisites`: client `API_WEDGED` does not fail the API row or `blockDesk`; Start API only for `API_DOWN`; server `ib_loop_lag_ms.wedged` still blocks without Start API
- `GlobalBarStatusBridge`: two consecutive `/api/mode` failures before publishing disconnected/WEDGED (same grace as scanner polls)
- `resolveCapsuleSelection`: prefer `gateway_mode` over session `mode`; optimistic thumb while the POST is in flight
- App dialog overlay/content z-index 10000 (above the gate at 9000)
- WEDGED hint copy no longer says auto-restart / Start API

## How it works now

Opening Trader can still stall a 4s `/mode` probe. One miss is ignored. A WEDGED flag in health is honest in the header, not a desk lock. The capsule paints the port Nova is targeting. Confirm/Switch is visible even if the gate is up. Spend gates are unchanged.

## Why this approach

Rejected killing the API (ADR 010). Rejected treating every WEDGED as DOWN -- the PID was listening and `/livez` was 84ms. Rejected removing the gate entirely -- real API_DOWN and a server-reported IB wedge should still block. Grace of 2 matches the existing scanner-poll contract instead of inventing a third timeout.

## Verification

- `npx vitest run` on 7 files: 43 passed
- `npm run build`: exit 0
- Soak: POST `/api/ibkr/gateway-mode` paper, live, paper, live -- all ok, connected, 506-719ms; left on live READY

## Follow-ups

HTTP loop `max_ms` still 42759 from the Trader-open stall. ADR 010 isolation is not fully keeping Trader subscribe work off the uvicorn loop. Do not "fix" that by auto-killing the PID.

## Keywords

API_WEDGED, Trading prerequisites, Trader, Paper Live, gateway_mode, Start API, probe timeout
