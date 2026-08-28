# 2026-08-28 -- Morning API soak: refreshes were Vite, API process never died

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** `CHANGELOG.md` 2026-08-28 Daily / Run Nova API starts stable · `PROBLEM_LOG.md` 2026-08-28 Desk refreshed and Start API appeared · `DEFERRED_LOG.md` D-006

## Task

Soak the desk after the operator saw a few self-refreshes and thought the API had stopped. Same class as prior API_WEDGED / reload mornings.

## Goal

Say whether the API is actually dead, keep today's Gappers, and stop the launcher from starting WatchFiles-on again.

## Why it mattered

A false "API stopped" plus a Start API click kills a live clientId 17 process. After 09:30, that also throws away the session Gappers roster.

## What we changed

- `scripts/Start-NovaApi.ps1`: default `NOVA_API_RELOAD=0`; `-Reload` opt-in only
- `scripts/Start-NovaDaily.ps1`: `HealthWaitSec` default 180 (was 60)
- `.cursor/rules/run-app.mdc`: stop telling agents to start uvicorn `--reload`
- `tools/test_start_nova_api_script.py`: asserts the default path is reload-off
- Did **not** restart pid 16820 (reload=true until the next start)

## How it works now

The 08:22 process (`86bbb510002d` / pid 16820) is the only API. IB is live/ready. Gappers 16 live, Gainers 50 live. Yahoo sockets ~125 and stable (not the 2026-08-26 pile-up). HTTP lag can spike past 4s while `snapshot_quotes` is cold-inflight, so the header can paint Start API while Desk is green. That is a probe miss. Do not click Start API or Reload backend.

The 09:11 refreshes were Vite HMR (`ui-console.log`), not WatchFiles. There were no `WatchFiles` / second `Started server process` lines today.

## Why this approach

Restarting now would drop L1 and, after 09:30, make today's Gappers unrecoverable (ADR 008). Editing `app_lifespan.py` to move `init_sentry` after `yield` would WatchFiles-kill this reload=true process. So the live PID stays, the launcher is fixed for the next start, and the 94s HTTP-dark startup is D-006.

Rejected: killing :8000 to "fix" the red Start API chip (that is the 2026-08-14 auto-heal mistake). Rejected: leaving `NOVA_API_RELOAD=1` as the daily default.

## Verification

- T0 09:14:22 / T1 09:16:02 / T2 09:20:02: same instance, listen=true, IB ready, 16/50 rows
- Browser 09:20: Desk up, Live, 16 Gappers / 50 Gainers, HOD LIVE. Start API appeared after a Gainers click; `/api/health` then missed 4s and answered in 3689ms; `http_loop_lag_ms.max_ms=4360.6`, `wedged=false`
- `py -3 -m pytest tools/test_start_nova_api_script.py backend/tests/test_scripts_ascii.py -q` -- 6 passed

## Follow-ups

- D-006: do not block `yield` on Sentry / cache restore
- After a no-reload start (not today): confirm `/api/health` `reload=false`
- Do not click Start API while Desk is green

## Keywords

soak, NOVA_API_RELOAD, Start-NovaApi, Vite HMR, Start API, API_WEDGED, init_sentry, snapshot_quotes, gappers freeze
