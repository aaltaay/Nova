# Data schema: Desk operations: diagnostics, data folders, updates, issues, small desk features

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/diagnostics/, backend/issue_report/, frontend/electron/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

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
  generated_at, safe: boolean | null, open: [{kind: "recording" | "position" |
  "working_order" | "bot_trade" | "stock_mode" | "download", venue: "paper" |
  "sim" | "ibkr" | null, symbol: string | null, text}], unknown: [{kind,
  error}]}`. It covers the Session Records, the practice ledgers this process
  has loaded, IBKR's cached positions and open orders (with no ready session,
  Nova watches nothing there), the bot's open trade, ADR 037's in-memory stock
  modes, approvals and trades, and running history downloads. `safe` is true
  only when every reader answered and nothing is open, false when anything is
  open, and null when a reader failed (never read as "nothing open").
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
  1, tag, repo_root, asked_at}` (owner `frontend/electron/engineFollow.mjs`);
  the new desk reads it once, deletes it, and restarts the backend onto that
  release without asking again. An unknown version, an unreadable file or one
  older than a day is no promise. A bundled engine is the installer's own.
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

  Nothing pulls or restarts on a timer: an unattended nightly pull and restart
  was proposed and not built, pending the operator's explicit say-so.

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
"current" | "failed", text} | null}`. `notice` is `null` or `{stage: "available" | "downloading"
| "stopped" | "ready" | "installing", tag, installed, percent, retry, error,
notes}`; `whats_new` is `null` or `{mode: "updated" | "recent", tag, since:
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
dropped, and the process and integrations checks carry no evidence. The dump
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

A live `/ws/hod-momo` `alert` frame for a watched symbol -- any strategy,
Running Up (12) included (operator ask, same day); never the `initial`
snapshot, a reconnect's replay or the Sim playhead's history -- raises a toast
in the main desk window: "XYZ hit HOD Momo" once a HOD Momo strategy fired,
"XYZ is running up" while only Running Up has, with the alert's time (ET),
strategy, price, change, volume and RVOL, each left out when unknown. One toast
per symbol: a burst folds into it (count and strategies); it leaves
`WATCH_TOAST_TTL_MS` (20 s) after its newest alert unless hovered. Open goes to
the symbol, Take off the hot list removes it, × dismisses. It places nothing. HOD
Momo's tradeable floor still applies: a listed symbol the master gate refuses
raises no alert, so no toast.

**A setup forming on a watched symbol** (operator ask, 2026-09-24: "shouldn't
these toast notifications be watching if a strategy is forming?"). The same
toast follows the setup scanner's live board (`/ws/setups`, ADR 022 / 031;
owner `watch_list/setupClimbs.ts`, pure). A watched symbol's setup raises it
when it climbs its ladder: forming (`leg` or `pullback`), `armed`, `near`,
`triggered` -- each at most once per setup (its `setup.leg_t`: a near that
drops back to armed and returns is one toast), forming at most once per
`WATCH_SETUP_FORMING_REPEAT_MS` (5 min) per symbol and setup. `failed`,
`filtered` and `watching` never raise one. A triggered setup, or an armed or
near one a newer leg replaced, ends its ladder, so the next one forming is
news again. Only a climb between two live frames counts: the first frame after
a page load, a reconnect or a return from Sim is read silently (nothing old is
announced as new), the Sim eyes' board (`source: "sim"`) never toasts, and a
symbol's ladder before it was watched is already known, so watching a symbol
mid-setup announces only what comes next. It fires at every bot level: the
watch list is the operator's own ask, not a proposal. Still one toast per
symbol: HOD Momo alerts and setup lines fold together (one line per setup,
newest first), and the title names the newest event -- "PFSA: bull flag
armed", "PFSA: first pullback near the trigger" (the open for red to green,
the high for a flat-top), "PFSA: bull flag triggered". A setup line reads the
scanner's own words (state chip and reason, the tape verdict when near; the
full explanation on hover) and follows the board while the toast is up -- a
setup that fails or drops off the board says so -- without restarting the
toast's timer. The setup scanner follows the HOD Momo names only, so the Watch
list tab adds a **Setup** column: the symbol's most advanced setup on the
board, "Nothing forming" for a symbol the scanner follows with no row, and
"Not followed" for one outside `universe_symbols` (an API without the field
says it cannot tell).

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

