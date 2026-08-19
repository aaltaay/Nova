# 2026-08-19 -- Gateway launch must not kill a listening session

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops / market-feed
- **Related:** `CHANGELOG.md` 2026-08-19 · `PROBLEM_LOG.md` 2026-08-19 Open live Gateway killed a logged-in session

## Task

Stop the morning "self-heal" path from restarting a logged-in IB Gateway and leaving Nova flickering / not READY.

## Goal

Open live/paper attaches when that API port is already up. Login banner and kill-CTAs only when the ports are actually dark.

## Why it mattered

Today (2026-08-19) Gateway farms were green on 4001. Nova still asked for 2FA. Open live Gateway Stop-Process'd IBC at 13:47. API :8000 was down by 14:01. Morning check at 03:55 had already failed on `session_reason=connecting` while health was green. Yesterday's follow-Gateway work does not cover "same port already listening."

## What we changed

- `launch_or_focus_gateway`: already_listening / focused_authenticating; kill+IBC only on a real mode switch
- Prerequisites: launch buttons only for `launch_gateway`; API_DOWN hides them; API_WEDGED uses Reconnect
- Login banner hides for port-open-but-disconnected and missing status fields
- Vite launch middleware probes 4001/4002 before spawning IBC
- Morning check retries connecting/synchronizing up to ~90s

## How it works now

Self-heal for this class is: do not destroy the healthy door. If 4001 LISTEN, persist live mode and wake reconnect. If the process is up and neither port LISTEN, that is 2FA -- focus, do not restart. Restart IBC only when you asked for a dark door and the other door is already logged in.

## Why this approach

Rejected "always restart IBC so mode matches ini" -- that is the flicker. Rejected auto-login (credentials stay out of git). Rejected treating API_WEDGED as API_DOWN (ADR 010). Morning check wait is cheaper than claiming READY on LISTEN alone.

## Verification

- `py -3 -m pytest tests/test_launch_gateway.py` -- 10 passed
- Vitest `tradingPrerequisites.test.ts` + `GatewayDisconnectedBanner.test.tsx` -- 24 passed
- `npm run build` -- tsc + vite exit 0
- After starting `backend/run_api.py` (port 8000 was refused): `/api/ibkr/status` `connected=true` `session_state=ready` `mode=live` `preferred_port_reachable=true`. Gateway process was left running (started 13:47). `ib_loop_lag_ms.wedged=false`.

## Follow-ups

API still has to be running for reconnect. WS1 Discord channel still missing (03:55 alert 404/timeout). Do not claim Jul 30 morning FIXED until an unattended 03:55 PASS line exists with `connected=true`.

## Keywords

IBC, 4001, already_listening, Open live Gateway, flicker, morning check, connecting
