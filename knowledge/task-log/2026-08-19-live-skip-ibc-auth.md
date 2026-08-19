# 2026-08-19 -- Live click skips IBC so 2FA can show

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** `CHANGELOG.md` 2026-08-19 Live click skipped IBC · `PROBLEM_LOG.md` 2026-08-19 IBC auto-login hid 2FA

## Task

Explain why Live never showed a lasting auth prompt, and record those IBC steps on the door trail. Make the next Live click show Gateway login.

## Goal

Operator can see Live login / 2FA. Trail shows clicked-Log-In vs Simulated Trading vs attach/refuse.

## Why it mattered

The operator thought Live failed because they never authenticated. IBC had already clicked Log In and finished Simulated Trading in a few seconds.

## What we changed

- Live `force_restart` starts `ibgateway.exe`, not IBC
- `ibc_log_harvest.py` parses IBC logs into trail events (no passwords)
- Harvest after an IBC paper launch

## How it works now

Paper click still IBC auto-login. Live click leaves the Gateway login window up. Trail `actor=ibc` explains auto-login when IBC was used.

## Why this approach

Clearing IBC credentials would break morning paper start. Skipping IBC only on an explicit Live door change is the smallest way to show auth.

## Verification

pytest harvest + launch_gateway live-skips-IBC.

## Follow-ups

Manual Live click after API restart: confirm login window, complete live, Client 17 green.

## Keywords

IBC, 2FA, Live, Simulated Trading, gateway trail
