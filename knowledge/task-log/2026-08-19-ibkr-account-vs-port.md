# 2026-08-19 -- Paper/Live follows IB account not port

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops / market-feed
- **Related:** `CHANGELOG.md` 2026-08-19 Paper/Live follows the IB account · `PROBLEM_LOG.md` 2026-08-19 Live snap-back · ADR 013

## Task

Make Paper/Live a real door workflow: do not kill a session that is already the requested account class; do not treat 4001 LISTEN as live; do not snap the capsule back to Paper after a Live click.

## Goal

Clicking Live while already live is a no-op. Clicking Live while the IB login is paper restarts IBC as live (2FA on the desktop). The capsule shows the account class, with Live held only while that click is in flight.

## Why it mattered

The desk had a paper DU login on port 4001 from an earlier attach. That looked like "already live." A Live click followed paper, persisted paper, and bounced the capsule. Killing a healthy Gateway the same morning was the other half of the same confusion.

## What we changed

- ADR 013: requested door vs listen port vs `managedAccounts` kind
- `mode_identity.switch_plan` / `follow_paper_allowed`
- `request_gateway_mode`: noop vs `launch_or_focus_gateway(..., force_restart=True)`
- `launch_gateway`: stop LISTEN owners on 4001/4002 (java included)
- Capsule + header tooltip: account kind, not port
- Follow-paper still allowed when there is no Live click (overnight scanners)

## How it works now

If `broker_account_kind` already matches the click, Nova persists that door and leaves Gateway alone. If it does not (or Nova is disconnected), Nova sets sticky Live/Paper intent, kills the Gateway API listeners, starts IBC with that TradingMode, and waits for 2FA without following a leftover paper socket. Live spend is still a separate env gate.

## Why this approach

Reconnect-to-4001 cannot become live if the login is DU. The only way to change account class is IBC TradingMode (same username, different door). Auto-promoting paper to live is forbidden. Treating 4001 as live is how we lied to the operator. Force restart is scoped to the capsule door change, not the Open live button on an already-listening port.

## Verification

pytest `test_mode_identity.py`, `test_launch_gateway.py`, `test_gateway_mode_switch.py`, `test_ibkr_account_kind.py`; Vitest `GatewayModeCapsule.test.ts`; `npm run build`; API restart and status / gateway-mode POST.

## Follow-ups

If IBC `TradingMode=live` still returns a DU account, that is an IB login/config problem -- Nova must stay disconnected with Live intent, not snap to Paper. Confirm IBC config TradingMode after a real Live click. `auto_live` remains NO-GO.

## Keywords

ADR 013, Paper, Live, 4001, account kind, IBC, force_restart
