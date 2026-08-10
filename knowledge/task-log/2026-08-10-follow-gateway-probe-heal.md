# 2026-08-10 — Follow-Gateway probe-based IBKR port heal

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops / market-feed
- **Related:** `CHANGELOG.md` §2026-08-10 — Follow-Gateway probe heal · `PROBLEM_LOG.md` §2026-08-10 — Port heal stuck on timeout

## Task

Make paper/live Gateway port mismatch self-healing a core reconnect law so Nova attaches to whichever API port is actually listening without babysitting `.env`.

## Goal

Preferred dark + alternate up → heal (refuse, timeout-on-dark, or pre-dial TCP probe); preferred still listening + timeout → no heal; spend gates unchanged; tests + docs/MDC updated.

## Why it mattered

User logged into Live Gateway (4001) while Nova targeted paper (4002). Status correctly showed `paper_port_refused_live_listening`, but heal never fired because Windows timed out the dark preferred port and heal was refuse-string-only. Scanners stayed blocked despite a healthy Gateway window.

## What we changed

- `gateway_heal.alternate_heal_eligible` — probe-based eligibility
- `client_connect.try_connect_alternate_port` — uses probes; timeout-on-dark heals
- `client_connect.maybe_heal_from_port_probes` + reconnect fast path before preferred dial
- Tests for eligibility, timeout-on-dark, preferred_dark
- `ibkr-gateway-login-warning.mdc`, `docs/ibc-gateway-setup.md`, client docstrings

## How it works now

Nova follows the listening Gateway. On each reconnect: if preferred TCP is dark and the other mode's port is up, attach there immediately, persist `IBKR_GATEWAY_MODE`, then `earn_usable`. If preferred connect fails as refuse, or as timeout while preferred is still dark, same heal. If preferred still listens and connect times out (326 / 2FA wedge), do not jump ports. Intentional Paper/Live capsule still blocks silent heal. Orders stay gated by `safety.py`.

## Why this approach

**Required.** Refuse-only heal was too brittle on Windows (closed ports often time out). Jumping on every timeout was unsafe when preferred still listens (clientId / Authenticating). TCP probes match the status UI's `disconnect_hint` truth. Pre-dial fast path avoids an 8s preferred timeout tax every mismatch. Rejected: always-paper pin only (does not fix today's Live Gateway); silent live spend unlock (never).

## Verification

- `py -3 -m pytest tests/test_gateway_heal.py tests/test_port_diagnostics.py tests/test_ibkr_client_connect.py -q` → 24 passed
- Live API log after restart: `preferred paper:4002 failed (refused…); trying live:4001 (follow-Gateway self-heal)` — heal path fired; Gateway then refused/timed out API accept (wedged socket / settings), separate from eligibility

## Follow-ups

- Pin IBC `TradingMode` to reduce how often heal must fire
- UI banner when `gateway_self_heal.to_mode=live` (honest "attached to LIVE")

## Keywords

IBKR, gateway_heal, follow-Gateway, probe, 4001, 4002, self-heal, preferred_dark
