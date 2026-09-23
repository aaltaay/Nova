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
3. Cold restart through IBC and approve the IBKR Mobile 2FA prompt within
   three minutes (IBC drops a prompt older than its 180 s timeout).
4. Optional, worth doing once: enable the IBC command server so
   `C:\IBC\ReconnectAccount.bat` becomes a soft reconnect and the next wedge
   does not need a full restart plus 2FA. In
   `%USERPROFILE%\.nova\ibc\config.ini` set `CommandServerPort=7462` and
   `ControlFrom=127.0.0.1` (the desk's IBC log still showed
   `CommandServerPort=0` on 2026-09-23). It takes effect on the next Gateway
   start, so do it before step 3.

**It worked if** Nova's log shows `completed-orders cache refreshed`, there is
no `completed orders request timed out`, and the amber Desk warning clears
within about 60 seconds.

Known open risk, accepted: the trading PC is Wi-Fi only, and a Wi-Fi
re-association coincided with a Gateway 1100 disconnect on 2026-09-17. Moving
it to wired Ethernet removes that class of morning disconnect.

## 3. Keep Windows from restarting the desk

IB Gateway's saved login survives only Gateway's own 11:45 PM restart. **A PC
restart ends it**, and the next start needs your phone
(`docs/ibc-gateway-setup.md`, "What the saved login survives"). Worse, after a
restart Windows waits at the sign-in screen, and Nova's scheduled tasks only
run while you are signed in -- so nothing starts and nothing alerts until you
sign in.

That is what happened on 2026-09-23: Windows Update restarted the desk at 02:29
ET to install an optional preview update (KB5124010). The desk's settings made
that possible:

- **Active hours were 8 AM to 2 AM**, so Windows treated 2 AM to 8 AM --
  premarket -- as free time to restart.
- **"Get the latest updates as soon as they're available" was on**, which is
  why an optional preview update installed at all.

Change, in Settings > Windows Update (Nova does not change Windows settings for
you):

1. **Advanced options** > turn off *Get the latest updates as soon as they're
   available*.
2. **Pause updates** (up to five weeks at a time) and install them yourself on
   a weekend, then restart by hand. IBKR asks for your phone once a week at the
   weekend anyway, so a weekend restart costs no extra login.
3. **Advanced options** > turn on *Notify me when a restart is required*, so a
   pending restart is visible before it happens.

Active hours alone do not fix this: Windows caps them at 18 hours, and a
restart at any hour still costs a phone login.

To see what happened on a given night, run:

```powershell
py -3 tools\premarket_verify.py relogin
```

It prints one line: a Windows restart (who asked for it, when, and when you next
signed in), or a fresh Gateway start.

## 4. Arm the unattended premarket (#14)

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

**Evidence that closes #14:**

1. An unattended `03:55` run in `backend/logs/morning-check.log` (one nobody
   started by hand) that ended `RESULT PASS`.
2. One week with no phone login other than IBKR's weekly one at the weekend.

Check both in one command, from `C:\Users\aalta\github\Nova`:

```powershell
py -3 tools\premarket_verify.py            # text; exit 0 only when both are met
py -3 tools\premarket_verify.py --json     # the same, for an agent
```

It lists every weekday phone login and every morning the check did not run,
each with its reason -- a Windows restart and who asked for it, or a fresh
Gateway start -- read from the IBC logs, `daily-start.log` and the Windows
event log. Until it prints `RESULT MET`, #14 stays open no matter how the code
looks.

The first criterion was met on 2026-09-22 (`03:55:03 RESULT PASS`). The second
was not: in the week to 2026-09-23 the desk needed the phone on weekdays after
an unrecorded restart and an unexpected shutdown (09-21), a Start-menu restart
(09-22) and the Windows Update restart (09-23).

## Related

- `scripts/Install-NovaDailyTask.ps1` · `scripts/Invoke-NovaMorningCheck.ps1`
- `tools/premarket_verify.py` (#14 evidence, `relogin`) · `backend/ibkr/relogin_reason.py` · `backend/ibkr/windows_restarts.py`
- `architecture/decisions/018-desk-venue-vs-spend-arming.md` (venue persists, arming never does)
- `docs/paper-shadow-protocol.md` · `AGENTS.md` §8
