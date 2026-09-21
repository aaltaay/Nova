# Live desk runbook -- sync to master, restart Gateway, arm the morning

Operator work on the trading PC. An agent can prepare this recipe but cannot
produce the evidence: the Gateway restart needs a 2FA approval and the
unattended premarket proof needs real mornings. Covers #331 and #14.

Best done on a **Sunday**, when IBKR's weekly re-authentication falls anyway, so
one 2FA approval covers both the re-auth and the restart.

## 1. Sync the desk to master

The clone that runs the desk is `C:\Users\aalta\github\Nova`. **Never assume it
is clean** -- it is also where agents and IDEs have been working.

```powershell
cd C:\Users\aalta\github\Nova
git fetch origin
git status --short
```

- **Clean?** Go straight to the checkout below.
- **Dirty?** Preserve it before anything else -- do not `git checkout --` over
  work you have not looked at (branch preservation, #369):
  ```powershell
  git switch -c wip/desk-$(Get-Date -Format yyyy-MM-dd)
  git add <the paths you want>      # explicit paths, never -A
  git commit -m "wip: desk state before sync"
  ```
- **On a feature branch whose PR already merged?** Nothing to save; its commits
  are in master already.

Then take master:

```powershell
git checkout master
git pull --ff-only origin master
```

Restart the API so the new code is live (the localhost watchdog respawns it
within ~5 s; Vite hot-reloads the UI). Confirm the desk header still shows the
venue you expect -- the venue is durable, but **every restart comes up
disarmed** by design (ADR 018). Arm at the header padlock when you want to
place.

## 2. Cold-restart IB Gateway

Do this **after** the sync, and in this order:

1. **Stop the SIM history download tool first.** Its client IDs reconnect
   aggressively and can land in the middle of a Gateway login.
2. **Upload Gateway diagnostics to IBKR support *before* restarting** if you
   still want the stuck-request state diagnosed. The `.ibgzenc` logs are
   encrypted and are the only evidence of a "another pending request" stall --
   a cold restart destroys it.
3. Cold restart through IBC and approve the IBKR Mobile 2FA prompt.
4. Optional, worth doing once: enable the IBC command server
   (`CommandServerPort`) so `ReconnectAccount.bat` becomes a soft reconnect and
   the next wedge does not need a full restart plus 2FA.

**It worked if** Nova's log shows `completed-orders cache refreshed`, there is
no `completed orders request timed out`, and the amber Desk warning clears
within about 60 seconds.

Known open risk, accepted: the trading PC is Wi-Fi only, and a Wi-Fi
re-association coincided with a Gateway 1100 disconnect on 2026-09-17. Moving
it to wired Ethernet removes that class of morning disconnect.

## 3. Arm the unattended premarket (#14)

If the API or Gateway comes up after 09:30 ET, that day's Gappers table stays
empty for the whole session by design (ADR 008 freeze) -- so every late or
manual start is a lost Gappers day.

```powershell
cd C:\Users\aalta\github\Nova
.\scripts\Install-NovaDailyTask.ps1
```

It registers `Start-NovaDaily.ps1` on a premarket trigger (default 03:40 local,
machine should be on ET), a 06:00 backstop, logon/unlock, plus
`NovaMorningCheck` at 03:55 and `NovaRepoHygiene` at 02:30. Then:

- Enable **wake timers** in Windows power settings, or the task cannot start a
  sleeping machine.
- Configure one alert channel so a failed leg is audible:
  `alerts_channels.json` in the operator cache feeds
  `POST /api/alerts/system-event`, with a direct Discord/webhook POST as the
  fallback when the API itself is down.

**Evidence that closes #14** (an agent can check these for you the next
morning):

1. A real unattended `03:55` line in `backend/logs/morning-check.log` from a run
   nobody started by hand.
2. One week with no unexpected IBC `Login attempt` other than the weekly 2FA.

Until both exist, #14 stays open no matter how the code looks.

## Related

- `scripts/Install-NovaDailyTask.ps1` · `scripts/Invoke-NovaMorningCheck.ps1`
- `architecture/decisions/018-desk-venue-vs-spend-arming.md` (venue persists, arming never does)
- `docs/paper-shadow-protocol.md` · `AGENTS.md` §8
