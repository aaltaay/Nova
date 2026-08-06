# 2026-07-31 -- IBKR usable-session SoT recovery (core + consumers/ops)

- **Status:** completed
- **Agents:** parent subagent (core) + follow-up subagent (consumers/ops)
- **Domain:** market-feed / ibkr-ops (in-session; no specialist hop)
- **Related:** `CHANGELOG.md` §2026-07-31 IBKR usable-session SoT · `PROBLEM_LOG.md` §2026-07-31 Error 1100 stuck unusable

## Task

Implement Nova's IBKR usable-session SoT recovery plan end-to-end: core spine (1100/1101/1102, earn_usable, status honesty) plus consumer/ops follow-ups (banner gate, chart_bars, honest get_ib None detail, integrity, smoke, daily start).

## Goal

Soft IB connectivity blips restore usability automatically (or force-reconnect within ~30s); Authenticating Gateway backs off without heal thrash; `/api/ibkr/status.connected` means product-usable; UI/ops never treat transport-up-but-unusable as a login CTA or healthy skip.

## Why it mattered

A single Error 1100 left the desk green on the chip but dead on charts/orders until a human noticed -- the worst kind of split-brain for a trading UI. After the core SoT landed, the login banner / integrity / smoke / daily start could still lie about "Gateway down" vs "session recovering".

## What we changed

### Core (prior agent)

- Constants: 1101/1102 names, `IBKR_UNUSABLE_FORCE_RECONNECT_SEC`, auth-backoff, positions warm timeout
- `session_errors`: revoke+stamp+wake on 1100; restore enqueue on 1101/1102; persist last code/ts
- `session_usable.earn_usable`: single-flight warm → fence → READY → `_on_session_ready`
- `session_reconnect` + `client_ops`: dialer recovery, force_reconnect awaits usable
- Status: `connected`=usable, `transport_connected`, `session_reason`/`session_state`/`session_generation`; port hints use transport
- Positions warm-up wrapped in `asyncio.wait_for`

### Consumers / ops (this follow-up)

- `GatewayDisconnectedBanner`: login CTA only when transport down / ports dark / disconnect login hint; hide on transport_up + !usable (Error 1100)
- Wired `transport_connected` / `session_reason` / ports / disconnect_hint through types, `useIbkrStatus`, `WorkspaceContext`, `DashboardPage`
- `chart_bars` early gate uses `is_ready()`; error detail includes SoT reason when transport is up
- `client.unavailable_detail()` + call sites in `bars.py`, `tape_stream.py`, `depth/subscribe.py`, `account.py`
- `integrity_live` `ibkr_connected` / scanner_feed use `is_ready()` (usable)
- `smoke_check.ps1` fails if not usable; reports transport + reason separately
- `Start-NovaDaily.ps1` waits for Gateway API port then status.connected; never treats Authenticating title / LISTEN alone as healthy; loud 2FA STATUS warn; no Gateway kill / no IBC edits

## How it works now

Public SoT is usable + reason (+ transport diagnostic). Connectivity error handlers never issue IB requests; they enqueue and wake. The reconnect loop never idles on bare 5s sleep while `transport_up && !usable`. UI login banner and ops scripts key off the same split: transport for "is Gateway down?", usable for "can we trade/scan?".

## Why this approach

- Rejected expanding DEGRADED into more product states -- public story is usable+reason
- Rejected soft READY on 1102 without `_on_session_ready` / generation bump -- leases would lie
- Rejected redefining `connected=is_ready()` without a transport field -- breaks port hints
- Rejected showing login CTA whenever `!connected` after SoT flip -- false alarm on every 1100
- Rejected daily-start "healthy" = process title or LISTEN -- Authenticating still needs 2FA
- Extracted modules to keep new files <400 lines and shrink `client.py` after growth

## Verification

```text
# Core (prior)
pytest tests/test_ibkr_session_errors.py tests/test_ibkr_client_readiness.py
  tests/test_routes_trading.py::test_status_route_* ...
# 65 passed

# Consumers/ops (this follow-up)
pytest tests/test_ibkr_client_readiness.py tests/test_ibkr_account.py
  tests/test_integrity_live_builders.py tests/test_hod_momo_integrity.py
  tests/test_scanner_integrity_mode.py tests/test_routes_trading.py
# 83 passed

npx vitest run src/ibkr/GatewayDisconnectedBanner.test.tsx
  src/workspace/WorkspaceContext.test.tsx
# 13 passed
```

## Follow-ups

Live smoke against a real 1100/1102 cycle when Gateway blips.

## Keywords

IBKR, Error 1100, 1101, 1102, earn_usable, usable session, SoT, auth-backoff, transport_connected, session_reason, reconnect_loop, GatewayDisconnectedBanner, chart_bars, integrity_live, smoke_check, Start-NovaDaily, unavailable_detail
