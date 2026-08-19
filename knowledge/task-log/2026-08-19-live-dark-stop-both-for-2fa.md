# 2026-08-19 -- Live dark means stop both doors so 2FA can appear

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** `CHANGELOG.md` 2026-08-19 Live dark means stop both doors · `PROBLEM_LOG.md` 2026-08-19 Live click with paper still on 4002 skipped 2FA · ADR 013

## Task

Continue the Paper/Live work after Live produced no real 2FA.

## Goal

When Live is a new login (4001 dark), the operator sees IBKR Mobile / SECOND FACTOR. When live is already logged in on 4001, a Live click only reconnects.

## Why it mattered

"Keep both Gateways" plus "Live must show real auth" fought each other. One IBC install retargets one Java window. Leaving paper on 4002 made a Live click start IBC with no new login dialog.

## What we changed

- `request_gateway_mode` uses `force_restart=True` for `start_ibc` and `replace_target`.
- `launch_or_focus_gateway(force_restart=True)` stops both listen ports, then IBC that door.
- Live spawn always clears `Restart=OK`.
- Spawn / ADR / IBC setup / login-warning copy no longer say the other Gateway stays up.

## How it works now

- Target port listening -> reconnect. No kill. No 2FA.
- Target port dark -> stop 4001 and 4002, IBC that door. Live can prompt the phone.
- Two simultaneous Gateways need a second IBC + `IbDir`. Not shipped.

## Why this approach

Reconnect-only when the door is already up keeps fast flips. Killing only the dark target port left paper running, so IBC never opened a cold live login. Dual-process from one `StartGateway.bat` was a false promise.

## Verification

pytest on `test_gateway_mode_switch.py`, `test_launch_gateway.py`, `test_mode_identity.py`. Then recycle API and POST live (operator 2FA).

## Follow-ups

Do not claim two Gateways from one IBC. Do not blank `IbPassword`. Do not treat 4001 LISTEN as live.

## Keywords

Live, 2FA, IBC, start_ibc, force_restart, 4001, 4002
