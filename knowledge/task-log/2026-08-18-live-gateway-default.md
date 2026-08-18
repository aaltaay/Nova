# 2026-08-18 -- Live Gateway is the default door

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** `CHANGELOG.md` 2026-08-18 -- Gateway default is live; paper is fallback

## Task

Make live (port 4001) the default Gateway Nova checks on boot. Paper (4002) becomes the fallback / secondary option. Align morning IBC scripts with that.

## Goal

A cold start knocks on 4001 first. If live is dark and paper is up, follow-Gateway can still attach to 4002. Spend keys stay as the operator already set them.

## Why it mattered

Nova and IBC were both paper-first. The operator's morning desk is live market data. Waking up to a Paper target while a Gateway window was already green was the wrong door, not a missing login label.

## What we changed

- Constitution Invariant #7 and §5: Gateway connection default is live; spend still gated; `auto_live` NO-GO
- `IBKR_GATEWAY_MODE_DEFAULT = "live"`
- `.env` `IBKR_GATEWAY_MODE=live` (local, not committed)
- Local IBC `TradingMode=live` + `TRADING_MODE=live` in the StartGateway wrapper
- `.env.example` and IBC setup docs
- Tests for unset env → live, explicit paper still wins

## How it works now

1. Nova reads `IBKR_GATEWAY_MODE` (default live) and dials 4001.
2. If 4001 is dark and 4002 is listening, follow-Gateway may persist paper and attach.
3. IBC morning login is live. Phone 2FA may be required.
4. Place/bracket still need `IBKR_ORDERS_ENABLED` and, on live, `IBKR_LIVE_TRADING_CONFIRMED`.

## Why this approach

Changing only `.env` would leave the next clean install and the IBC wrapper on paper, so the morning mismatch would return. Changing only IBC would leave Nova knocking on 4002. Both had to move together.

Rejected treating this as "arm live trading." The ask was which door Nova checks first. Spend flags were already set by the operator; this change does not flip them.

Rejected killing the current Gateway process from the agent. Config now says live; the running window is still yesterday's paper login until IBC is restarted and 2FA is approved.

Earlier (2026-08-16) we rejected auto-live IBC because overnight live login means phone 2FA. The operator has now chosen that cost.

## Verification

- `py -3 -m pytest backend/tests/test_ibkr_safety.py::TestGatewayModeDefault backend/tests/test_ibkr_safety.py::TestOrderSafetyGate -q` -- 10 passed
- `py -3 tools/doc_invariants.py` -- OK
- `npm run build` (frontend) -- exit 0
- After `Run Nova.bat` restart: `GET /api/ibkr/status` → `gateway_mode=live`, `preferred_port=4001`, `spend_status=live_armed`, `disconnect_hint=both_ports_unreachable`
- API log 10:37:20: `attempting connect to 127.0.0.1:4001 (live)` then `trying paper:4002 (follow-Gateway self-heal)`

## Follow-ups

- Restart Gateway via local IBC so the live socket (4001) actually listens.
- Confirm the operator wants `spend_status=live_armed` once that session is READY (both spend flags are already true).
- Do not commit `.env` or `%USERPROFILE%\.nova\ibc\`.

## Keywords

IBKR_GATEWAY_MODE, live, paper, 4001, 4002, IBC, TradingMode, fallback, follow-Gateway
