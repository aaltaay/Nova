# 2026-08-26 -- Dual API Error 326 desk restore

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops / market-feed
- **Related:** `CHANGELOG.md` §2026-08-26 Dual API Error 326 · `PROBLEM_LOG.md` §2026-08-26 Dual API stole clientId 17

## Task

Address the Trading prerequisites red state: Gateway session not READY (reason: connecting) plus door trail "Failed to fetch" while targeting live port 4001.

## Goal

One Nova API on :8000, one IBKR clientId 17 session READY, honest copy when a second process steals the slot, door trail readable again.

## Why it mattered

The checklist told the operator this was reconnect-stuck / Error 1100 (or implied login). Gateway was already up. A stray `uvicorn` and the morning sidecar were fighting clientId 17. New HTTP (door trail, health) was refused because the sidecar listen socket was gone.

## What we changed

- `backend/api_instance_lock.py` -- cache lock (`schema_version` 1, owner this module, stale when PID dies)
- `backend/main.py` -- `acquire_or_exit()` after app wiring (before bind on import)
- Error 326 handled in `session_errors` / `client_connect` / `session_reconnect` as `client_id_in_use`
- Prerequisites + door trail copy; feed-rule anti-pattern

## How it works now

Starting a second API exits with a loud lock error. If Error 326 still happens (TWS/other client), status reason is `client_id_in_use` and the checklist says stop the extra API -- not 2FA. Door trail fetch failures say the API did not answer.

## Why this approach

A bind-only check is not enough on Windows (SO_REUSEADDR lets a second listen). A PID lock at `main` import covers `run_api.py` and `python -m uvicorn main:app`. Changing clientId on conflict was rejected -- ADR 010 is one clientId; two APIs is the bug. Killing the API for a slow health probe remains forbidden; this restart was a dead listen socket (new TCP refused), not loop starve.

## Verification

- `pytest tests/test_api_instance_lock.py tests/test_ibkr_session_errors.py tests/test_ibkr_client_connect.py tests/test_gateway_heal.py` -- 39 passed
- Vitest tradingPrerequisites / formatDoorTrail / GatewayDoorTrail -- 20 passed
- Live: single `run_api.py`, `/api/ibkr/status` READY, `/api/ibkr/gateway-trail` returns events, `/api/movers` has rows

## Follow-ups

Do not start `uvicorn` beside Desktop/morning `run_api.py`. Morning task should keep refusing to kill a living API; the lock now also refuses a second start.

## Keywords

Error 326, clientId, dual API, door trail, session READY
