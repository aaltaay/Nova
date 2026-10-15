# Data schema: Desk operations: diagnostics, data folders, updates, issues, small desk features

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/diagnostics/, backend/issue_report/, backend/request_guard/, frontend/electron/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## Desk diagnostics (ADR 021)

`GET /api/diagnostics` (owner `backend/diagnostics/`) answers `schema_version: 1`,
`generated_at`, `groups: [{id, title}]` (process, integrations, gateway,
market_data, recorder, practice, frontend), `counts: {ok, warn, fail, off,
unknown}`, `process: {pid, instance_id, release_tag, repo_root, env_file}` and
`rows[]`, each `{id, group, title, state: "ok"|"warn"|"fail"|"off"|"unknown",
detail, cause, fix, since: number | null, action: {kind, label} | null,
evidence: object}`. `action.kind` is one of `reconnect_ibkr | launch_gateway |
reload_backend | refresh` -- only actions that exist today. An `unknown` row
always says why. `?ui=vNNN` lets the page report its revision for the
`frontend_revision` row. `GET /api/diagnostics/bundle` is the same checklist
as plain text. Rows judge from raw facts (`evidence`); no secret value is ever
included, only presence and the file it was read from. `/api/ibkr/status`
gains `attach: {attempts_in_window, window_sec, max_attempts_per_window,
backoff_sec, last_attempt, next_delay_sec, human_step: string | null,
human_step_poll_sec, cleared_at, cleared_reason, recent[]}` from
`ibkr/attach_retry.py` (bounded attach retry: 1, 2, 5, 10, 30 s, at most 5 per
10 min, then a stated human step).

**A Gateway that refuses its API port while logged in restarts itself** (operator,
2026-10-02: "Shouldn't this be fully auto-healed?"). After a 30-minute Wi-Fi drop that
day the Gateway was logged in, both farms ON, port 4001 LISTENING, and refused every
connection; Nova said "finish the login" and waited. Owner `ibkr/gateway_api_heal.py`:
when the dialer's connects are refused without a break for `IBKR_GATEWAY_API_STUCK_SEC`
(120 s) while that port is LISTENING, a Gateway process runs and the internet answers,
Nova sends IBC's `RESTART` -- the Gateway restarts on its saved login, no 2FA (IBC
user guide) -- at most once per `IBKR_GATEWAY_API_HEAL_COOLDOWN_SEC`. IBC takes commands
only with its command server on: Nova sets `CommandServerPort=7462`, `ControlFrom` and
`BindAddress` `127.0.0.1` in `~/.nova/ibc/config.ini` (on every launch and before a
restart), which IBC reads at the Gateway's next start. `/api/ibkr/status` adds
`gateway_api_heal: {state: "ok" | "wait" | "not_listening" | "no_gateway" |
"no_internet" | "cooldown" | "restart" | "restart_failed", text, since, last_restart:
{at, ok, error} | null, refused_since}`, and the checklist adds the `gateway_api_stuck`
row while it is not `ok`. **One Gateway at a time**: the launcher's process check
(`ibkr/gateway_process.py`) matches `ibgateway1.exe` -- Gateway 10.45's name, which the
old `Get-Process -Name ibgateway` never matched, so at 12:46 that day Nova started a
second Gateway beside the running one and it took over the IBKR login. `ibkr/session_errors.last_error()` is
`{code, message, ts} | null` for the last IB errorEvent of any code.

**Pages and names the API refused** (#828 item 1). A refused socket shows in a
browser only as close code 1006, so the `process` group carries the
`api_refusals` row, read from the request guard's memory
(`request_guard/recent_refusals.py`). `ok` "Nothing refused since the API
started"; `warn` while the latest refusal is under `REFUSAL_DIAG_RECENT_SEC`
(15 min) old, its detail counting the refused values per header and kind, most
recent first, as `N <page origin(s) | Host name(s) | missing Host name(s)>
(<request | socket>, N times)` -- never naming one -- and its cause and fix one
sentence per kind of refusal, the fix naming that kind's latest value: an
`Origin` that is a page on this PC
(`http://localhost`, `http://127.0.0.1` or `http://[::1]`, any port) -> add it
to `NOVA_CORS_ALLOWED_ORIGINS` with the Vite origins, then Reload backend; a
browser extension (`chrome-extension://`, `moz-extension://`, ...) -> remove it
if unknown; `null` -> a sandboxed frame or an HTML file opened from disk; any
other `Origin` -> a web page in a browser on this PC, close that tab; a `Host`
-> add it to `NOVA_ALLOWED_HOSTS` (with `NOVA_API_HOST` and `NOVA_API_KEY`) if
that is you from another machine, otherwise it was refused on purpose (DNS
rebinding). The fix then names up to three more values the sentences did not
(`Also refused: <Host | Origin> <value> (<request | socket>, N times), ..., and N
more.`). After the window the row is `ok` again with "last refused N min ago:
1 <noun> (...)" and the fix "Nothing to do. Last refused: <Host | Origin>
<value> (...).", so one probe does not keep the desk yellow all day. `evidence` is the
snapshot: `refusals: [{kind: "http" | "websocket", header: "Host" | "Origin",
value, reason, count, first_at, last_at, last_path}]` newest first (wall-clock
seconds; value and path cut to 200 characters), `refused_total`,
`dropped_values`, `max_values` (32) and `recent_window_sec`. Refused values are
the sender's text -- a site the operator had open, or a name an attacker chose --
so only the fix names them, at most 60 characters of one, unprintable characters
as `?`; the desk renders every field as text. An issue filed from the desk
prints a row's detail and cause, never its fix or a `process` row's evidence
(see "Public-safe by construction"), so a refused value never reaches GitHub. A `warn`
row is listed under "Needs attention" at the top of the Trading prerequisites
panel; the panel reads the checklist only while it is open, and a refusal does
not open it.

**PC memory** (operator report 2026-10-11: "nova keeps driving the ram higher
and higher"; the PC sat at 72 of 80 GB committed while Nova held 3.4 GB of it).
The `process` group carries the `pc_memory` row, read from the memory watch's
last reading (`perf.memory_watch.status()`; its shape is in `performance.md`,
"Memory watch"). Its detail is always `PC memory <load>% in use, <used> of
<limit> GB committed. Nova <total> GB (API a, Sim import b, desk c, Gateway d),
<share>% of it; other programs <n> GB` (parts holding nothing left out); the
other programs are named only in the fix -- `The biggest others: <image name>
xN <GB> (largest pid P, <GB>); ...`, at most three -- because an issue filed
from the desk prints a row's detail and cause, never its fix or a `process`
row's evidence, and what else runs on the operator's PC is not Nova's to
publish. States: `fail` when a Nova part holds past its leak line (the API
`PERF_MEMORY_API_LEAK_MB` 5,000 MB, the desk's processes together
`PERF_MEMORY_DESK_LEAK_MB` 4,500 MB; the week to 2026-10-11 peaked at 3,433 and
2,763) -- "Nova's <part> holds X GB, past its Y GB line", cause a leak in Nova,
fix the heap census and Report an issue -- or when the commit charge reaches
`PERF_MEMORY_CRITICAL_PCT` (97%) of its limit, where any program's next
allocation fails; `warn` at `PERF_MEMORY_PRESSURE_PCT` (90%) of RAM in use or
of the commit limit, its cause "Nova holds most of it." when Nova's share of
the commit charge is half or more, else that other programs do; `ok` below;
`unknown` before the first reading (20 s after start) or when the last is older
than `PERF_MEMORY_STALE_SEC` (300 s); `off` off Windows. `evidence` is the
reading.

**PC network ports** (operator report 2026-10-14: the PC ran out of ports at 11:45 ET and the backend
restarted 19 times in 40 minutes; "just make sure no leakage happens"). The `process` group carries the
`pc_ports` row, read from the port watch's last reading (`perf.port_watch.status()`; its shape is in
`performance.md`, "Port watch"). Detail: `Network ports <in_use> of <count> in use (<pct>%); <n> held by
programs that have closed`. States: `fail` at `PERF_PORTS_CRITICAL_PCT` (90%) -- "nearly out", cause: every
new connection fails once none are left, IB Gateway's, the desk's and the backend's own included; `warn` at
`PERF_PORTS_PRESSURE_PCT` (70%), or when `closed.connections` reaches `PERF_PORTS_CLOSED_WARN` (500) -- a
leak that only grows, cause: Windows keeps connections of programs that have closed; `ok` below; `unknown`
before the first reading or when the last is older than `PERF_PORTS_STALE_SEC` (300 s); `off` off Windows.
The fix for a leak is a restart of the PC at a quiet moment (IB Gateway needs its login after one); the
living programs holding the most are named only in the fix, as the memory row does. `evidence` is the
reading.

**The API guard never stops a backend on a probe that could not run** (same report). Owner
`api_process_guard.py` / `api_instance_lock.py`: the guard's listen probe answers listening, not listening
(a refusal, or a timeout -- on Windows a refused loopback connect outlasts the 0.4 s probe), or unknown (any
other error: the PC would not open the connection). Unknown never stops the API, and a second API never
classes a living holder it cannot probe as an orphan -- it refuses to start and leaves it running. A stop
the guard does make flushes the eyes' journal (up to 5 s, its own budget) and the log queue first; journal
lines a blocked disk could not take in that time are lost with the exit, and the log says how many.

## Which backend answers (operator report, 2026-09-24)

`GET /api/health` adds `release_tag: string | null` -- the revision (`vNNN`)
this API process runs, read once when it started
(`diagnostics.process_info.REVISION`), `null` when git could not say -- beside
`instance_id` / `pid` / `started_at`. A backend left running across a merge or
an update keeps its own code, so the desk's window title names it after the
desk's own revision when the two differ: `Nova — Stock Scanner · v1007 ·
backend v991 (older -- restart it)`, or `backend v1051 (newer -- update the
desk)` when the desk's installer is behind; when they run one release the title
names it once, `Nova — Stock Scanner · v1007` (operator ask, 2026-09-30: "i
need them to be treated as ONE") (`electron/appTitle.mjs`;
read once a minute and on focus by `utils/backendReleaseTag.ts`; a backend
older than the field is read once per process from its `/api/diagnostics`
`process.release_tag`; nothing while unknown, never another process's
revision). **Reload backend counts only a new process.** The desktop app's
reload (`electron/sidecar.reloadEngine`) restarts an engine it started itself;
an engine it only attached to (scripts/windows/Run Nova.bat, the localhost watchdog, another
checkout) is stopped by that engine's own checkout's `scripts/Stop-NovaPorts.ps1`
(`process.repo_root` from `/api/diagnostics`) and started again by the
watchdog or, with none running, by that checkout's `scripts/Start-NovaApi.ps1`
-- never by the app's packaged engine, whose data lives elsewhere
(`electron/engineRestart.mjs`). It reports success only when a different
`instance_id` answers `/api/health`, and otherwise says why ("Not restarted:
..."); the Vite dev server's reload already waited for a new `instance_id`.
**One restart at a time** (operator report, 2026-09-29: "Why is it taking
forever?"): a reload asked while one runs joins it instead of queueing a second
(`serialQueue.createSharedRun`), and the header's API-down auto-heal restarts
nothing while `/api/health` answers -- a queued second reload had stopped the
engine the first had just brought up. The localhost watchdog stops waiting on
a Vite that exited and retries a failing Vite every 10 min after three
failures, so it checks the API every interval. The
Bots page reads an API older than ADR 031 (setups listed without a `level`) as
a backend that needs a reload, never as a setup with no scanner.

**A restart loads only what its checkout holds** (operator report, 2026-09-25:
"I closed the app and clicked reload backend" -- the new process came up v1017
again, because the engine's checkout was itself v1017 until a pull at 07:57 ET,
while the desk had updated itself to v1024). `/api/health` and `/api/diagnostics`
`process` add `checkout_tag: string | null` -- the revision of the checkout this
process runs from as it is on disk now (`diagnostics/checkout_revision.py`:
re-read on a worker thread at most every `DIAG_CHECKOUT_REVISION_TTL_SEC`, never
on the request; `null` for a packaged engine, which has no checkout, or when git
cannot say). A restart loads newer code only when `checkout_tag` is ahead of
`release_tag`, so an older backend's title reads `(older -- restart it)` when its
checkout is ahead or unknown and `(older -- pull master, then restart)` when it
is not (`appTitle.backendRemedy`). Reload backend's confirmation says a restart
would start the same revision again, its note says so when one did, and the
`frontend_revision` row's fix names the checkout's revision.

**Who owns the backend** (ADR 038, amended 2026-09-29; operator: "1 go"). The
operator's backend is the checkout engine the watchdog, `scripts/windows/Run Nova.bat` and the
morning script start. The installed desk's bundled engine keeps its data in the
app's own folder, so it is a different Paper account, bot session and history.
- **At launch** the installed desk uses whatever Nova engine answers `:8000`.
  It never asks about it, never stops it and never starts a second engine over
  it.
- **The owner.** `/api/health` adds `frozen: boolean` and `repo_root: string |
  null` (`diagnostics.process_info.engine_home`; null for a packaged engine). A
  checkout engine whose root is a main checkout (`.git` a folder), with a `.env`
  and `scripts\Start-NovaApi.ps1`, is remembered as the owner in
  `%APPDATA%\nova\engine-owner.json` = `{schema_version: 1, repo_root, seen_at}`
  (owner `frontend/electron/engineOwnership.mjs`). An unknown version, an
  unreadable file or a checkout without its start script reads as no owner.
- **On an empty port** the desk starts the owner's engine with that checkout's
  `Start-NovaApi.ps1`, so it outlives the desk. If it does not answer, the desk
  asks: Retry (the default), the bundled backend for this session (its data
  folder named), or Exit. With no owner, the bundled engine starts as before.
- **`GET /api/diagnostics/restart-check`** (owner
  `diagnostics/restart_check.py`) answers what a restart of this process would
  interrupt, from memory only (no IBKR request): `{schema_version: 1,
  generated_at, safe: boolean | null, open: [{kind: "bell" | "recording" | "position" |
  "working_order" | "bot_trade" | "stock_mode" | "download", venue: "paper" |
  "sim" | "ibkr" | null, symbol: string | null, text}], unknown: [{kind,
  error}]}`. It covers the Session Records, the practice ledgers this process
  has loaded, IBKR's cached positions and open orders (with no ready session,
  Nova watches nothing there), the bot's open trade, ADR 037's in-memory stock
  modes, approvals and trades, and running history downloads. It also reads
  the clock: from 09:25 to 09:45 ET on an exchange day it lists the opening
  bell (`kind: "bell"`, `venue` and `symbol` null), because a restart then
  drops every Level 2 and Time & Sales line as the bell rings. So Restart to
  update and the backend notice ask first, with "Not now" the default
  (operator report, 2026-10-12: Restart to update at 09:30:25 left the desk
  without MNDR's lines through its flush into VWAP). `safe` is true
  only when every reader answered and nothing is open, false when anything is
  open, and null when a reader failed (never read as "nothing open").
- **`POST /api/diagnostics/stop`** `{reason?: string}` (owner
  `diagnostics/stop.py`; keyed even on a loopback desk, like `/api/config`)
  answers `{ok: true, stopping: true, reason}`, logs `API: stopping at the
  desk's request -- <reason>` and leaves through uvicorn's own shutdown a
  quarter second later, so the Session Records close and the leaderboard run
  ends `shutdown`. A desk reload asks for it first (`engineRestart.askEngineToStop`,
  reason "the desk updated the backend to vNNN" or "the operator reloaded the
  backend") and runs `Stop-NovaPorts.ps1` only when the engine refuses or the
  port is still held after `ENGINE_GRACEFUL_STOP_MS` (25 s). Until 2026-10-13
  every reload was that force-kill: both of that morning's update restarts
  (07:51, 08:45 ET) left no log line and read on the leaderboard as
  `unexpected` gaps, i.e. as crashes.
- **One version** (operator ask, 2026-09-30: "i need them to be treated as
  ONE"). The desk and the owner's backend run the same release. The backend's
  checkout is only ever brought to the desk's own `vNNN` tag, never past it
  (`syncToRelease`, `frontend/electron/engineSync.mjs`): fast-forward only, on
  a clean `master`, refused when the release changes `backend/requirements.txt`,
  and a checkout already at or past the tag is left where it is (master never
  moves back). Until 2026-09-30 it pulled master's newest commit, which put the
  backend on v1051 while v1051's installer was still being built (desk v1050).
- **Restart to update updates both.** Before the installer runs, the desk asks
  the owner's backend what a restart would interrupt; anything open (or a
  backend that cannot say) is listed and the operator may wait, which installs
  nothing. The checkout is brought to the release being installed; if it
  cannot be, the operator chooses between waiting (the default) and the desk
  alone. The old desk leaves `engine-follow.json` in userData = `{schema_version:
  1, tag, repo_root, asked_at}` (owner `frontend/electron/engineFollow.mjs`).
  Once the "Updating Nova" window is up, right before the installer runs, the
  old desk restarts the backend onto that release (`engineSync.handOffForInstall`,
  operator report 2026-10-13: "Why doesn't the backend restart during
  installation?"): the engine's own stop, the port free, then the checkout's
  `Start-NovaApi.ps1` in a process of its own, without waiting for it to answer
  -- it comes up while the installer runs, and the new desk's launch waits for
  it. Only onto the checkout's exact release, read again then; a restart that
  fails there never holds up the install. The new desk reads the promise once,
  deletes it, and restarts the backend onto that release without asking again
  only when it still runs other code (the restart at install did not happen).
  An unknown version, an unreadable file or one older than a day is no promise.
  A bundled engine is the installer's own.
- **A backend behind the desk follows by itself** (ADR 038 amendment
  2026-10-13; operator: "it should already know we need to restart the backend
  and restart it without us having to click on it"). Every 15 s the installed
  desk looks whether the owner's backend runs an older release than itself
  (`engineSync.follow`). If it does and the restart check holds nothing but
  recordings, it brings the checkout to the desk's tag, reads the restart
  check again, and restarts the backend, with no button -- only when the
  checkout then holds the desk's exact release, never one past it; the notice reads "Nova is updating the backend to
  vNNN…". Otherwise the notice lists what holds it (`engine.auto.holds`) beside
  **Update backend now**, and Nova goes once it clears. Each pair of releases
  is tried once; still behind, the action below is the operator's again.
- **The backend notice** (`frontend/src/desktop_update/BackendNotice.tsx`, in the
  update strip). It shows while the backend runs another release than the desk,
  with one action: **Update backend to vNNN** when it is behind and runs from
  the owner (the checkout to the desk's tag, then a restart -- never a restart
  and then a pull); **Update desk to vNNN** when it is ahead (it looks for that
  release now, as Help > Check for Updates does); **Restart backend now** for a
  behind backend from another checkout that already holds newer code. It reads
  the restart check first: nothing open goes in one click; anything open, or a
  backend too old to say, is listed and confirmed. Later hides it until a
  revision changes.

  The operator retired the separate unattended nightly pull of master and
  restart (#616) on 2026-10-13. Updates use the existing release flow; the
  backend follows the desk's installed release under the checks above.

## Where Nova keeps its data (operator ask, 2026-09-24)

"any recording and data, lets keep them off the C drive": the operator's F:
drive holds every data folder. The Session Records, downloads, leaderboard,
catalysts and eyes already default to `F:\Nova\...` while F: is mounted. The
checkout's own `backend\.cache` (archive, cold archive, nightly backups, Level 2
and tape archive, practice and execution ledgers, perf) and `backend\logs` move
there with `py -3 tools/data_root.py move`, run while Nova is stopped. Each is
copied to `F:\Nova\cache` / `F:\Nova\logs`, every file is verified by size and
modified time, and the C: folder becomes a directory junction, so every writer
(the backend, the premarket scripts, Vite, research, tools) keeps its path. Only
the checkout the tool runs from moves (`--repo` names another): a worktree keeps
its own `backend\.cache` and so its own `api-instance.lock`. A junction whose
drive is gone fails every write loudly; nothing starts an empty store on C:.

The tool refuses while :8000 or :5173 answers or the API lock's process lives.
It never merges into a folder it did not fill, never copies C: over a folder
that already became the data, and finishes an interrupted move on the next run.
Its marker `F:\Nova\cache\.nova-data-root.json` (and `F:\Nova\logs\...`) is
`{schema_version: 1, moved_from, state: "copying" | "verified" | "moved",
started_at, verified_at, moved_at, files, bytes}`; an unknown version refuses.
The C: original (`backend\.cache.moved-<stamp>`) is deleted only once the
marker reads `verified` or `moved`. `status [--json]` is read-only and answers
`{schema_version: 1, repo, data_drive: {root, mounted, free_bytes},
desk_running: string[], folders: [{id: "cache" | "logs", path, target, real,
kind: "junction" | "folder" | "missing", originals, files, bytes, error}]}`.

`/api/diagnostics` adds the `data_folders` row (group `process`; owner
`diagnostics/collect_data_root.py`), `evidence: {data_drive, data_drive_mounted,
system_drive, folders: [{id, label, path, real, env, error}]}` for the cache,
logs, captures, downloads, leaderboard, catalysts and eyes, `real` with
junctions resolved and nothing created to look. It is `warn` while a folder
sits on the system drive and F: is mounted (the fix names the move, or the
environment variable that put it there), `fail` when a folder's drive is gone
and `unknown` when one cannot be resolved.

## Why the Gateway needed a phone login; premarket evidence (#14)

IB Gateway's saved login survives only its own `AutoRestartTime` restart; any
end of the process (a PC restart, a crash, closing it) costs a phone login.
`ibkr/relogin_reason.py` explains the latest Gateway start from the IBC log's
`autorestart file (not) found` line and the Windows System event log
(`ibkr/windows_restarts.py`, read-only `wevtutil`, cached per boot):
`{schema_version: 1, reason: "token_reused" | "pc_restarted" |
"gateway_started_fresh" | "unknown", text, login_ts: number | null, restart:
{boot_ts, cause: "windows_update" | "start_menu" | "power_button" | "app" |
"unexpected" | "unknown", label, initiated_ts, process, windows_reason,
reason_code: string | null, shutdown_type: "restart" | "power_off" |
"shutdown" | null, first_signin_ts} | null}` (epoch seconds; `null` for
anything unrecorded). `power_button` is a System 1074 from `winlogon.exe` on
behalf of SYSTEM (`S-1-5-18`) with reason `0x500ff` and Shutdown Type `power
off`, as the desk recorded on 2026-10-05 06:45 and 2026-10-06 07:16 ET; the
Start menu names `StartMenuExperienceHost.exe` and the user. `winlogon.exe` on
behalf of a user stays `start_menu`, and on behalf of SYSTEM otherwise is `app`
-- never the Start menu, and a `restart` is never the power button.
`shutdown_type` is the event's own (`null` in a word Nova cannot read), and
`text` says "powered off" or "restarted" by it. The query asks each event id
of its own provider only. A restart is claimed
only when one is on record within `RELOGIN_BOOT_WINDOW_SEC` before the login;
an unreadable event log is never read as "no restart". While a 2FA prompt is
open, `/api/diagnostics`'s `gateway_ibc_login` row carries it as
`evidence.relogin` and leads its `cause` with `text`.

`tools/premarket_verify.py` (read-only) answers #14's two criteria:
`{schema_version: 1, generated_at, days, morning_runs: [{date, started,
unattended, result: "PASS" | "FAIL" | null, failed_leg}], missed_mornings:
[{date, reason}], full_logins: [{ts, source: "ibc_log" | "daily_start",
weekday, expected, relogin}], restarts: [restart], restarts_readable,
criteria: {unattended_pass: {met, date}, no_unexpected_logins: {met, count}},
met}` -- `unattended` is a run whose first line falls in 03:50-04:05 local,
`expected` a phone login at the weekend (IBKR's weekly re-auth). `relogin`
prints the explanation's `text` (`--json` the object); `Start-NovaDaily.ps1`
logs it as `WHY:` and `Invoke-NovaMorningCheck.ps1` adds it to a failed
Gateway leg's alert. Nova's IBC launchers set `DAYOFWEEK` so IBC's weekday
log names survive Windows 11's missing `wmic`.

**Proof availability (#742).** The verifier adds `evidence_sources` keyed by
`morning_check`, `daily_start`, `ibc` and `windows_restarts`: each source reports
`status: "readable" | "missing" | "unreadable" | "partial" | "unsupported"`,
`read_at`, `first_ts`, `last_ts`, `dates[]`, `problems[]` and, for the Windows
query, `queried_since`. `login_evidence` is `{complete, requested_from,
requested_through, problems[]}`; `criteria.no_unexpected_logins` also carries
`known` (an observed unexpected login establishes failure; absent observations
establish a quiet week only with complete proof). Missing or partly read sources,
insufficient retained dated history and unavailable Windows evidence keep the
quiet-week verdict unknown and `met: false`. Readable-empty restart evidence is
known; bare empty login lists carry no coverage. The one-PASS plus quiet-week
criterion stays unchanged; missed mornings are context. The precise retained
observation contract and its limits live in `docs/live-desk-sync.md` §4.
`tools/premarket_ibc.py` owns the verifier's pure per-start timestamp acceptance:
it returns records and source problems together. Rejected records have unknown
timestamps and cannot populate `full_logins` or a known weekday failure;
positively dated records retain their counts even if other evidence is partial.
The shared `ibkr/relogin_reason.py` operator-diagnostic contract stays unchanged.

## Release notes and the update notice (operator ask, 2026-09-23)

**The release record.** Each `vNNN` GitHub Release body carries one hidden
line, written by `tools/release_notes.py` from the commit that made it
(`Desktop pack` > `publish-release`):
`<!-- nova-release-notes {schema_version: 1, tag, title, kind, scope, pr,
summary, points} -->` -- `title` the PR title without its conventional prefix,
`kind` / `scope` that prefix (`feat` / `desk`; `null` without one), `pr`
`integer | null`, `summary` plain text (at most 500 characters) and `points`
`string[]` (at most 8). `<` and `>` are JSON-escaped so the line can never
close its comment. A body without the line (a release made before it existed)
is listed as `recorded: false`, never given an invented summary.

**The update view.** The Electron main process publishes one view to the main
window over IPC (`frontend/electron/updateBridge.mjs`; channels
`nova:update:view` / `nova:update:subscribe` / `nova:update:act`; Trader
pop-outs neither receive it nor may act): `{schema_version: 1, installed,
notice, whats_new, file_issue, engine}`. `engine` (installed desk only, ADR 038
amendment) is `{owner: string | null, attached_to_owner: boolean, running:
"pull" | "restart" | null, last: {at, outcome: "pulled" | "restarted" |
"current" | "failed", text} | null, auto}`. `auto` (ADR 038 amendment
2026-10-13) is `null` while nothing holds the backend's restart by itself, or
`{state: "waiting" | "left", holds: string[], reason: string}`: `waiting` lists
what holds it (the restart check's `text` lines, every kind but `recording`,
plus each `unknown`; a backend with no readable answer holds it too); `left`
means Nova tried this pair of releases once and the backend is still behind,
so the button is the operator's (`reason`: the failure, when there was one). `notice` is `null` or `{stage: "available" | "downloading"
| "stopped" | "ready" | "installing", tag, installed, percent, retry, error,
notes, auto}`; `auto` (operator ask 2026-10-14) is `null` when the release
waits for the operator's click, else `{waiting: string[]}` on an `available` or
`ready` notice: Nova downloads or installs it by itself, and `waiting` lists in
the operator's words what it waits for (`[]`: it goes now); `whats_new` is `null` or `{mode: "updated" | "recent", tag, since:
string | null, notes}`. `notes` is `{loading, error: string | null,
releases: [{tag, number, recorded, title, kind, scope, pr, pr_url, summary,
points, published_at, url}], more, older_unlisted, page_url}` -- newest first,
at most 30 listed (`more` counts the rest; `older_unlisted` says GitHub's one
page did not reach the installed release). The window answers
`{action: "download" | "later" | "restart" | "whats-new-close" | "open-link" |
"backend-sync" | "check-update", url?}` (`backend-sync`: the backend notice's
Update backend to vNNN; `check-update`: its Update desk to vNNN); `open-link` opens only this repository's release, pull request and issue
pages and gists (`isReleaseLink` / `issueLinks.isIssueLink`). `file_issue` is
`null` or `{requested_at}` (epoch ms): Help > File an Issue… sets it, and the
page opens its issue form when the value changes after it subscribed (the value
the first view carries is never replayed); with no page listening the menu opens
GitHub's new-issue page instead.

**A release still being built (operator report, 2026-10-13).** `Desktop pack`
publishes a merged commit's Release about seven minutes after it lands, and
Help > Check for Updates in that gap read only "Nova v1275 is the latest
release." (v1276 merged 22:25:08 UTC and published 22:31:20; the operator asked
at 22:29 and 22:30). A Help-menu check that settles on `current` now asks GitHub,
unauthenticated, whether a newer release is being built
(`frontend/electron/releaseBuild.mjs`); automatic checks never ask. Reads:
`GET /repos/aaltaay/Nova/actions/workflows/desktop-pack.yml/runs?branch=master&status=in_progress`
(then `status=queued` when none of those will pack), its `workflow_runs[]`
`{id, status, event, head_branch, head_sha, created_at, run_started_at}`, newest
first, never a pull request's. Each run's jobs are read (`GET
.../actions/runs/{id}/jobs?filter=latest&per_page=100`, `jobs[] {id, name,
status, conclusion, run_attempt, labels}`, the newest attempt of each name
counting). A run counts only while its Release can still be published: no
`Desktop pack` job and none of the checks `tools/release_gate.py` requires
(`Release checks / Backend tests`, `/ Frontend build`, `/ Frontend E2E`,
`/ Agent contract`) has finished other than `success` -- the run stays
`in_progress` while the other side still runs, so a red pack would otherwise be
named as building. A `workflow_dispatch` run (PR delivery's, or by hand) always
packs; a `push` run packs only when its `Desktop pack` job runs on
`windows-latest` (a docs-only push runs it on `ubuntu-latest` and gets no
Release), and one whose job has no runner yet is not counted. The run's `vNNN`
is its head commit's count, as
`Desktop pack` stamps it (`git rev-list --count`): `GET
/repos/aaltaay/Nova/commits?sha=<head_sha>&per_page=1`, whose `Link` header's
`rel="last"` page is that count. A count above the installed release's adds the
dialog's `detail` under the unchanged message: "v1276 is being built now
(started 4 min ago). A build usually takes about 7 minutes; check again in about
3 minutes. It is published only if its checks pass." -- "is queued to be built
(queued 1 min ago)" for a queued run, "this one is taking longer; check again in
a few minutes" past the usual time (`UPDATE_BUILD_TYPICAL_MINUTES`,
`updatePolicy.mjs`). Every request shares one `RELEASE_BUILD_TIMEOUT_MS` (4 s)
deadline. Any failure -- offline, rate limit, an HTTP error, an answer of another
shape, no `rel="last"` -- writes one WARN line to `update.log` and the dialog says
exactly what it said before. Nothing is persisted.

**The release ping and the automatic install (operator ask, 2026-10-14: "If a
new release goes up in the cloud, how can the cloud communicate with us").**
GitHub cannot call the desk: it has no public address and its API answers
`127.0.0.1` only. So `Desktop pack` > `publish-release`, right after a Release
is created or updated, posts its tag to a public ntfy.sh topic: `POST
https://ntfy.sh/nova-aaltaay-desk-releases`, body `vNNN` (plain text), header
`Title: Nova vNNN`; a post that fails warns and never fails the job. The
installed desk keeps one outgoing connection to `GET
https://ntfy.sh/nova-aaltaay-desk-releases/json` (`RELEASE_PING_TOPIC`,
`frontend/electron/releasePing.mjs`; a test holds the workflow to the same
topic): ntfy's stream, one JSON event per line, `{id, time, event: "open" |
"keepalive" | "message" | ..., topic, message}`. A `message` whose text is a
`vNNN` newer than the installed release makes the desk ask GitHub now (an
automatic check, origin `ping`), at most once per `UPDATE_PING_MIN_GAP_MS` (60
s; a ping inside the gap checks once it ends). Anyone can post to a public
topic, so a ping is a hint, never a source: the installer still comes from the
Release through electron-updater, checked against its sha512, and a false ping
costs one check. A connection silent for `RELEASE_PING_SILENT_MS` (3 min; ntfy
sends a keepalive every 45 s) is dropped; a dropped one opens again after 5 s,
doubling to 5 min, and asks `?since=<time of the last event read>` so a release
posted meanwhile still arrives. `NOVA_UPDATE_CHECK=0` opens no connection.
Nothing is persisted; `update.log` says when it starts listening, when a
connection drops (once per run of failures) and when it comes back.

A newer release found by any check then goes by itself
(`frontend/electron/autoInstall.mjs`), every `UPDATE_AUTO_TICK_MS` (30 s)
looking whether it may: it downloads once nothing holds it, and installs once
nothing holds it and Windows has seen no keyboard or mouse input for
`UPDATE_AUTO_IDLE_MS` (5 min, Electron `powerMonitor.getSystemIdleTime`). What
holds it, in `notice.auto.waiting`: weekday trading hours, 07:00-16:00 ET
("trading hours (until 16:00 ET)"); every line `GET
/api/diagnostics/restart-check` lists but a recording, read as the backend's
own automatic restart reads it (`engineFollow.autoRestartHolds`: a position, a
working order, a bot trade, a stock mode, a history download, the opening bell,
a reader that failed, or a backend that did not answer); and, for the install,
"5 minutes with no keyboard or mouse input". The install is Restart to update's
own, with no dialog: the restart check is read again before the backend's
checkout is brought to the release and once more after (a pull can take two
minutes); a hold that appeared meanwhile waits for the next look, and anything
else that stops it -- the checkout cannot follow, the engine would not stop --
leaves that version to the operator's click for the session, said in
`update.log`. A version the operator answered Later for, or one an install
left, is the operator's (`auto: null`) until the next launch. Hide (the
notice's button while a download runs) only hides the notice: the download goes
on and the install by itself still follows (PR #978 review).
A release found in trading hours by a ping or a re-check raises no notice until
16:00 (as before); the launch check and Help > Check for Updates show theirs at
once, with `auto` saying it waits. `NOVA_UPDATE_AUTO_INSTALL` (`0` / `false` /
`no` / `off`, process env or the desk `.env`) turns the automatic download and
install off: the offer-only desk of 2026-09-23, `auto` always `null`.

**Persisted (userData, owner `frontend/electron/`).**
`release-notes-cache.json` `{schema_version: 1, fetched_at, rows}` -- the last
page of GitHub's Releases API, so What's new after the restart reads the notes
the notice fetched (`releaseNotesSource.mjs`; an unknown version is ignored).
`whats-new.json` `{schema_version: 1, seen_tag, closed_at}` -- the release whose
notes the operator last closed (`whatsNew.mjs`; no file shows the installed
release's own notes once; an unknown version is left alone and shows nothing).

## Filing an issue from the desk (operator ask, 2026-09-24)

"When I do the update, I can also click and say 'File an issue' ... it goes
directly to GitHub"; then "link the issue/dump file as part of this issue
automatically"; "humans are not going to ... give you a title or description";
"I really don't want any personal information about my computer, but I need
enough debugging points ... this is real money." Owner `backend/issue_report/`
(the form: `frontend/src/issue_report/`, opened from the What's new card and
Help > File an Issue…). Nothing there places, stages or cancels an order.

`GET /api/issues/draft` builds a draft -- the desk as it is now -- and answers
`{schema_version: 1, repo: "aaltaay/Nova", public: true, filer: {direct,
via: "gh" | null, account: string | null, reason: string | null}, kinds: [{id:
"bug" | "feature", label, github_label: "bug" | "enhancement"}], context,
context_lines: string[], limits: {title_max, details_max}, draft_id,
created_at, auto_title, dump: {file_name, bytes, summary: {rows, fail, warn,
unknown, log_records, client_errors, windows, checklist_error, log_error,
removed}, sections}}`. `context` is `{nova, commit, ui, venue, page, tab,
symbol} | null`, each `null` when unknown, rebuilt from checked fields only.
`GET /api/issues/draft/{draft_id}/dump` is the dump as text, exactly as it would
be uploaded (404 once expired). Drafts are in memory for
`ISSUE_REPORT_DRAFT_TTL_SEC` (30 min), at most `ISSUE_REPORT_DRAFTS_KEEP`.

`POST /api/issues` `{schema_version: 1, kind, title, details, context | null,
draft_id, attach_dump}` -> 201 `{schema_version, number, url, kind, title,
labels, auto_title, auto_description, removed, dump: {file_name, url: string |
null, error: string | null, saved} | null, via: "gh"}`. It needs the desk's
API key even on loopback (`auth.is_issue_report_mutate`: it publishes on a
public repository as the operator). A bug's title and description are
optional: left empty, Nova writes them from the dump -- the title from the
first failing check (else the newest engine error), with the page and the time;
the description from the failing and warning checks, the newest engine errors
and desk window errors -- with no model and no tokens. A feature needs a title
or a line; a report with no words and no dump is refused. The dump is uploaded
first, as a **secret gist** (`gh gist create`), and linked from the issue; a
copy is saved under the operator cache in `issue_dumps/`; a failed upload still
files the issue and says so in it. The body ends with the context, the
checklist counts, the dump link and a hidden record `<!-- nova-desk-issue
{schema_version: 1, kind, filed_at, context, dump, dump_file, auto_title,
auto_description} -->`. Filing goes through the GitHub CLI signed in on this
PC (`gh api`); Nova never reads the token. A refusal is `{detail: {reason,
error, field, new_issue_url}}` with `reason` one of `ISSUE_INVALID` (400),
`ISSUE_DRAFT_EXPIRED` (409, the form builds a fresh draft),
`ISSUE_FILER_UNAVAILABLE` (503: no `gh`, or signed out), `ISSUE_FILE_FAILED`
(502) and `ISSUE_FILE_UNCONFIRMED` (502, no link: the issue may exist);
`new_issue_url` is GitHub's new-issue page prefilled with the same issue.
New issues land in `00 - Untriaged` (`backlog-inbox.yml`).

**Public-safe by construction** (`issue_report/scrub.py`, one `Scrubber` for
the dump and for typed text): every secret-named environment value and
token-shaped string, IBKR account ids, balances and P&L by name and dollar
amounts of $1,000 or more (share prices stay), file paths (the repo, the data
drive, the cache, the logs and the home folder become `<repo>` / `<data>` /
`<cache>` / `<logs>` / `<home>`, any other path `<path>`), the Windows user
and machine names, e-mail and IP addresses (loopback stays). Evidence fields
that name paths, files, folders, environment keys or monitor labels are
dropped, and the process and integrations checks carry no evidence. Engine-log
lines that quote what a sender chose (`ISSUE_REPORT_SENDER_TEXT_LOGGERS`: the
request guard's refusals, `request_guard.middleware`) keep their logger, time
and count with a fixed message in place of the text, so a refused Host name or
page origin stays on the desk (#828). The dump
(`issue_report/dump.py`, schema 1, text): a summary, every diagnostics row with
its state, detail, cause, since and evidence, the engine log's latest
`ISSUE_REPORT_LOG_RECORDS` (50) distinct warnings and errors (repeats folded,
a traceback's exception kept), the desk windows' reported errors and each open
window's page and symbol.

## Symbol directory for the header search (operator ask, 2026-09-23)

`GET /api/symbols/directory` (owner `backend/symbol_directory.py`, read-only)
answers `{schema_version: 1, source: "alpaca_assets", fetched_at: number |
null, count, error: string | null, symbols: [[symbol, name, exchange], ...]}`
-- every active US equity listing on NASDAQ / NYSE / AMEX / ARCA / BATS from
Alpaca `/v2/assets` (listing metadata only, no price), ETFs and units
included, sorted by symbol, cached in process for
`SYMBOL_DIRECTORY_TTL_SEC`. A failed fetch keeps serving the last good
directory with `error` set; no keys is `count: 0` with the reason. The
header ticker search loads it on first focus and matches desk symbols first,
then listed symbols by ticker prefix or company name; `/regex/` and `A*X`
wildcards run over symbols only. Recent look-ups persist in `localStorage`
`nova.search.recent` (`{schema_version: 1, symbols: string[]}`, newest first,
at most 12; owner `components/tickerSearchRecents.ts`).

## The operator's watch list and its toasts (operator asks, 2026-09-23 and 2026-09-24)

**The watch list is today's hot list** (ADR 044, "One Bots page" above: watching only, never who trades; owner
`watch_list/watchListStore.ts`, over `hot_list`). A symbol is starred on or taken
off from a scanner row's hover actions (★ / ★ Listed), the symbol menu's ★ row
(right-click a scanner row, a HOD Momo strip or alert row, a Contenders or Setups
row, a Desk board or Focus rail row, a Trader tab), the chart menu, the Trader's
Who trades row, Tickers today on the Bots page, or the Hot list tab (the old Watch
list tab). A write shows at once and is undone when the backend refuses it, in the
backend's words. The list is the backend's, fresh at 04:00 ET, so the leaders
rule's names are on it too. The list this desk kept before (`localStorage`
`nova.watch.list` = `{schema_version: 1, symbols: string[]}`, an unknown version
ignored) is only read now: the Hot list tab offers once to star what fits, or to
forget it, and then removes the key. The sample desk keeps its own list in memory
and sends nothing.

**Which toasts come** (operator, 2026-10-12: "i get alot of stupid toast notifications ... the way we have it
codded is no good"; ADR 044 amendment of that day). A toast is something to act on in the next minute, about
a stock the operator chose. Every candidate event for a listed name passes one gate (owner
`watch_list/toastGate.ts`, pure), which raises a toast, folds it into the toast already on screen, or holds it
back with its reason:

- **Stars toast; auto stars toast once.** A star (★, `how: "star"`) toasts on its HOD Momo alerts and its
  setups. An auto star (☆) toasts only when it joins the list -- "GIXI joined the top 3 Gainers", its rank
  and change on the board -- once a trading day, and only when it joined within
  `WATCH_TOAST_JOIN_FRESH_MS` (2 min), so a page load never announces an old join. The join toast's
  **★ Star it** makes it a star (`POST /api/hot-list/star`), so it toasts like one from then on.
- **Running Up never toasts.** A live `/ws/hod-momo` `alert` frame for a star -- never the `initial`
  snapshot, a reconnect's replay or the Sim playhead's history -- raises "XYZ hit HOD Momo" for any
  strategy except Running Up (12), with the alert's time (ET), strategy, price, change, volume and RVOL,
  each left out when unknown. Running Up stays on the HOD Momo feed and the Hot list tab.
- **Setups from armed up, with their numbers.** A star's setup toasts when it arms, comes near its trigger
  or triggers (forming is the Hot list tab's Setup column, never a toast), and the toast carries the
  setup's trigger and stop (`setup.trigger`, `setup.stop`) beside the last price.
- **A trading window.** No toast outside it: `localStorage` `nova.watch.toastWindow` =
  `{schema_version: 1, start: "HH:MM", end: "HH:MM"}` in ET, set on the Hot list tab, 07:00-16:00 by default
  (`WATCH_TOAST_WINDOW_DEFAULT`; owner `watch_list/toastWindow.ts`). An unknown version or a malformed
  window reads as the default with a console warning; the tab refuses an end at or before the start.
- **One quiet period per stock.** After a toast, the stock's HOD Momo alerts stay quiet for
  `WATCH_TOAST_QUIET_MS` (15 min): one that comes while its toast is still on screen folds into it (strategy
  and count) without restarting its timer; otherwise it is held back. A setup moving up a stage always
  comes through and starts the quiet period again. The gate's memory is the trading day's (04:00 ET).

One toast per symbol, as before: HOD Momo alerts and setup lines fold together (one line per setup, newest
first), the title names the newest event, and a toast leaves `WATCH_TOAST_TTL_MS` (20 s) after its newest
raised event unless hovered. Open goes to the symbol, Take off the hot list removes it, × dismisses. It places
nothing. HOD Momo's tradeable floor still applies: a listed symbol the master gate refuses raises no alert,
so no toast.

**Nova scores its own toasts** (owner `watch_list/toastScores.ts`). Every raised toast is kept for the trading
day with its kind (`join` | `hod` | `armed` | `near` | `triggered`), time and the price it showed (null when
it showed none). Once its five minutes have passed, the main desk window reads the symbol's live 1-minute
bars (`GET /api/ticker/{symbol}/bars?timeframe=1Min`): the reference is the toast's price, else the close of
the last minute before it; the outcome is the close of the fifth minute after the toast's own. A replay
answer (`coverage.replay`, a Sim desk) or a failed read is tried again later; after
`WATCH_TOAST_SCORE_GIVE_UP_MS` (30 min) the toast reads "no bars", never a guess. Held-back events are
counted by reason (`running_up`, `auto_star`, `forming`, `quiet`, `outside_window`). The day's record is
`localStorage` `nova.watch.toastScores` = `{schema_version: 1, day: "YYYY-MM-DD", toasts: [{id, symbol,
kind, at, price, score: null | {ref, after, move} | {none}}], held: {reason: count}}` (`at` epoch ms, `move`
a fraction), at most `WATCH_TOAST_SCORES_MAX` toasts, replaced at the next trading day; an unknown version
is dropped with a console warning. The Hot list tab shows it per kind: toasts, scored, higher five minutes
later, the median move, and what was held back.

**A setup's ladder** (operator ask, 2026-09-24: "shouldn't these toast notifications be watching if a
strategy is forming?"; owner `watch_list/setupClimbs.ts`, pure). The toasts follow the setup scanner's live
board (`/ws/setups`, ADR 022 / 031). A setup climbs its ladder: forming (`leg` or `pullback`), `armed`,
`near`, `triggered` -- each at most once per setup (its `setup.leg_t`: a near that drops back to armed and
returns is one climb), forming at most once per `WATCH_SETUP_FORMING_REPEAT_MS` (5 min) per symbol and
setup. `failed`, `filtered` and `watching` are off the ladder. A triggered setup, or an armed or near one a
newer leg replaced, ends its ladder, so the next one is news again. Only a climb between two live frames
counts: the first frame after a page load, a reconnect or a return from Sim is read silently (nothing old is
announced as new), the Sim eyes' board (`source: "sim"`) never toasts, and a symbol's ladder before it was
watched is already known. It fires at every bot level: the watch list is the operator's own ask, not a
proposal. The title names the climb -- "PFSA: bull flag armed", "PFSA: first pullback near the trigger" (the
open for red to green, the high for a flat-top), "PFSA: bull flag triggered". A setup line reads the
scanner's own words (state chip and reason, the tape verdict when near; the full explanation on hover) and
follows the board while the toast is up -- a setup that fails or drops off the board says so -- without
restarting the toast's timer. The setup scanner follows the HOD Momo names only, so the Hot list tab has a
**Setup** column: the symbol's most advanced setup on the board, "Nothing forming" for a symbol the scanner
follows with no row, and "Not followed" for one outside `universe_symbols` (an API without the field says it
cannot tell).

The ranked Five Pillars list (tab id `watchlist`, `GET /api/strategy/watchlist`)
is labelled **Contenders** in the UI, and the scanner's pillars column
**Pillars**; ids, API paths and wire fields are unchanged.

## The close-of-day reminder (operator ask, 2026-10-01)

Owner `frontend/src/close_reminder/`, mounted once with the app bar (never on the sample desk). At
15:50 ET a card per Paper or Live position still open ("Still holding 500 GRML at 15:50 -- be flat by
15:55"), escalated at 15:55 ("close it now", pulsing), gone at 16:00; a position that goes flat
takes its card with it. Once per position per day per stage: a dismissed card does not return at
its stage. Sim is left out (its clock is the replay playhead); weekends too; there is no holiday
calendar on the client. `localStorage` `nova.closeReminder.fired` (a `prefStore` envelope) holds `{schema_version: 1, date:
"YYYY-MM-DD" (ET), keys: ["<date>|<venue>|<SYMBOL>|<warn | final>", ...]}`; another date or an unknown
version is ignored. On Live the rows may be last-known (the Gateway dropped) and the card says so.
Nothing here places, stages or cancels an order.


## The desk's voice and the header mute (operator ask, 2026-10-14)

Operator: "when we execute a trade, I want the speaker to say, 'Purchased 100 shares' ... When we sell,
I want it to say that as well. I don't want it to embarrass me, though, so I do really want to master
the mute button on the header." Owners: `frontend/src/sound/` (the switch and the voice),
`frontend/src/ibkr/fillVoice.ts` (what a fill says; `FillVoiceHost.tsx` speaks it) and `frontend/electron/deskSound.mjs` (the desktop
windows). Display only: the voice reads the order rows the desk already polls, after the fact; it never
sits on the order path and never places, stages, cancels or delays an order.

- **The header's mute** (a speaker, left of the padlock) is one switch for every sound Nova makes: the
  voice, the HOD Momo ping, the Setups ping, the Trader's call ping, the Nova OS alarm and the TraderTV
  stream. Muting stops a sentence mid-word. On the desktop it also mutes every Nova window's audio, the
  stream's pop-out included (`webContents.setAudioMuted`, applied to windows opened later too). Each
  source's own switch still works under it; while the header mute is on, each says so on hover, and the
  in-page stream's Sound on button is disabled with that reason. `localStorage` `nova.desk.sound.muted`
  (a `prefStore` envelope, `{schema_version: 1, value: boolean}`), shared by every window: a click in
  one window reaches the others through the `storage` event. Missing, or an unknown version, reads as
  sound on.
- **What speaks: fills, on the desk's venue.** From the working and closed order rows
  (`/api/ibkr/orders`, `/api/ibkr/orders/closed`, as `ibkr/ibkrAccountPoller.ts` reads them): an order
  whose `filled_qty` grew says the shares filled since the last read -- "Bought 100 shares of A B C."
  (the ticker spelled letter by letter), "Sold", "Shorted" (a SELL with `short_entry`), "Covered" (a BUY
  whose `effect` is `closes`). Before the verb: "Bot" when a bot sent it (`bot_id`, or an `order_origin`
  of `bot`, `auto_entry`, `approve`, `bot_api` or `nova_exit`). Before the sentence:
  "Loss limit." for the daily loss limit's Auto sell (`order_origin` `loss_limit`, ADR 056; never "Bot sold"),
  "Flatten." for the ticket's Flatten and KILL (`order_origin` `ticket_flatten`, `emergency_kill`, and
  the retired `bot_trip` / `all_stop` on older rows), "Stop hit." for a stop that closes (a `STP` order type or `leg_role` `stop`, not a buy
  stop that opens), "Target hit." for a `target` / `target2` leg. ", partial." while the order still
  works. Fills of one symbol and one sentence in one read are said once with their shares added; more
  than three sentences in one read say the first two and "And N more fills."
- The daily loss limit (ADR 056, `loss-limit.md`) speaks twice at most per account and day, in the poll
  leader's window: "Loss limit warning. Paper is down 1,620 dollars of 2,000." at 80% (with Warn me), and
  "Daily loss limit reached on Paper." at the limit; the header mute silences both.
- **Order rejected.** An order the ticket, a hotkey or the action bar sends and the backend refuses says
  "Order rejected." beside its pop-up (`ibkr/notifyOrderRejected.ts`; the soft warnings it skips stay
  silent).
- **Never spoken:** fills already on the rows when the desk first reads a venue (the snapshot's
  `ordersRead` turns true at the first read in which both lists answered, and that read seeds silently,
  after a start or a venue change alike); shares a Sim rewind takes back (a row whose fill shrank is
  re-based, not spoken); cancels (a cancel that lost the race is a fill, and the fill speaks); an order
  placed or working; anything on the sample desk.
- **One voice.** Only the window that polls the account (the desk poll leader, `ibkr/deskSharedPoll.ts`)
  speaks; the others follow the rows silently. A position that changes (the 1 s account poll) asks for
  the order rows at once, so the voice follows a fill by about a second, not the 5 s order poll.
- **The voice is the computer's own** (`speechSynthesis`, an English voice installed on the PC). Nothing
  is sent anywhere. A window that cannot speak (no voice, or the browser's first-click rule) says why on
  the mute button's hover.


## Who may reach the API: Host names and socket origins (security alerts, 2026-10-09)

Owner `backend/request_guard/`, a pure ASGI middleware that sees every HTTP
request and every WebSocket handshake. It sits inside CORS and the HTTP timing
and outside the API key and the routes: CORS -> timing -> guard -> API key ->
routes. A refused request reaches no route.

**Host names (HTTP and WebSocket).** A request needs exactly one `Host`
header, and its name -- port ignored, case folded, a trailing dot dropped,
`[::1]` read as `::1` -- must be `127.0.0.1` (or any `127.x` address),
`localhost`, `::1`, the bind host `NOVA_API_HOST` when it is a name or address
(a wildcard such as `0.0.0.0` never is, and the API says so at start), or a
name in `NOVA_ALLOWED_HOSTS` (comma-separated, a port ignored). This stops DNS
rebinding: a web page that points its own name at 127.0.0.1 still sends its own
name. `NOVA_ALLOWED_HOSTS=*` turns the check off, with a WARNING at every start;
it is a way out, not a setting.

**Socket origins (WebSocket only).** A handshake with no `Origin` passes: only
non-browser clients (Python, Node, bot brains, tools, tests) send none. One
`Origin` must be in the CORS list (`NOVA_CORS_ALLOWED_ORIGINS`, else
`http://localhost:5173` and `http://127.0.0.1:5173`) or be `file://`, the
packaged desk. Two `Origin` headers, `null` and `*` are always refused, even when
the CORS list names them. A CORS list holding `*` lets every page's fetches
through, so sockets take the two Vite origins in its place (with a WARNING at
start): the browser desk keeps its feeds, and no other page gets them. Origins
compare exactly, case folded. HTTP origins are
left to CORS and the API key: the packaged desk sends none on its fetches.

**What the desk sends (measured 2026-10-09, Electron 41.10.6 / Chromium 146,
a sandboxed window loading its page with `loadFile`):** its sockets send
`Origin: file://`; its fetches send no `Origin` and `Sec-Fetch-Site: cross-site`
and read answers that carry no CORS header. Chrome sends `null` for a local file,
so no web page can send `file://`. The browser desk on Vite sends
`http://127.0.0.1:5173` or `http://localhost:5173`; every client addresses
`127.0.0.1:8000` (or `localhost:8000`).

**Refusals say why.** HTTP: status 400,
`{"detail": "Nova's API does not answer to this Host name. ...add the name to
NOVA_ALLOWED_HOSTS in .env and restart the API.", "reason": "HOST_NOT_ALLOWED"}`.
The body never repeats the Host it refused. WebSocket, before accept: where the
server can answer the handshake (the ASGI `websocket.http.response` extension;
uvicorn 0.44 and TestClient), status 403 with the same JSON shape, `reason`
`HOST_NOT_ALLOWED` or `ORIGIN_NOT_ALLOWED` (that detail names
`NOVA_CORS_ALLOWED_ORIGINS`); otherwise close code 1008 with "Host not allowed:
add it to NOVA_ALLOWED_HOSTS" or "Origin not allowed: add it to
NOVA_CORS_ALLOWED_ORIGINS". A browser sees either as close code 1006.

**The engine log** names every refusal: `request guard: refused <http |
websocket> '<path>' -- <Host | Origin> '<value>' is not allowed`, once per kind,
header and value per 60 s (`REFUSAL_LOG_WINDOW_SEC`); the next line for that
value adds `; N more since HH:MM:SS`. Values are cut to 200 characters and
printed escaped. At start one INFO line lists the allowed names and socket
origins, and a WARNING names each setting that was ignored or is unsafe.

**The desk shows them too** (#828 item 1): every refusal, not only the ones the
log prints, is counted in memory per kind, header and value (the 32 most
recently seen values; counts since the API started) and read by the
diagnostics row `api_refusals`, "Pages and names the API refused" (see "Desk
diagnostics" above). An issue filed from the desk keeps these log lines without
their values (see "Public-safe by construction").

The policy is read once, when `main.py` builds the app; a change to `.env`
needs an API restart. The bot and agent routes keep their own loopback checks
on the caller's address (`/bot/*`, `/api/bot/*`, `/ws/bot/*`, `/api/agent/*`).
