# 2026-08-16 -- Follow the logged-in Gateway after overnight IBC restart

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** `CHANGELOG.md` §2026-08-16 -- Follow the logged-in Gateway · `PROBLEM_LOG.md` 2026-08-16 -- Live pin + IBC paper restart

## Task

Investigate why paper/live did not come back cleanly and why Gateway looked closed this morning.

## Goal

Desk attaches to the Gateway that is actually logged in, and the UI tells the truth when the other port is the one that is up.

## Why it mattered

Every morning restart felt like a 20-minute login ritual. This time Gateway was never closed -- Nova was aimed at the wrong port and screamed 2FA.

## What we changed

- Sticky Paper/Live intent still blocks follow-Gateway for 120s (mid-switch 2FA).
- After that grace, preferred dark + alternate up → follow-Gateway.
- Prerequisites: "Use paper Gateway" / "Use live Gateway" instead of Open IB Gateway.
- Loud login banner no longer fires on port-mismatch hints.
- Immediate ops: switched Nova to paper; session READY.

## How it works now

IBC `TradingMode=paper` + AutoRestart 11:45 PM brings Gateway back as paper. If you left Nova on Live, it will follow paper after two minutes (or you click Use paper Gateway). Click Live when you want live money and finish phone 2FA. Spend gates stay locked unless already armed.

## Why this approach

Rejected keeping sticky intent forever (this morning's trap). Rejected the old 18s timer (yanked mid-2FA). Rejected auto-changing IBC TradingMode to live (overnight live login means 2FA on the phone every night). Follow the listening Gateway after a short grace is the "just work" path.

## Verification

- `GET /api/ibkr/status` after paper switch: connected=true, mode=paper, session_state=ready, port 4002
- pytest `backend/tests/test_gateway_heal.py`
- Vitest tradingPrerequisites + GatewayDisconnectedBanner
- `npm run build`

## Follow-ups

Restart Nova API once so the 120s grace is loaded in the running process. IBC TradingMode can stay paper for a smooth overnight desk; use the capsule for live sessions.

## Keywords

IB Gateway, IBC, AutoRestart, paper, live, follow-Gateway, intentional mode
