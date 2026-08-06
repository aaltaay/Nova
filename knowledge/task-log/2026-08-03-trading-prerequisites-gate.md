# 2026-08-03 -- Trading prerequisites gate (no Alpaca as API)

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed | ibkr-ops | execution (UI gate only)
- **Related:** `CHANGELOG.md` §2026-08-03 Trading prerequisites · `PROBLEM_LOG.md` §2026-08-03 Alpaca-as-API health

## Task

Stop treating Alpaca as "the API," and put a clear trading-prerequisites front door in front of the user when Nova API or IB Gateway is down -- without wiping scanner/chart data.

## Goal

User sees a checklist of required services (Nova API :8000, IBKR enabled, Gateway READY, orders armed) with heal CTAs; desk is blocked until API + Gateway are up; header API chip means Nova process only.

## Why it mattered

Misleading "up · Alpaca account RTT" made the desk look healthy when the real trading path is IBKR. Scattered banners/spend badges existed but never formed one "get these up before you trade" gate -- trust-damaging for live trading.

## What we changed

- `backend/health_status.py` -- `mark_nova_process_health()` is API chip SoT; Alpaca `/v2/account` no longer writes `cached_health`
- `backend/app_lifespan.py` -- bootstrap marks process health; Alpaca keys missing only warn
- `backend/integrations_health.py` -- Alpaca chip from keys presence, not account RTT
- `frontend/src/ibkr/tradingPrerequisites.ts` + `TradingPrerequisitesGate.tsx` -- checklist + blocking overlay
- Header: remove Alpaca RTT label and Alpaca/News integration chip
- `GlobalBarStatusBridge` uses real `diagnoseBackend()` (API_DOWN vs API_WEDGED)

## How it works now

- API chip = Nova process reachable (`health_source=nova_process`)
- Gateway chip / `/api/ibkr/status` = IBKR session
- If Nova API or Gateway fails: full-viewport `TradingPrerequisitesGate` with Start API / Launch Gateway / .env spend hints
- Spend lock does not full-block the desk (tickets still refuse place); it appears on the checklist when the gate is open
- Scanner/chart state is not cleared under the overlay

## Why this approach

Unify existing heal paths (Start API, Launch Gateway, spend env) behind one checklist instead of inventing new backend readiness infrastructure or wiping caches. Rejected full Alpaca rip (news/listing still need it) and rejected clear-on-outage (user asked for stop/block, not wipe).

## Verification

- `py -3 -m pytest tests/test_health_latency_attribution.py tests/test_integrations_health.py -q`
- `npx vitest run src/ibkr/tradingPrerequisites.test.ts src/components/HeaderConnectionStatus.test.tsx`

## Follow-ups

- Optional soft banner when only spend is locked (desk otherwise ready)
- Later: replace Alpaca news/listing/avg-vol aux if product wants zero Alpaca HTTP

## Keywords

trading prerequisites, API_DOWN, API_WEDGED, Alpaca account RTT, nova_process, TradingPrerequisitesGate, IB Gateway, spend_status
