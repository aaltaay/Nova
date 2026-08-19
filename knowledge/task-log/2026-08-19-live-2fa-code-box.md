# 2026-08-19 -- Live leaves Login so the 2FA code box can appear

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** PROBLEM_LOG 2026-08-19 2FA code box vs IBC click-through

## Task

Operator never saw the Gateway panel where you type the authentication code. Try Live again so that panel can show.

## Goal

Live restart does not let IBC click Log In into Simulated Trading. Login window stays. Operator clicks Live Trading then Log In; window becomes SECOND FACTOR AUTHENTICATION.

## Why it mattered

Farms green + Client 17 red is a finished paper session. IBC source: paper does not use 2FA. Live 1016+ puts the code box in the same Login frame after it retitles.

## What we changed

- Live `force_restart` starts `ibgateway.exe` (no IBC)
- Clears `Restart=OK` in local `jts.ini`
- Paper still IBC

## How it works now

Look at the desktop Login window. Click **Live Trading**, then **Log In**. Type the code when the title becomes SECOND FACTOR AUTHENTICATION. Nova still refuses paper.

## Why this approach

IBC always clicks Log In after filling the password. That is incompatible with a code box. Autofill can return after the 2FA path works.

## Verification

pytest `test_launch_gateway.py` (14 passed). Manual Live launch after API restart.

## Follow-ups

If Login never appears, Gateway may still be restoring a session; check `Restart=` in `jts.ini`.

## Keywords

2FA, SECOND FACTOR AUTHENTICATION, IBC, Login, Restart=OK
