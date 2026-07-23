# 2026-07-23 — Daily auto-start for Gateway + Nova API/UI

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops / ops tooling
- **Related:** `CHANGELOG.md` §2026-07-23 — Daily auto-start · `docs/ibc-gateway-setup.md`

## Task

Create a script so Nova (API + frontend) and IB Gateway start automatically at computer logon or at 6am, without daily manual clicks.

## Goal

One installable Windows Scheduled Task that launches IBC Gateway (when configured) plus Nova API/UI, safely if already running.

## Why it mattered

Manual `Run Nova.bat` + Gateway login every morning is friction; empty scanners when Gateway is down look like “no gaps.”

## What we changed

- `scripts/Start-NovaDaily.ps1` — idempotent bootstrap (Gateway → API → UI → browser), logs to `backend/logs/daily-start.log`
- `scripts/Install-NovaDailyTask.ps1` — register/unregister task (`Daily` / `AtLogon` / `Both`, default Both @ 06:00)
- `Start Nova Daily.bat` — one-click manual run
- Docs section in `docs/ibc-gateway-setup.md`

## How it works now

Run `.\scripts\Install-NovaDailyTask.ps1` once. At 6am and/or logon, Windows runs `Start-NovaDaily.ps1`, which skips healthy `:8000`/`:5173` and an already-running Gateway. Prefers `%USERPROFILE%\.nova\ibc\start_gateway.ps1`. Phone 2FA may still be required.

## Why this approach

- **Scheduled Task over Startup folder** — supports a clock time (6am) and AtLogon without duplicating shortcuts; easy unregister.
- **Idempotent starter** — Both triggers can fire the same morning without killing a healthy stack.
- **Reuse existing Start-NovaApi/Ui + IBC paths** — no second launch story; credentials stay out of git.
- **Rejected:** silent auto-login without IBC (unsafe / not supported); forcing Gateway restart every run (disruptive mid-session).

## Verification

- Scripts added; IBC launcher/config already present under `%USERPROFILE%\.nova\ibc\`.
- User/agent runs `Install-NovaDailyTask.ps1` once; optional `schtasks /Run /TN NovaDailyStart` to smoke.

## Follow-ups

- Enable Windows wake timers if the PC sleeps through 6am.
- Confirm Scanner Source is IBKR in Settings (Alpaca green badges ≠ Gateway logged in).

## Keywords

scheduled task, daily start, IBC, IB Gateway, Run Nova, AtLogon, 6am, Start-NovaDaily
