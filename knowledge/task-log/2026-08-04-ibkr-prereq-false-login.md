# 2026-08-04 -- IBKRPRO up but Nova prereq false login / stuck synchronizing

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops / market-feed (UI honesty)
- **Related:** `CHANGELOG.md` 2026-08-04 -- Honest IBKR prereq · `PROBLEM_LOG.md` 2026-08-04 -- IBKRPRO up but Trading prerequisites said not READY

## Task

Diagnose why Trading prerequisites showed IB Gateway not READY / login+2FA while IBKRPRO Gateway already showed API Server connected.

## Goal

Restore a usable IBKR session and stop mislabeling "Nova stuck reconnecting" as a Gateway login failure.

## Why it mattered

Live desk was blocked with a false 2FA story while Gateway was healthy. That wastes operator time and hides the real failure (long-lived API session after Error 1100).

## What we changed

- Restarted Nova API (ops) -- session returned READY on live port 4001.
- Prerequisites: port-open / `*_port_open_but_disconnected` → honest detail + `reconnect_ibkr` CTA (`POST /api/ibkr/reconnect`).
- `earn_usable`: transport_down clears sticky `SYNCHRONIZING`.
- `reconnect_loop`: per-iteration crash fence; clear SYNCHRONIZING when TCP is down before redial.
- Tests: readiness + Vitest prereq case.

## How it works now

`status.connected` = usable READY (not raw Gateway window state). When the preferred API port is listening but Nova is not usable, the desk asks to reconnect Nova, not to re-login. A wedged in-process client after hours of reload may still need an API restart; reconnect CTA is the first self-heal step.

## Why this approach

- Rejected treating Gateway window green as product READY -- that would re-break the 1100 soft-blip honesty from 2026-07-31.
- Rejected only fixing copy without a Reconnect CTA -- operator still needed a one-click path short of killing the API.
- Kept API restart as the hard recovery when in-process `connectAsync` thrashes while an out-of-process probe succeeds (poisoned long-lived worker).

## Verification

- After API restart: `GET /api/ibkr/status` → `connected=true`, `session_state=ready`, `mode=live`, `broker_account_kind=live`.
- Side-script `connectAsync(clientId=17)` succeeded while wedged API could not (evidence for process-local wedge).
- `pytest tests/test_ibkr_client_readiness.py` (27 passed); Vitest `tradingPrerequisites.test.ts` (6 passed).

## Follow-ups

- Prefer starting API with `NOVA_API_RELOAD=0` for trading sessions (reload + 20h+ uptime was part of the wedge).
- If reconnect CTA fails while port stays open, UI already hints to restart Nova API.

## Keywords

IBKRPRO, session READY, synchronizing, Error 1100, trading prerequisites, reconnect, false 2FA
