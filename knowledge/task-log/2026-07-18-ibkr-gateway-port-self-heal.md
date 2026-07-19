# 2026-07-18 — IBKR Gateway paper/live port self-heal

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops / market-feed (Gateway connect)
- **Related:** `CHANGELOG.md` § IBKR Gateway paper/live port self-heal · `PROBLEM_LOG.md` § Stock View Disconnected while paper Gateway was connected

## Task

Make paper/live Gateway port mismatch self-heal so Stock View does not stay “Disconnected” when Gateway is up on the other API port.

## Goal

Preferred port refuse/timeout → try alternate (4001↔4002) → persist `IBKR_GATEWAY_MODE` → reconnect; never unlock orders; still warn when neither port is up.

## Why it mattered

User ran paper Gateway (4002) while `.env` said `live` (4001). Gateway’s own status looked fine; Nova looked broken. Manual `.env` edits should not be required for this class of mismatch.

## What we changed

- Added `backend/ibkr/gateway_heal.py` (classify failure, persist mode, heal status).
- Wired reconnect loop in `ibkr/client.py` to try alternate port after refuse/timeout.
- Exposed `gateway_self_heal*` on `GET /api/ibkr/status`.
- Constant `IBKR_GATEWAY_SELF_HEAL_DEFAULT` + `.env.example` / login-warning rule note.
- Tests in `test_gateway_heal.py`.

## How it works now

Reconnect: preferred port → on refuse/timeout, alternate port → on success set `os.environ` + rewrite `.env` + log `IBKR: self-healed gateway_mode`. Spend still requires `safety.py` gates. Disable with `IBKR_GATEWAY_SELF_HEAL=false`.

## Why this approach

- **Tried alternate after real IB connect failure** (not TCP-only probe) so Immersed-style false ports are not mistaken for Gateway.
- **Persist `.env`** so the next process start matches the live Gateway without re-healing every boot.
- **Rejected** auto-unlocking orders or flipping live confirm — port heal is data-path only.
- **Rejected** UI Paper/Live buttons as the heal mechanism (they are status/docs only today).

## Verification

`py -3 -m pytest tests/test_gateway_heal.py tests/test_ibkr_client_connect.py -q` → 10 passed.

## Follow-ups

Optional UI chip when `gateway_self_heal` is set; IBC still required when neither port listens.

## Keywords

IBKR, gateway_heal, IBKR_GATEWAY_MODE, 4001, 4002, self-heal, Disconnected, paper, live
