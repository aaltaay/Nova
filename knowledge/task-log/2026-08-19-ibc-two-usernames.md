# 2026-08-19 -- Live vs paper IBC usernames; password field empty

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** `CHANGELOG.md` 2026-08-19 Live vs paper IBC usernames · `PROBLEM_LOG.md` Gateway password field stayed empty · ADR 013

## Task

Explain why the Gateway password box was empty, and make Live fill the live username plus password so IBKR Mobile 2FA can fire.

## Goal

IBC types the live login id and the saved password, then clicks Log In. Paper uses the paper login id.

## Why it mattered

The operator was looking at a Live login form with no password. That was our blank-password experiment, not a missing secret in IBC config. Live and paper also use different IBKR usernames.

## What we changed

- Local IBC `config.ini` keys `IbLoginIdLive` / `IbLoginIdPaper`; door click copies the matching one onto `IbLoginId`.
- Stopped blanking `IbPassword` before IBC start.
- Tests for `align_ibc_login_id` and password round-trip.

## How it works now

Same saved `IbPassword` for both doors. Live click: live username, IBC fill, Log In, phone. Paper click: paper username. Nova still refuses a paper account while Live is requested.

## Why this approach

Outside SendInput cannot reliably type into Java. IBC already fills both fields if the password is on disk. Blanking the password to delay Log In left an empty box when the waiter missed "Setting user name". Switching login id is the real live vs paper split; IBC docs treat paper credentials as simulated even when TradingMode=live.

## Verification

`py -3 -m pytest backend/tests/test_gateway_login_fill.py backend/tests/test_launch_gateway.py -q` -- 20 passed.

## Follow-ups

If Simulated Trading appears after the live username, the live password may differ from paper -- ask, do not guess. Do not commit `%USERPROFILE%\.nova\ibc\config.ini`.

## Keywords

IbLoginIdLive, IbPassword, empty password, IBC, 2FA
