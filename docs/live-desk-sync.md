# Live desk runbook -- sync to master, restart Gateway, arm the morning

Operator work on the trading PC. An agent can prepare this recipe but cannot
produce the evidence: the Gateway restart needs a 2FA approval and the
unattended premarket proof needs real mornings. Covers #331 and #14. Section 5
prepares the Gateway minimum-version switch, and the PAUSE trial in section 3 is
the planned-restart half of #14.

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

From the installed desk you can skip the terminal when the checkout is already
a clean `master` (ADR 038 amendment). While the window title reads
`backend vNNN (older -- ...)`, the notice under the header offers **Restart
backend now**, or **Pull master and restart**. Either one first lists anything
a restart would interrupt: recordings, positions, working orders, the bot's
trade. A dirty checkout, another branch, or a master that changes
`backend/requirements.txt` is refused with the reason; use the steps above
then.

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

### Planned restart: IBC PAUSE (untested on Windows -- trial it off hours)

A restart you choose (a Windows update you installed on purpose, a driver) could
keep the Gateway's login if IBC is told to `PAUSE` first. IBC 3.24.0 added it;
the desk has **never run it**, so until the trial below passes, a planned restart
still costs the phone login and nothing in this runbook relies on PAUSE.

What IBC's guide (`C:\IBC\userguide.pdf`, "PAUSE", pp. 14-15) says it does:

- It shuts the Gateway down tidily, like `STOP`, but keeps the current login so
  that the next IBC start **resumes the session without a login**.
- A Gateway has no File > Restart menu, so IBC has to write that login file at
  the end of the current minute (the next minute, if this one ends imminently).
  The Gateway process therefore exits **up to about 75 seconds** after the
  command, not at once.
- It **cannot cross the weekly reset.** The saved login is invalidated at the
  start of the next week, and IBKR's Gateway reset is reported as Sunday 01:00
  ET. Use PAUSE Monday to Friday; a restart across Sunday needs the phone.
- After a PAUSE, IBC's start loop deletes its `PAUSE<session>` marker in
  `C:\Jts`, prints `IBC is paused` and **exits instead of relaunching** the
  Gateway. The next IBC start looks for the login file at
  `C:\Jts\<user folder>\autorestart` -- the same file the 11:45 PM self-restart
  uses.

How it is sent, and what is missing on this PC (read-only check, 2026-10-09):

- `C:\IBC\Pause.bat` calls `SendCommand.bat PAUSE`, which opens a **telnet**
  session to `127.0.0.1:7462` and types the command into it with
  `Scripts\SendIBCCommand.vbs`.
- The command server is on: `%USERPROFILE%\.nova\ibc\config.ini` has
  `CommandServerPort=7462`, `ControlFrom=127.0.0.1`, `BindAddress=127.0.0.1`, and
  port 7462 listens on 127.0.0.1 (owned by the Gateway's java process). Only this
  machine can reach it, and any program on this machine can send it `STOP`, so
  treat the port as part of the desk's attack surface.
- **`telnet.exe` is not installed**, so `Pause.bat` fails as it stands. Turn on
  the Windows *Telnet Client* optional feature for the trial (Settings > System >
  Optional features > More Windows features), or write and test a small TCP
  sender during the trial. Do not improvise one on the day.
- `SendCommand.bat` finds its `.vbs` by a relative path, so run it from `C:\IBC`
  (`cd C:\IBC` first).
- **Never send PAUSE, STOP or RESTART to the desk while it is trading, and agents
  never send them at all.** They end the Gateway session the same way.

Trial, off hours, phone in hand (a failed trial costs one ordinary phone login):

1. Monday to Friday after 20:00 ET and well before the 11:45 PM self-restart, no
   position, recordings and the Sim download tool stopped. Note the time.
2. `cd C:\IBC`, then `Pause.bat`. Wait at least 90 seconds. **Success looks like:**
   the Gateway window closes and port 4001 stops listening; Nova shows the
   Gateway as down. If the Gateway is still up after 2 minutes, stop and report.
3. Start the Gateway again **without restarting Windows** (Nova's "Open live",
   or `start_gateway.ps1`) after about 2 minutes. Do **not** use "Start fresh
   login": it clears the `Restart=OK` marker in `jts.ini` that the resume needs.
   **Resumed without the phone** when the new IBC log shows
   `autorestart file found at C:\Jts\...\autorestart: authentication will not be
   required` and no `Second Factor Authentication` dialog; `py -3
   tools\premarket_verify.py relogin` then reads it as a saved login.
4. Repeat the real case: PAUSE, then restart Windows, sign in, and let the
   AtLogon task start the Gateway (section 4). Record how long a gap the saved
   login survived. Try a long one (an hour or more) only after a short one works.
5. Whether Nova's own helpers interfere is part of the trial: does anything
   relaunch the Gateway before the Windows restart, and does `premarket_verify`
   count the resumed start as a quiet one for #14? Write the answers on #14.

Until all of that has been seen once, a failed resume is the expected, safe
outcome: the login window opens and you approve your phone.

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
- Check what the trading path runs at (read-only):
  `powershell -ExecutionPolicy Bypass -File scripts\Repair-NovaPriority.ps1`.
  Every Nova task states its priority: 4 (Normal) for `NovaDailyStart`,
  `NovaMorningCheck` and `NovaLocalhostWatchdog`, 7 (below normal, on purpose)
  for `NovaRepoHygiene`. A task registered before 2026-10-01 has Task
  Scheduler's default, 7: BelowNormal CPU, Low I/O and memory priority 2, which
  IBC, the Gateway, the API and Vite inherit. Re-register it (above, and
  `scripts\Register-NovaLocalhostWatchdog.ps1`); that stops and restarts
  nothing. A process already running keeps its priority, and the IBC loop
  relaunches every Gateway at its own, so raise them in place with the same
  script and `-Apply`: nothing restarts and the Gateway keeps its login. Outside
  04:00-20:00 ET.
- The hidden tasks (`NovaLocalhostWatchdog`, `NovaRepoHygiene`) run PowerShell
  under `conhost.exe --headless`, which has no window. Registered before the
  2026-10-01 fix, they ran `powershell.exe -WindowStyle Hidden`, which hides its
  console only after it has drawn: the watchdog's 5-minute kick flashed a black
  Windows Terminal window every time. Re-register them (the two scripts above);
  that stops and restarts nothing.
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

**Proof availability (#742).** The report must distinguish a readable source
with no login events from a missing, unreadable or partly read source. A quiet
week needs both the retained `daily-start.log` and IBC logs: successful reads,
dated observations reaching the requested window's start, and observations on
each completed calendar day in that window. It also needs a successful Windows
restart query covering that window. An empty successful restart query is known
evidence; an empty login file supplies no dated history. A source's oldest
timestamp alone does not establish the week's coverage.

The report shows each source's read status, retained timestamp range, observed
dates and any gaps. Missing files, failed reads (including one failed IBC file),
short retained history and unsupported or unreadable Windows evidence leave the
quiet-week criterion **unknown / OPEN**, even if zero logins were observed. A
window shorter than one week cannot establish #14's week. This is a verdict on
the retained observations, not a guarantee of continuous monitoring or evidence
that an unrecorded login never happened.

A recognized IBC startup banner with a missing, truncated or invalid date/time
makes that source partial. Later undated authentication evidence cannot borrow
an older startup's timestamp to establish a quiet week; the report remains
unknown / OPEN rather than guessing when that startup occurred.

Each valid startup banner supports only that startup's first authentication
record. A later authentication record needs a fresh valid banner or a valid
dated IBC line following it. A record still awaiting a dated line when another
startup begins is partial evidence, even when a previous banner is readable:
the diagnostic parser's retained fallback cannot certify the record's date.
An unused banner also stops dating authentication once the recorded IBC history
moves to another calendar date. Timestamp-rejected records stay unknown and do
not create a weekday login, count or known failure. Genuinely dated unexpected
records still establish failure even when another record or source is partial.
The verifier's pure `tools/premarket_ibc.py` parser returns those records and
their source problems together; the operator's diagnostic parser is unchanged.

### Authentication boundary completeness (#742 review)

Every observed IBC startup must include an authentication outcome. A valid banner
followed by another startup or EOF without that outcome is partial evidence,
even when the other retained dates cover the requested window. A dated line
earlier than its pending startup contradicts lineage: retain the authentication
timestamp as unknown, report the problem, and exclude it from weekday counts.
This does not change the one-unattended-PASS acceptance criterion.

The unattended-PASS criterion is evaluated separately. Missed mornings remain
context: they do not themselves add another closing criterion or require every
morning to pass. One genuine unattended PASS plus adequate evidence of a quiet
week still meets the same two criteria. Fixing this verifier does not close #14
or produce the trading PC's proof.

The first criterion was met on 2026-09-22 (`03:55:03 RESULT PASS`). The second
was not: in the week to 2026-09-23 the desk needed the phone on weekdays after
an unrecorded restart and an unexpected shutdown (09-21), a Start-menu restart
(09-22) and the Windows Update restart (09-23).

## 5. Switching the Gateway build (`TWS_MAJOR_VRSN`) -- rehearsal checklist

IBKR has said Gateway builds older than **10.50.1** are being desupported. The
login notice on build 10.39.1, quoted in Lean's Interactive Brokers brokerage
issue #271 (2026-10-06), says "desupported on 20261215" and names 1050.1 as the
minimum. That is second-hand: nobody has reported what the notice says on 10.45,
and the desk's own logs cannot show it (see below). Plan on **2026-12-15** as the
date the desk must be on 10.50.1 or later, and on 10.45 as a rollback that ends
then. This section is the repeatable checklist for a build switch and its
rollback; it is operator-timed, and an agent never edits the launcher, restarts
the Gateway or approves the phone prompt (never automate the second factor).

### Where the desk stands (read-only check, 2026-10-09)

The desk has **already been on 10.51 since 2026-10-06**, so the first rehearsal
happened without a written checklist; the checklist below is the one to follow
the next time, and the section after it says what that history does and does not
prove.

| Piece | State |
|---|---|
| Launcher `%USERPROFILE%\.nova\ibc\StartGateway.bat` | `TWS_MAJOR_VRSN=1051`, rewritten 2026-10-06 00:33 (with `start_gateway.ps1`) |
| Running Gateway | build **10.51.1b** (Sep 29, 2026), process started by its own 11:45 PM restart on 2026-10-08, API on port 4001 |
| IBC | **3.24.2**; first IBC log 2026-10-06 21:54 (`IBC-3.24.2_GATEWAY-1051_*`) |
| Rollback target | `C:\Jts\ibgateway\1045`, build **10.45.1h** (Jun 24, 2026), last started 2026-10-05, install kept |
| Stock `C:\IBC\StartGateway.bat` | still `1045`, but unused: it is the zip's own file |

### The notice search (step 1 of the preparation)

On 2026-10-09 I searched, read-only, the 50 text files under `C:\Jts` (the
launcher logs of both builds, both `jts.ini` files, `xmlopt.dat`) and all ten IBC
logs under `%USERPROFILE%\.nova\ibc\Logs` (2026-08-15 to 2026-10-09, Gateway
10.45.1h and 10.51.1b) for desupport, minimum version, "no longer supported",
upgrade or update required, `1050.1` and `20261215`. **Nothing matched.** That is
weak evidence, not an all-clear:

- IBC records only the **titles** of the windows it sees, never their text. The
  titles over those weeks were the second-factor prompt, *Existing session
  detected*, *Re-login is required*, *Restart in progress*, *Shutdown progress*,
  *Pending Tasks*, *API User Connections*, the account Configuration dialog, the
  main *IBKR Gateway* frame and a *Gateway* dialog -- none of them a notice.
- The Gateway's own logs (31 `.ibgzenc` files) are encrypted, so nothing here can
  read them.
- A message IBKR draws on the login screen would therefore leave no trace in
  either place, and 10.45 has not been started since 2026-10-05.

So the question stays open: **the next time any Gateway login window shows a
notice, read it and put its words on #14.** (One line in the 10.51 launcher log,
`initNSMsgVersionLimits: minVersion=51, maxVersion=52`, is a login-protocol
range, not a desupport signal.)

### What the 10.51 history proves, and what it does not

Proven by the IBC logs and the process list (IBC 3.24.2 + Gateway 10.51):

- A full login with the phone prompt (2026-10-07 08:10), the `TWS API socket port
  is already set to 4001` / `Configuration tasks completed` steps, and two
  consecutive 11:45 PM self-restarts (2026-10-07, 2026-10-08) that resumed on the
  saved login with no phone (`autorestart file found ... authentication will not
  be required`). Port 4001 listens and Nova is connected.
- Nova's IBC-log readers (`relogin_reason`, `premarket_ibc`, the log harvest) read
  the new file names and the 3.24.2 banner; `premarket_verify.py relogin` ran
  clean on them.

**Not** proven, and what each item below checks: the 10.45 API-settings reset
(only the *port* is logged, not the localhost-only box), the 10.48 open-orders
change (no de-activated order has been seen), IBC 3.24.2 on any build other than
10.51.1b, and the rollback to 10.45.

### Checklist

Do it on a **Sunday**, when the weekly re-auth falls anyway (top of this
runbook), with the phone in hand. The switch ends the Gateway process, so it
costs one phone login; the prompt is approved by you, within three minutes.

**A. Before you touch anything**

- [ ] Flat, no working orders you care about, recordings stopped, the SIM history
      download tool stopped (section 2, step 1). Upload Gateway diagnostics to
      IBKR support first if you still want a stall diagnosed (step 2).
- [ ] Note the current state: `findstr TWS_MAJOR_VRSN %USERPROFILE%\.nova\ibc\StartGateway.bat`,
      the running build (`findstr "Build 10." C:\Jts\launcher.log`) and `dir C:\Jts\ibgateway`.
- [ ] Back up the shared settings: `copy C:\Jts\jts.ini C:\Jts\jts.ini.before-<ver>`.
      The Gateway reads and rewrites `C:\Jts\jts.ini` (the copy inside
      `ibgateway\1045` is stale since 2026-10-03), and the 10.45 reset note in D
      is why a copy matters.
- [ ] The target build is installed under `C:\Jts\ibgateway\<ver>\` with its
      `ibgateway1.exe` (or `ibgateway.exe`); IBC finds the Gateway by that folder
      number alone.

**B. Switch** (operator)

- [ ] Stop the Gateway the way you already do (close it; do not kill IBC's
      window mid-login), then edit `TWS_MAJOR_VRSN` in
      `%USERPROFILE%\.nova\ibc\StartGateway.bat`. The `v1051` text in
      `start_gateway.ps1` is only a label. Leave the stock `C:\IBC\StartGateway.bat` alone.
- [ ] Start through Nova's "Open live" or `start_gateway.ps1` (not raw
      `ibgateway.exe`, which leaves the login empty) and approve IBKR Mobile.

**C. IBC 3.24.2 compatibility** -- the new IBC log
(`IBC-3.24.2_GATEWAY-<ver>_<DAY>.txt`) must show, in order:

- [ ] `Starting IBC version 3.24.2`, then `Login attempt: 1` and `Click button: Log In`.
- [ ] `Second Factor Authentication initiated`, then that dialog `Closed` after
      your approval, and no `Re-login is required` / `timed out` line.
- [ ] `TWS API socket port is already set to 4001` and `Configuration tasks completed`.
- [ ] **No window title you have not seen** in the list under "The notice search".
      A new dialog that IBC does not know sits waiting on the desk; look at the
      Gateway window itself on the first login of every new build, and read any
      notice aloud into #14.
- [ ] **The first 11:45 PM restart on the new build** logs `autorestart file found
      ... authentication will not be required` and needs no phone. This, not the
      first login, is the real test of the saved login on the new build.
- [ ] If IBC 3.24.2 cannot drive the new build, there is no newer IBC: roll back
      (section F). Do not patch IBC's jar.

**D. API socket and localhost settings** -- IBKR's 10.45 notes say an upgrade
**resets "Enable ActiveX and Socket Clients" and the localhost-only setting**.
In the Gateway window: Configure > Settings > API > Settings.

- [ ] *Enable ActiveX and Socket Clients* is ticked (port 4001 listening is
      evidence it is on, but read the box).
- [ ] *Socket port* is 4001 (`OverrideTwsApiPort=4001`; IBC logs the port, nothing
      more) and *Read-Only API* is off. `GET /api/ibkr/status` should say
      `connected: true`, `gateway_read_only: false`.
- [ ] *Allow connections from localhost only* -- **decide it on purpose.** Nova
      only ever dials `127.0.0.1`, so ticking it costs nothing. Read the box in
      the window; do not infer it from which address the port listens on. It
      matters more here because `config.ini` has
      `AcceptIncomingConnectionAction=accept`, which makes IBC click *Accept* for
      any client that is not in Trusted IPs.
- [ ] *Trusted IPs* still contains `127.0.0.1` and nothing else you do not know.
- [ ] `.\scripts\smoke_check.ps1` passes, and `completed-orders cache refreshed`
      appears in Nova's log (section 2, "It worked if").

**E. Open orders (the 10.48 `reqOpenOrders` change)** -- "What 10.48 does to the
open-orders view", below, says what the code does. After the first login on the
new build:

- [ ] On the **Live** venue (a Paper tab reads Nova's own ledger, not the broker),
      the Working Orders and Closed Orders panels agree with IBKR's own order list
      (phone app or TWS), including any greyed *Inactive* orders.
- [ ] Read the statuses the Gateway actually sends. With Nova connected, run this
      from the repo under a client id Nova does not use (Nova is 17, or
      `IBKR_CLIENT_ID`). It places nothing:

```python
from ib_async import IB, OrderStatus, StartupFetch

ib = IB()
ib.connect("127.0.0.1", 4001, clientId=90, timeout=15, fetchFields=StartupFetch(0))
for t in ib.reqAllOpenOrders():
    print(t.order.clientId, t.order.orderId, t.order.permId, t.orderStatus.status)
print("known:", sorted(OrderStatus.DoneStates | OrderStatus.ActiveStates))
ib.disconnect()
```

- [ ] Every printed status is in the `known:` list. `Inactive` is fine (below). **Any
      other word stops the switch** until the callers of `ib.openTrades()` are
      checked. Write the statuses you saw on #14.
- [ ] **Empty output is not a pass.** Nova asks with `reqOpenOrders` as client 17;
      this probe asks `reqAllOpenOrders` as client 90, and the 10.48 note names
      only the first. If the account holds no de-activated order there is nothing
      to see and the status word stays unconfirmed: leave this item open on #14,
      and treat a Working Orders row that no live order explains as the signal.

**F. Rollback to 10.45** (works only while IBKR still allows 10.45; the notice
date is 2026-12-15, and 10.45 is below its 1050.1 minimum, so this is a stopgap)

- [ ] Close the Gateway; put `TWS_MAJOR_VRSN=1045` back in
      `%USERPROFILE%\.nova\ibc\StartGateway.bat`.
- [ ] 3.24.2 has never driven 10.45; the proven pair is **3.24.1 + 10.45**. To
      restore it, with the Gateway closed: rename `C:\IBC` to `C:\IBC-3.24.2` and
      `C:\IBC-3.24.1-old` to `C:\IBC`. (3.24.2 stays in `%USERPROFILE%\.nova\ibc\releases`.)
      `config.ini` is not in `C:\IBC` and needs no change.
- [ ] Restore `C:\Jts\jts.ini.before-<ver>` only if the API settings (section D)
      regressed; the login files in `C:\Jts` are shared by both builds.
- [ ] Start through Nova, approve the phone, repeat C, D and E, and put the reason
      on #14.

### What 10.48 does to the open-orders view

Read from the code (pinned `ib_async` commit `c9f4c14`), **not** exercised against
a Gateway that holds a de-activated order -- none was available:

- ib_async creates a `Trade` for every `openOrder` the Gateway sends, with
  whatever status it gives. Nova asks once, at connect, with `reqOpenOrders`
  (`StartupFetch.ORDERS_OPEN`, see `backend/ibkr/client_connect.py`); it never
  calls `reqAllOpenOrders`. That request is per API client, so the new rows are
  orders that **client 17 placed** and IBKR has since de-activated, not other
  clients' orders.
- `ib.openTrades()` drops every trade whose status is in `OrderStatus.DoneStates`
  = `{Filled, Cancelled, ApiCancelled, Inactive}`. A de-activated order reported
  as `Inactive` is therefore **not** a working order: it is absent from
  `ibkr.orders.open_orders()` (the Working Orders panel, cancel-all and the kill
  switch's reads), `live_book.open_rows`, `execution/live_cancel.py` and the
  restart check -- and from the `working_ids` that `execution/startup_sweep.py`
  builds, so the sweep cannot keep a row `still_working` because of it.
- It **is** in `ib.trades()`, and `Inactive` is in `IBKR_CLOSED_ORDER_STATUSES`, so
  it appears under Closed Orders (`orders.closed_orders`). New rows there that
  you did not expect are this, not a bug.
- In the sweep, a ledger row whose order id the Gateway lists as `Inactive` is
  closed `failed` with `SWEEP_UNRESOLVED` ("broker reports Inactive"). That is
  the right word for an order the broker rejected or de-activated. The sweep
  looks at the terminal row **before** executions, so an order that went
  `Inactive` after a partial fill also reads `failed`; that predates 10.48.
- **Where it could be misread: a status that is not `Inactive`.** If 10.48 sends
  de-activated orders under any other word, ib_async counts them as open. They
  would show as working orders, the sweep would hold their ledger rows at
  `still_working` indefinitely, cancel-all, the kill switch and flatten would try
  to cancel them, and the restart check would say IBKR keeps them working.
  Checklist step E reads the real word.
- The sweep and `live_book.order_state` match on the bare order id, not
  `(clientId, orderId)`. That is safe while every row came from client 17, which
  is the case unless `IBKR_CLIENT_ID` was changed between two runs.

### Places that still name 1045

The desk runs 1051; these only matter if the IBC launcher is missing or the
Gateway is rolled back, and none was changed here (this change is documents only;
the follow-up is #804, which also covers an unknown order status counting as open):
`backend/constants_ibkr.py` (`IBKR_GATEWAY_EXE_DEFAULT`, the first
`IBKR_JTS_INI_PATHS` entry, whose file is stale since 2026-10-03; the live
`C:\Jts\jts.ini` is the second and is still cleared), `scripts/Start-NovaDaily.ps1`
(the raw-exe fallback), `scripts/start_gateway_ibc.ps1.example` and
`.cursor/rules/ibkr-gateway-login-warning.mdc`.

## Related

- `scripts/Install-NovaDailyTask.ps1` · `scripts/Invoke-NovaMorningCheck.ps1`
- `scripts/Repair-NovaPriority.ps1` (what the trading path runs at; `-Apply` raises it in place) · `scripts/NovaProcessPriority.ps1` · `backend/process_priority/`
- `tools/premarket_verify.py` (#14 evidence, `relogin`) · `backend/ibkr/relogin_reason.py` · `backend/ibkr/windows_restarts.py`
- `architecture/decisions/018-desk-venue-vs-spend-arming.md` (venue persists, arming never does)
- `docs/paper-shadow-protocol.md` · `AGENTS.md` §8
