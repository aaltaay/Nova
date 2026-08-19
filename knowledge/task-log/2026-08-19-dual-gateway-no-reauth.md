# 2026-08-19 -- Dual Gateway Paper/Live without re-auth

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** `CHANGELOG.md` 2026-08-19 Paper/Live keeps both Gateways · `PROBLEM_LOG.md` Paper/Live killed the other session · ADR 013

## Task

Switch Paper/Live on the fly without closing the other Gateway or asking for live 2FA every time.

## Goal

If live is already logged in on 4001, a Live click only reconnects. Same for paper on 4002. First login of a door may still 2FA. The other door stays up.

## Why it mattered

Nova was killing both listeners on every opposite-door click. That felt like an IBKR rule. It was a Nova choice, and it made fast flips impossible.

## What we changed

- `switch_plan`: `noop` / `reconnect` / `start_ibc` / `replace_target`
- Launch no longer stops both ports or every Gateway window
- Intentional heal no longer expires into follow-Gateway while the other port is up

## How it works now

One Gateway process is still one account. Fast flipping keeps two processes. Nova has one IB socket, so it dials one port at a time without logging the other out.

## Why this approach

Two running Gateways is the only way to avoid re-auth. Clearing AutoRestart on a single process still logs you out of the other account. Rejected: keep killing on every flip.

## Verification

pytest `test_mode_identity.py` `test_launch_gateway.py` `test_gateway_mode_switch.py` `test_gateway_heal.py`

## Follow-ups

Two Gateways sharing `C:\Jts` can still fight on a cold second start. If the second window fails, split `IbDir`. First Live login of the day can still 2FA.

## Keywords

dual Gateway, Paper, Live, 2FA, reconnect, ADR 013
