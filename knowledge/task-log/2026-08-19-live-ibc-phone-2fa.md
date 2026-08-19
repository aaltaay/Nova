# 2026-08-19 -- Live IBC fills login; phone 2FA is IBKR's job

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** `CHANGELOG.md` 2026-08-19 Live IBC fills login · `PROBLEM_LOG.md` 2026-08-19 Live 2FA vs AutoRestart · ADR 013

## Task

Keep IBC autofill for username/password on Live, and make IBKR send an IBKR Mobile prompt instead of finishing login with no phone code.

## Goal

Live click starts IBC (not a blank Gateway exe). Local IBC AutoRestart is cleared for that door so a live login can require 2FA. Paper keeps the week-long token.

## Why it mattered

Skipping IBC blocked autofill, which was required. IBC never sends the phone code; AutoRestart was why IBKR often did not either.

## What we changed

- Live `force_restart` uses IBC again
- `_align_ibc_trading_mode("live")` writes AutoLogoff and clears AutoRestart
- Paper align restores `AutoRestartTime=11:45 PM`
- Docs / ADR 013 / login-warning MDC: Nova cannot send IBKR Mobile

## How it works now

IBC types credentials and clicks Log In. You approve IBKR Mobile. Trail `ibc_second_factor` vs `ibc_simulated_trading` says whether IBKR asked. If IBC still opens Simulated Trading, that is still a paper session -- Nova will refuse Live attach.

## Why this approach

Rejected blank-login exe (no autofill). Rejected hoping IBC can push 2FA (it cannot). Clearing AutoRestart on Live is the IBC-documented way to stop the week-long skip-2FA token without deleting Gateway files.

## Verification

pytest `test_launch_gateway.py` (force live uses IBC; align live clears AutoRestart).

## Follow-ups

Manual Live click: phone prompt, then `broker_account_kind=live`. If Simulated Trading still appears, that is IBC/Gateway live-radio, not missing autofill.

## Keywords

IBC, 2FA, IBKR Mobile, AutoRestart, Live, autofill
