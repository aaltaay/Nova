# 🏛️ AGENTS.md — Project Constitution (Law)

> **Single source of truth.** `gemini.md` is a legacy alias that `@`-imports this file (consolidated 2026-07-28 after the two mirrors drifted).
>
> **Status:** ENFORCED — Active governance document
> **Last Updated:** 2026-09-23
> **Project:** Nova — Stock Alert Automation System
> **Enforcement:** Every AI agent (Cursor, Antigravity, any LLM assistant) MUST read this file before writing ANY code. Violations are NEVER acceptable.

---

## Retired ledgers (owner instruction, 2026-09-20)

`BACKLOG.md`, `PROBLEM_LOG.md` and `CHANGELOG.md` are retired and archived under
`_archived/`. Do not read, update, regenerate, or require them during ordinary
agent work. Read archived material only when the user explicitly asks for
historical context. Old references in comments, past PRs, task logs, and
maintenance history are not instructions to restore these files. Use GitHub
Issues/milestones for current work and PR descriptions plus regression tests for
completed fixes. No `problem_log=` footer, problem-log fragment, changelog
entry, changelog fragment or collation job is required or supported.

## 0. PURPOSE

This document is the **single source of truth** for how this project is built, maintained, and extended. It exists because:

1. AI assistants lose context between sessions.
2. Without rules, assistants dump everything into monoliths.
3. The user has explicitly mandated modular, disciplined engineering.

**If a rule here conflicts with an agent's default behavior, this document wins.**

### Master Roadmap (product phases)

- **Canonical ledger:** `knowledge/obsidian/03-Nova-Decisions/Nova-Roadmap-Status.md` — which phase is NEXT, checkboxes, History.
- **Target architecture (maintenance):** `architecture/README.md` + `architecture/dependency-rules.md` + ADRs under `architecture/decisions/` — modular monolith, selective ports/adapters, feature slices, CSS cascade layers. Structural moves must cite an ADR.
- **Continuity rule:** `.cursor/rules/nova-roadmap-continuity.mdc` — read status first; phase-close verify + commit + push; scope guard.
- **Phase B ops:** `docs/paper-shadow-protocol.md` — paper shadow (historical: its `signal` → `confirm` → `auto_paper` ladder was retired by ADR 025; the bot's Off / Eyes / Strategy + Activate is the one automation path); **`auto_live` NO-GO**.
- **Plan / canvas:** `nova_master_roadmap_a_z.plan.md` · `nova-home.canvas.tsx`
- **Nova OS engine map (retired, ADR 025):** `knowledge/obsidian/03-Nova-Decisions/Nova-OS-Status.md` — history of P0–P10; the verdict, mode ladder and executor are gone, the event log and kill switch remain. Product “what’s next” is Roadmap-Status.
- **Docs (docs + canvases):** `.cursor/agents/docs.md` — documentation steward; memory in `.cursor/agent-memory/`; dashboard is Nova Home; preferred canvases `nova-home` + `agent-*` (+ Cursor `context-usage-*`). Continuity: `.cursor/rules/docs-continuity.mdc`. Agent OS: `.cursor/agent-system/` + `docs/agent-operations.md`.

---

## 1. ⚖️ Architectural Invariants (Unbreakable Law)

These rules CANNOT be violated under ANY circumstance:

| # | Invariant | Rationale |
|---|-----------|-----------|
| 1 | **Data-First** | No tool is written before the JSON schema is confirmed in this file. |
| 2 | **Deterministic Tools** | All Python scripts in `tools/` must be atomic, testable, and side-effect-free unless explicitly noted. |
| 3 | **Secrets in `.env` only** | No API keys, tokens, or credentials EVER appear in source code, logs, or commits. |
| 4 | **`.tmp/` is ephemeral** | Never treat `.tmp/` files as a source of truth. |
| 5 | **SOP before code** | If logic changes, update `architecture/` or relevant `.cursor/rules/` FIRST, then write code. |
| 6 | **Self-Annealing** | Any error -> Analyze -> Patch -> Test -> Update SOP/rules -> Record the cause, fix, and verification in the PR or issue. If the bug cannot be fixed this session (too big, wrong task, needs an ADR), **MUST** open or update a GitHub Issue labeled `deferred` instead of a band-aid (`deferred-log.mdc`). |
| 7 | **Broker Execution Gate** | Alpaca-sourced scanning is permanently read-only. Trade execution is permitted ONLY through the explicit opt-in `backend/ibkr/` module. Gateway connection default is **live** (port 4001). The IBKR paper Gateway (4002) is **legacy**: by hand only (`POST /api/ibkr/gateway-mode {"mode":"paper"}`), never an automatic fallback -- `IBKR_PAPER_GATEWAY_FALLBACK` is off by default because a paper login beside a live session is read-only and carries no tape (ADR 020). Spending still requires `IBKR_ENABLED=true` and `IBKR_ORDERS_ENABLED=true`; live money also requires `IBKR_LIVE_TRADING_CONFIRMED=true` in `.env`. No other module may place orders. **Short entry (Phase K / ADR 009):** every SELL is risk-reducing unless an explicit `short_entry` opt-in on the execution command is approved by the short gate (`IBKR_SHORT_ENABLED=true` + fresh IBKR tick-236 `shortable_est`). Never infer shorts from side + flat position. `auto_live` remains NO-GO. |
| 8 | **Constitution is Law** | No code change may contradict this document. If a contradiction is needed, update this document FIRST with a maintenance log entry, THEN write the code. |

---

## 2. 📐 Modularity Laws (Enforced by the checker)

These rules describe behavior, not a snapshot of the tree. A hand-kept file tree
and hand-copied line counts lived here and went stale (11 of 24 listed files were
gone by 2026-09-20); the statements now live next to the code and the checker
keeps them honest. One command answers every rule in this section -- it is the
CI gate (`deploy.yml`; kinds in `tools/maintainer_lib/gate.py`), so run it
before you push:

```text
py -3 tools/maintainer_checks.py --gate --base origin/master
```

### 2.1 Where code goes

- **Entry points hold wiring only.** `backend/main.py`: app factory, middleware,
  `lifespan`, router registration. `frontend/src/App.tsx`: providers, shell,
  route definitions. Anything else belongs to a module (§2.3 caps both).
- **New code goes where its concept is owned.** `py -3 tools/module_map.py [word]`
  prints what every backend package and frontend folder owns, from the code.
- **Nothing owns it? Make an owner in the same change.** A backend package's
  `__init__.py` opens with a docstring whose first line names what it owns
  (`package_owner_missing`). A frontend folder gets a row in
  `frontend/src/FOLDERS.md` with its ADR 005 kind -- `feature`, `shared` or `app`
  (`folder_owner_missing` / `folder_owner_stale`).
- **Prefer a package to a new top-level `backend/*.py` module.** The backend root
  already holds about a hundred modules; a flat namespace is the hardest place to
  find anything.

### 2.2 Feature boundaries (ADR 005)

- A frontend feature imports another feature only through its barrel
  (`../chart`, never `../chart/barsStore`); `shared` code imports no feature
  internals. A deep import into another feature is a `cross_feature_import`.
- The ones that existed when this rule landed (2026-09-23) are frozen, per file,
  in `tools/maintainer_lib/baselines.json` (no count here -- it would go stale);
  one more fails the gate. The slice has no
  barrel yet? Add an `index.ts` exporting what you need.
- Frozen counts only go down. `--update-baselines` rewrites them to the tree; a
  PR that raises one says why.

### 2.3 File size

A line count is a proxy for "an agent can read this file in one pass and see one
concern". It prompts a judgment; it is not a target. **Never squeeze a file to
fit a number** -- deleting blank lines, joining statements or moving code to an
arbitrary sibling. The old hard 400 made agents do exactly that: on 2026-09-23
ten Python / TS files sat at 395-400 lines, against seven in the fifteen lines
below.

| Files | Rule | Kind |
|-------|------|------|
| `backend/main.py` | 200 **logical** lines | `file_size_hard` (gate) |
| `frontend/src/App.tsx` | 150 **logical** lines | `file_size_hard` (gate) |
| `frontend/src/index.css` | 50 raw lines (import-only barrel) | `file_size_hard` (gate) |
| Code (`.py` `.ts` `.tsx` `.js` `.jsx`) over 400 lines | split it, or state why it is one concern | `file_size` (advisory) |
| ... that grew in this change without that reason | split it or state the reason | `file_size_growth` (gate) |
| Any code file over 800 lines | split it; no reason covers this | `file_size_ceiling` (gate) |
| Constants tables (`backend/constants*.py`, `frontend/src/constantGroups/`) | exempt from 400; 800 still applies | -- |
| Stylesheets | advisory at 1000, prefer 700 or less | `file_size` |
| Tests | exempt | -- |

**Stating the reason:** one line in the file's first 40 lines, next to what the
file owns:

```python
"""Scanner discovery.

maintainer: one-concern the never-leak-a-scanner-slot invariant must live in one place
"""
```

A reason names the one invariant or state the file owns. "Legacy" or "too big to
split now" is not a reason -- split it, or leave the advisory finding and open a
`deferred` issue. **Growth** is judged against `--base` (in CI, the PR's target
branch); a new file over 400 counts as growth.

**Logical lines** exclude imports, comments and blank lines, so an entry point
is capped on the wiring it holds rather than on how many providers it imports
(`tools/maintainer_lib/sizes.py`). No counts are maintained here: a hand-copied
number goes stale (#393). `py -3 tools/maintainer_checks.py --json` ->
`logical_line_counts`, and the human report lists every oversize file.

### 2.4 Refactoring Protocol

When you split a file or move a function out of an oversize one:

1. **Move** it to the module that owns its concept (§2.1).
2. **Import** it back in the original file if still referenced there.
3. **Do NOT leave the old copy** behind.
4. **Update all callers** in the same commit.
5. **Never make a monolith worse.** If you're adding to `main.py` or `App.tsx`, extract first.
6. **Split along a seam** -- one concern per file -- never at an arbitrary line to pass a check.

---

## 3. 📐 Data Schema (Confirmed)

### CI scope output

`tools/ci_scope.py` classifies changed repository paths into boolean JSON fields:
`{"backend": true, "frontend": true, "e2e": true, "desktop": true, "source": true, "dependencies": true}`.
GitHub job outputs serialize these booleans as `true` / `false`. Unknown paths,
unavailable diffs, and manual runs select full verification. See `.cursor/rules/ci-scope.mdc`.

### Capture / replay truth (issues #316, #317)

`GET /api/capture` and recording fields in `/api/ibkr/status` describe one
server-owned recording symbol, with `capture_error: string | null` on IBKR status.
Cross-symbol HTTP starts/stops return 409 with
`detail`; the operator must stop the active symbol first.

Sim replay status adds `replay_ok: boolean` and `replay_error: string | null`.
A failed capture selection clears `replay_date` / `replay_symbol`, reports
`replay_source: "synthetic"` with `replay_ok: false`, and never claims a capture
loaded. Capture session listing rows add `empty: boolean`, `usable: boolean`,
and `unavailable_reason: string | null`; empty sessions cannot be selected.

QA 2026-09-22 (fix/qa-sim-replay): replay status adds `replay_loading: boolean`
-- true while a capture selection is still being read from disk, with
`replay_ok: null` and `replay_error: null` (neither loaded nor failed; the feed
matches nothing meanwhile). `POST /api/sim/replay` answers the same envelope as
`GET /api/sim/clock` (clock fields plus replay fields), and the Sim clock
payloads (`GET` / `POST /api/sim/clock`, `POST /api/sim/replay`) add
`replay_quote: {symbol, ts, covered, last, bid, ask, bid_size, ask_size,
prev_close} | null` -- a loaded capture's market at the playhead (null for
anything else), so the Trader's quote head and ticket follow every seek;
`covered: false` is a gap in the recording and every price is null. A capture
read never crosses a gap: inside the stretch that holds the playhead (the
manifest's segments, the open one, and data written past the last segment)
quotes, books and the tape come from that stretch only; in a gap there is no
quote or last, the pushed book is an explicit empty one (`recorded: false`) and
a practice order is refused `SIM_NO_PRICE`. Recorded quote rows (top of book,
`last: null`) load as quotes; odd-lot prints (sale condition `I`) never set a
capture's last or fill a practice order. A listing row whose manifest `source`
is not `ibkr` (the removed synthetic SIM1) is `usable: false` with a reason and
the capture player refuses it; a session whose every segment `failed` without a
print is `usable: false`. Row `prints` / `l2` are the manifest's counts -- the
recorder's live counts while this process records the directory -- and `-1`
when rows are on disk but not counted (rows written past the last segment
included).

### Replay progress and capture fidelity (#321, #337)

Historical job responses add `progress_pct: number`, `downloaded_through: number`
(epoch seconds), `eta_seconds: number | null`, `stale: boolean`,
`age_seconds: number`, and `started: number | null`; `updated` remains the durable
checkpoint time. ETA is an estimate only after advancement in the current run.
Trades jobs and the selection also carry `coverage: [[start, end], ...]` (sorted,
merged, half-open epoch-second ranges of downloaded prints) and
`covered_seconds: integer`; `progress_pct` is covered share of the window and
`downloaded_through` / `coverage_through` stay the end of the range that starts
at the window start. Coverage can have gaps: scrubbing a running download's
selection to an uncovered second makes the worker fetch there next, continue
forward, and backfill skipped gaps from the window start afterwards. The
snapshot adds `covered: boolean` (the playhead's second is downloaded); an
uncovered playhead returns no tape prints, and candles are never built or
flat-filled across a gap.
A complete candles (`bars`) job covers its window (`coverage` is the window,
`progress_pct` 100). The selection's `download_status` is its job's status now,
in the listing and in the snapshot -- a worker that died leaves `running` in
storage, which reads `interrupted`. At the window's (exclusive) end the snapshot
reads the window's last second, and `last` falls back to candles only where the
playhead's own second is not downloaded. That candle close is never a
practice price (QA R34): at an uncovered playhead a Sim practice order is
refused `SIM_NO_PRICE` ("Not downloaded at the replay playhead ...", before
the window has printed it stays "No trade has printed yet") and a protective
close gets flat at the last mark (`fill_basis: "last_mark"`), never
`last_print`.
The snapshot's `open` / `high` / `low` / `volume` count from the window's first
reported print. It adds `session_open: number | null` -- the regular session's
opening print once the playhead has reached 09:30 ET: the first reported print
at or after 09:30:00 inside the downloaded range that covers 09:30:00, else the
stored 1-minute bar that starts at 09:30, else null -- and `stats_scope:
"session" | "window"`: `session` only when the window starts at the session
start (04:00 ET) and the playhead's trades are unbroken from there, so `volume`
/ `high` / `low` are the day's so far; `window` otherwise. The quote card's
Gap% uses `session_open` against `prev_close` and shows Vol / High / Low only
for `session`; anything else is a stated absence, never the window passed off
as the day (QA W7).
Historical snapshot prints include stable integer `ordinal` within the selected job.
The historical SQLite store uses integer `PRAGMA user_version=1`, migrates known
unversioned tables, and refuses unknown versions. Selection refuses oversized
windows above the domain constant instead of silently truncating their prints.

Capture manifests stamp integer `schema_version: 1`. Validated legacy v1 is
migrated; unknown versions refuse loudly. Capture load diagnostics include
`l2_total`, `l2_loaded`, `l2_decimated`, `malformed_rows`,
`invalid_timestamp_rows`, `invalid_rows`, and `legacy_schema`. Recorder
`fidelity` includes `l2_offered`, `l2_coalesced`, `invalid_timestamp_rows`,
`timestamp_regressions`, and `last_stream_ts`. Diagnostics are counts except
`legacy_schema` / `l2_decimated` (booleans) and `last_stream_ts` (per-stream event timestamps).
No automatic retention policy is selected by these additions.

### Recording persistence and coverage (operator decision, 2026-09-21)

A Session Record is owned by the backend process -- up to
`CAPTURE_MAX_CONCURRENT` (3) symbols at once, each by the operator's choice,
because IBKR allows three depth lines and Record holds one per symbol -- and
no page event stops it. `/api/capture` and `/api/ibkr/status` carry
`capture_symbols: string[]` (start order) with `capture_symbol` as its first
entry for single-symbol readers; `/api/capture` adds `sessions: {SYMBOL: {producer,
book, recorder, healthy, error?, warning?}}` and the recorder's own `sessions`
map. A fourth symbol is refused 409 before any IBKR line is touched. What can stop it is a process
restart, a recorder failure, or a lost IBKR line, and the policy for each is
**resume, then say so** -- the market only happens once, so a gap in the
middle beats nothing after it. `capture/keepalive.py` owns this: a restart
whose active-session marker names today's Eastern date and is younger than
`CAPTURE_RESUME_RESTART_WINDOW_SEC` resumes into a new segment once IBKR is
ready; a recorder that stops itself is resumed with backoff
(`CAPTURE_RESUME_BACKOFF_SEC`), at most `CAPTURE_RESUME_MAX_ATTEMPTS` times per
unplanned stop; a recording whose tape line went `disconnected` re-acquires its
IBKR lines when the client is ready again. Resume never crosses a day boundary,
never changes symbol, and is cancelled by an operator Stop or by the operator
starting another symbol.

Every manifest segment carries `reason: "operator" | "rotation" | "failure" |
"restart" | "auto"` naming why it ended (`auto`: auto-record's planned stop, ADR 023) (`restart` is stamped by the startup finalizer,
whose `stopped_et` is the dead process's last write on disk -- `recovered_et`
keeps when the recovery ran).
`/api/capture/sessions` rows add `segments: integer`, `missing_sec: integer`
(seconds between the first segment start and the last segment stop that no
segment covers, except the gaps after a segment the operator stopped --
`reason: "operator"` -- which were not recorded but went missing from nothing),
`last_reason: string | null` and `spans: [[start, stop], ...]`
(whole epoch seconds per segment, sorted; an open segment runs to now). Segment
counts, spans and `replay_load.segments` include the segment still being
written (`stopped_et: null` while this process records it; a manifest still
saying `recording` that no process here advances ends at its last write) and
data written past the last segment's stop (`status: "unlisted"`) -- the
Sim scrubber draws `spans` as a thin recorded lane under the loaded replay, so a
downloaded window shows where Nova itself recorded that symbol. A capture selected for Sim
replay exposes its `segments` list in `replay_load` so the scrubber can draw
recorded stretches against the session and gaps as gaps; a quiet stretch inside
a segment is not a gap -- the recorder was up and the tape said nothing.

`/api/capture` adds `errors: {SYMBOL: string}` and `/api/ibkr/status`
`capture_errors: {SYMBOL: string}` -- each recording symbol's own trouble, so no
reader pins one symbol's tape error on another; `error` / `capture_error` stay
the legacy single value, and a `POST /api/capture` reply's `error` is only the
requested symbol's own trouble (or the writer's).

`/api/ibkr/status` adds `capture_sessions: object[]`, one per recording
symbol (`symbol`, `session_date`, `started_et`, `segment_started_et`, `segment`,
`counts`, `last_write_ts`, `dir`, `reacquired`), `capture_resume: object[]`
(`symbol`, `pending`, `attempt`, `max_attempts`, `next_at`, `reason`, `gave_up`,
`gave_up_reason`) and `capture_stopped: object[]` -- per symbol, the last stop
the operator did not ask for (`symbol`, `at`, `reason`, `error`, `dir`,
`counts`, `resumed`), kept until that symbol records again or the operator
stops it. All three are empty lists while nothing is recording or pending. The UI treats a running recording
as quiet state (chip, hairline, window title) and an unrequested stop as the
loud one.

### Recorded depth in historical replay (#309)

The historical replay snapshot carries `depth_available: boolean` and
`depth: object | null`. `depth` is the Level 2 book the local recorder
(`backend/l2/`) archived at or before the playhead second, shaped
`{symbol, bids, asks, ts, age_sec, l1_fallback, session_id, source}`, where
`source` names the archive (`l2_recorder`). `depth_available` is true only when
`depth` is present. An IBKR historical download carries no book, so an
unrecorded moment reports `depth_available: false` with `depth: null` and is
rendered as a stated absence, never an empty or invented ladder. `bid` / `ask`
stay null — a recorded book is not a quote stream. The lookup never reads ahead
of the playhead, and an unreadable `l2.db` degrades to the unrecorded case
instead of failing the snapshot.

Each snapshot print carries `side: "ask" | "bid" | "between" | null`, `bid` and
`ask` (`number | null`) and `side_source: "recorded_book" | null`, and the
snapshot adds `sides_recorded: integer`. A print gets a side only when `l2.db`
holds a book at or before its (whole-second) timestamp and one at or after the
next second, within `SIM_HISTORY_DEPTH_MAX_AGE_SEC`, and every book in that span
has the same top of book -- the quote provably held across the print's second --
classified by the live tape's own rule (`ibkr/tape_side.py`). Otherwise the side
is `null` and no bid/ask is attached. Unreported prints never get a side. No
side is ever inferred from price movement.

### Desk diagnostics (ADR 021)

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
10 min, then a stated human step). `ibkr/session_errors.last_error()` is
`{code, message, ts} | null` for the last IB errorEvent of any code.

### Why the Gateway needed a phone login; premarket evidence (#14)

IB Gateway's saved login survives only its own `AutoRestartTime` restart; any
end of the process (a PC restart, a crash, closing it) costs a phone login.
`ibkr/relogin_reason.py` explains the latest Gateway start from the IBC log's
`autorestart file (not) found` line and the Windows System event log
(`ibkr/windows_restarts.py`, read-only `wevtutil`, cached per boot):
`{schema_version: 1, reason: "token_reused" | "pc_restarted" |
"gateway_started_fresh" | "unknown", text, login_ts: number | null, restart:
{boot_ts, cause: "windows_update" | "start_menu" | "app" | "unexpected" |
"unknown", label, initiated_ts, process, windows_reason, first_signin_ts} |
null}` (epoch seconds; `null` for anything unrecorded). A restart is claimed
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

### Scanner rows and HOD Momo alerts on the wire (QA batch, 2026-09-22)

The REST scanner routes and `/ws/scanner` (`roster_replace` and the connect
snapshot) serve rows through one pipeline, `scanner_surface.surface_rows`:
blocklisted symbols removed, listing `exchange` attached, reference columns
decorated, Large Cap scored -- a roster push can no longer bring back a
blocklisted ticker or drop `large_cap_score`. Each row may carry
`rvol_source: "yfinance" | "alpaca" | null`, naming the average daily volume
`rel_volume` divides by (null or absent when unreported; the desk then says
so rather than guessing). A price-patch row's existing
`quote_quality: "close_fallback"` means the price is IBKR's prior close with no
trade yet; the desk shows it as such and states no change.
`GET /api/scan/envelope` (owner `routes/scan.py`) answers `rev`, `mode`,
`health` (with `integrations`), `data_feed`, `feed_error: string | null` and
`tables: {gappers | gainers | losers | afterhours | large_cap: {table_state,
roster_ts, last_scan}}` -- never rows. A persistent-authoritative desk (ADR
008), whose rows follow `/ws/scanner`, polls it so mode, health and feed
errors do not freeze at mount.

No socket frame on `/ws/scanner` or `/ws/hod-momo` carries a bare `NaN` /
`Infinity`: a non-finite float is `null` (`scanner_wire.dumps_wire`,
`hod_momo_models.alert_to_dict`). A HOD Momo alert's `id` is
`"<created_ms>-<SYMBOL>-<strategy_id>"`, taken from when Nova raised it
(`created_ts`), so two alerts raised on one stale print never share an id;
`timestamp` stays the trigger print's time. `change_pct` is `number | null`
-- null when the snapshot had none, never an invented 0.0. The HOD debug
snapshots' `last_enriched` is epoch seconds (`time.time()`), `0` when never
enriched. Integration-health `detail` strings are ASCII.

QA pass two (2026-09-22, Scanner / header / layout batch): a cached scanner
row -- and so every REST reply -- carries `quote_quality: "close_fallback" |
null` once an L1 tick has touched it (`ibkr/l1_apply.py`): `close_fallback`
means the price is IBKR's prior close with no print yet, `null` states a
print; a row no tick has touched has no key. A name-only row's `volume` is
`null` until a quote carries one (never a placeholder `0`), and an L1 tick
without a volume leaves the row's volume as it was. The universe gapper
enrichment and the after-hours L1 reprice stamp `rvol_source: "alpaca"` on
the RVOL they divide by the Alpaca IEX average. A gapper / after-hours row
restored from a snapshot has `change_pct` / `change_abs` measured from its
price against the prior close (`null` when either is unknown) -- never its
gap. A HOD alert restored from disk (today's restore and
`/api/hod-momo/history/{date}`) created before `HOD_MOMO_INVENTED_CHANGE_BEFORE_TS`
with `change_pct` exactly `0` reads `change_pct: null` (the pre-fix fill-in);
the archive file is not rewritten. `/api/hod-momo/debug/symbol/{sym}` and
`DELETE /api/hod-momo/blocklist/{symbol}` accept a symbol with a slash
(`BRK/B`). `/api/strategy/*` grades the rows the Scanner shows
(`scanner_surface.surface_rows`: blocklist out, RVOL / float / news in), and a
move past +100% reaches the graders in percent so it is never read as a
fraction under 1.0. Bar-derived sensor readings (`vwap`, `macd`, `emas`,
`last-move`) add `data.bars_as_of` -- epoch seconds of the newest 1-minute bar
they were computed from, `null` without bars -- so the board can say a
reading is stale.

### Scanner leaderboard: recorded, reconstructed, played back (ADR 023, operator decision 2026-09-22)

Owner `backend/leaderboard/`; store `leaderboard.sqlite3` (`PRAGMA
user_version=1`, unknown versions refuse) under `NOVA_LEADERBOARD_DIR`, else
`F:\Nova\leaderboard` when F: is mounted, else `<cache_dir>/leaderboard` --
beside, never inside, the capture root or the historical downloads. One
**leaderboard row** per symbol per minute per board:

`{symbol, minute_ts, board, source, rank, price, prev_close, change_pct,
volume, rvol, rvol_basis, float_shares, has_news, news_first_seen_ts, halted,
gap_pct, exchange, market_cap}` -- `minute_ts` is a whole-minute epoch second
and the row is the board **as it stood at `minute_ts`** (a reconstructed row
uses only minute bars that closed by then; a recorded row is the desk's board
snapshotted within `LEADERBOARD_RECORD_SETTLE_SEC` after it). `source` is
`recorded | reconstructed`; `board` is `gappers | gainers | losers |
afterhours | large_cap` (recorded: the desk's lists through
`scanner_surface.surface_rows`, so blocklisted names never appear) or `market`
(reconstructed: the whole market). `change_pct` is a fraction against the
prior close, computed from `price` and `prev_close` and `null` when either is
unknown (a `close_fallback` row has no print: `price` / `change_pct` null).
`rvol_basis` is `daily_avg` (the desk's RVOL: volume over the average daily
volume) or `time_of_day_20` (volume so far over the same-minute average of the
prior 20 sessions); two bases are never compared. `float_shares` is as known
that day or `null`; `has_news` / `news_first_seen_ts` only from news seen by
that minute. Every unknown is `null`, never a placeholder. `halted` is derived
at read time from the halt log: `true` while a logged halt is open, `false`
only for a recorded minute whose halt feed was answering, else `null`.

**Gap policy.** The recorder runs whenever the backend runs -- no button --
and writes, each minute 04:00-20:00 ET on exchange days, one `minutes` row
(`run_id`, `feed_live`, `halt_feed_ok`) and one `coverage` row per board
(`state: live | frozen | unavailable | feed_down`, `row_count`); a
reconstructed day writes `coverage` with `state: rebuilt`. A minute without a
`minutes` row was not recorded. Playback never carries a board across a gap:
the board at a playhead inside one is `null` with `gap: {reason, start, end,
stop}`, `reason` one of `not_running | feed_down | not_recorded |
outside_session` (`start` / `end` null for `outside_session`), `stop` --
for `not_running` -- `shutdown` (Nova was closed) | `unexpected` | null.
`runs` rows (`run_id`, `started_ts`, `last_beat_ts`, `stopped_ts`,
`stop_reason`) say whether Nova closed or stopped unexpectedly. Rows are
enqueued, never written on the IB loop (ADR 010).

**Halt / LULD log.** `halt_events` rows `{symbol, ts, event: start | end,
kind, code, source: ibkr_ticker_halted | nasdaq_trade_halt_rss,
session_date}` from IBKR tick 49 transitions and Nasdaq Trade Halt RSS rows.
A halt is never inferred from a gap in the prints.

**One ranking** (`leaderboard/ranking.py`, pure): qualify, then order by
`change_pct` (ties: volume, symbol). Playback's `leaders`, the S5 offline
universe and live auto-record call the same function; presets are
`BOARD_RULES`, `LEADERS_RULES` ($3-10, float <= 10M or unknown, volume >=
100k, top 3) and `S5_RULES` (top 3 with `time_of_day_20` RVOL >= 5). A
recorded row's `rank` is the desk's own order of that list (Losers stay
worst-first); a reconstructed row's `rank` is `BOARD_RULES`.

**Routes.** `GET /api/leaderboard/days` -> `{schema_version, store: {path,
ok, error}, days: [{date, recorded: {minutes, first_ts, last_ts, boards} |
null, reconstructed: {minutes, first_ts, last_ts} | null}]}` newest first.
`GET /api/leaderboard/{date}?at=<epoch>&source=` -> `{schema_version, date,
at, source, minute_ts, covered, gap, boards: {BOARD: {state, rows[]}},
leaders: {board, symbols[], rules}}` -- the board at the latest minute at or
before `at` (never after); `source` defaults to `recorded` when that day has
one, else `reconstructed`. `GET /api/leaderboard/{date}/coverage?source=` ->
`{date, source, session_open, session_close, spans: [[start, end], ...],
gaps: [{start, end, reason}]}` (whole epoch seconds). `GET
/api/leaderboard/{date}/halts?until=<epoch>` -> `{date, events[]}`. `GET
/api/hod-momo/history/{date}` accepts `?until=<epoch>` (alerts raised at or
before it, by `created_ts`, else `timestamp`; the reply stays a bare list). `GET /api/history/dates?type=all` lists every date with any saved
board; `type=movers` reads the `gainers-` / `losers-` files. `/api/ibkr/status`
adds `leaderboard_recorder: {recording, ok, error, since, run_id}`.

**Auto-record.** 07:00-10:00 ET the backend records the top
`LEADERBOARD_AUTO_RECORD_TOP_N` `LEADERS_RULES` names of the live Gainers
board through the Session Record path, using only **free** Level 2 lines
(`IBKR_MAX_DEPTH_SYMBOLS` total), and yields its lowest-ranked line the
moment the operator opens Level 2 on another symbol -- the operator never
loses Level 2 (operator decision 2026-09-22). It never starts, stops or
adopts a symbol the operator recorded by hand; its stops are planned
(`reason: "auto"`, excluded from `missing_sec` like `operator`), never a loud
unrequested stop; the operator pressing Record also takes a line back, and a
symbol the operator stopped is not retaken that day. `NOVA_AUTO_RECORD=0`
turns it off. `/api/ibkr/status` adds `auto_record: {active, window,
symbols[], leaders[], yielded[], last_error}`; `/api/diagnostics` adds the
`leaderboard_recorder` and `auto_record` rows (group `recorder`).

**Sim day.** `POST /api/sim/clock {session_date: "YYYY-MM-DD" | null}`
re-dates the Sim clock with nothing loaded -- any loaded replay, of that day or
another, is unloaded (never deleted) so the clock opens the full 04:00-20:00
session (operator decision 2026-09-22) -- and parks it paused at
`SIM_DAY_JUMP_PARK_MIN_ET`; `null` returns to today, unloading a replay of
another date. Off the live edge the Scanner board and the HOD Momo strip read the
leaderboard and the alert history at the playhead; Live and Paper stay on now.
The Sim Day calendar marks, per day and each from its own source, a board
recorded by Nova, the operator's usable Session Records (`/api/capture/sessions`)
and a rebuilt board; a day with none, a weekend or a future day cannot be picked.
`/api/leaderboard/days` lists every day on file (`LEADERBOARD_DAYS_LIMIT` 2,500).

### Setup scanner and tape gate (ADR 022)

`GET /api/setups/board` and the `{"type": "board", ...}` frames of `/ws/setups`
(owner `backend/setup_scanner/`; read-only -- nothing there places, stages or
cancels an order) answer `schema_version: 1`, `generated_at`, `session_date`
(Eastern `YYYY-MM-DD` or null), `universe` (symbols followed: the HOD Momo
active set), `seeding` (symbols still loading today's bars), `scoreboard:
boolean`, `scoreboard_error: string | null`, `proposing: boolean` (false on a
replay desk), `rows[]` (at most `SETUPS_BOARD_MAX_ROWS`; near, armed, triggered
within 30 min, pullback, leg, failed within 5 min, then nearest the trigger)
and `proposals[]` (the open ones). A row is `{symbol, state: "watching" |
"leg" | "pullback" | "armed" | "near" | "triggered" | "failed", reason, kind:
"first_pullback" | "second_pullback", nth, setup_id: string | null, setup:
{leg_t, trigger, entry, stop, risk, target1, pullback_bars, leg_high,
leg_low, leg_pct, armed_bar_t, armed_at, kind, triggered_at?, trigger_price?,
nth?} | null, leg: {t, high, low, pct} | null, last_price, distance: number |
null (trigger minus last, armed and near only), grade: "A" | "B" | "C" | null,
pillars: {price, change_pct, rvol, float, news, headline, catalyst} | null, tape:
{verdict: "go" | "wait" | "veto" | "blind", reasons: string[], line, metrics}
| null, proposal | null, outcome: "target_first" | "stop_first" | "open" |
null, bar_r, mfe, mae}`. An unknown pillar is `null`, never a failed one, and
no frame carries a bare `NaN` (`scanner_wire`). A proposal is `{id, setup_id,
symbol, kind, trigger, entry, stop, target1, risk, grade, reasons, created_at,
status: "open" | "triggered" | "failed" | "disarmed" | "rearmed", tape_now}`
-- raised only when a live setup is `near` and the tape says `go` (a re-arm at
new levels withdraws the open one, and the next `go` raises a fresh one), pushed once as
`{"type": "alerts", "alerts": [...]}` and recorded on the bot audit stream as
`setup_proposal` / `proposed`. Its close is recorded there too (a re-arm
replaces the engine's own copy): `setup_proposal` with outcome `rearmed` |
`disarmed` | `failed` | `triggered`, `reason` the plain-words cause, and
`inputs` the proposal with its `status` and `closed_at` -- the Bots page lists
the last half hour's withdrawn proposals from it. `blind` means Nova holds no
depth line for the symbol; the scanner opens none.
`GET /api/setups/scoreboard?days=N` (default 5, `0` = all) answers `{days,
date_from, row_count, rows[] (at most 500), summary: {all, by: {tape_at_trigger,
grade, session, kind}}}`, each stats block `{armed, triggered, trigger_rate,
target_first, stop_first, open, scored, win_pct, avg_r, avg_net_r, avg_mfe_r,
avg_mae_r}`; `GET /api/setups/rows?date=YYYY-MM-DD&symbol=` one day's rows.
Both answer 503 with the reason while the store is not open. Rows live in
`setups.db` under the operator cache (SQLite, `PRAGMA user_version = 1`; an
unknown version, or an unversioned file that already holds the table, refuses
to open and the board reports `scoreboard_error`), one per armed setup: levels,
grade and pillars at arm time, `near_tape` / `trigger_tape`, the first touch,
MFE / MAE over 15 minutes and `bar_r` under the research exit rules --
scores, never fills.

### Catalysts (ADR 024)

One pure classifier, `backend/catalysts/classify.py` (rules and `CATALYST_RULES_VERSION` in
`constants_catalysts.py`), for the backfilled history and the live desk. An item is
`catalyst` (`strength: "strong" | "weak"`), `negative` (dilution, delisting), `routine` or
`noise` (movers lists, "why is it moving", law-firm adverts, opinion, stock screens, roundups of
more than three tickers). Rules v6: a one-ticker "why is it moving" rewrite is labelled by the
cause its summary names ("... after the company priced a $5 million offering") when that cause
is a placed catalyst or dilution, and stays noise otherwise (no cause, "no news", a peer's news,
a denial, a list of stocks, an analyst piece). A **verdict** for a symbol-day reads only items published after the prior
session's 16:00 ET close and at or before its cutoff: `{verdict: "catalyst" | "negative" |
"routine_only" | "noise_only" | "none_found" | "not_checked", category, strength, title,
source, published_ts, url, negative_too, rules_version}` (plus `sources_answered`, `n_items`).
`none_found` only when a source looked; `not_checked` when none did. The live verdict adds
`news_pending: boolean` (a Nasdaq T1 / T12 halt inside the window with no resumption yet) and
`halt_code: string | null`.

The setup board's `pillars.catalyst` is that verdict at arm time (`catalysts/live.py`:
Alpaca since the prior close, fetched in the background, Finnhub company news since the prior
close (`catalysts/live_finnhub.py`, paced at `CATALYST_FINNHUB_CALLS_PER_MIN` inside the free
tier's shared budget; its Benzinga copies dropped -- Finnhub stamps them four hours early, #516;
`sources_answered` names `finnhub` while a read younger than `CATALYST_FINNHUB_TTL_SEC` covers
the window), plus the live catalyst feed; `null`
when no source looked and nothing was found); `pillars.news` is `true` only for a classified
catalyst, `null` when unknown (nothing read, `news_pending`, or only an unplaced
`company_news` headline) and `false` otherwise; `pillars.headline` is the catalyst's headline
(it was a timestamp). The leaderboard's `has_news` keeps its meaning (an article exists).

**The verdict on the desk** (ADR 024 amendment, operator report 2026-09-23): every scanner row
(REST and `/ws/scanner`, through `scanner_surface.surface_rows`) carries `catalyst: verdict |
null` -- the live verdict as `{verdict, category, strength, title, source, published_ts, url,
negative_too, rules_version, sources_answered, n_items, news_pending, halt_code}`
(`catalysts/live.WIRE_KEYS`), `null` while no source has read the symbol (unknown, never "no
news"). Owner `catalysts/board.py`: an in-memory map recomputed off the loop every
`CATALYST_BOARD_INTERVAL_SEC` for the current rosters and stamped at read time. `has_news` /
`newest_headline_at` stay on the row with their old meaning. The News column, the "Has news"
chip (company news: a catalyst, dilution / a reverse split, or a halt for news; unread rows
kept), the Trader tab's chip, the HOD strip's flame and `/api/strategy/*`'s catalyst pillar and
score read `catalyst` when the row has it; a row without the key keeps the headline flame.
`GET /api/catalysts/{symbol}` (owner `catalysts/routes.py`, read-only; reads Alpaca and Finnhub
for the symbol first when a read is missing or stale; one release carried by several sources is
listed once, from the best-ranked source) answers the Trader's News panel: `{schema_version:
1, symbol, generated_at, window_start, verdict: verdict | null, items: [{item_id, source,
publisher, published_ts, title, url, kind: "catalyst" | "negative" | "routine" | "noise",
category, strength, dilution}], items_total}` -- items since the prior close, newest first, at
most `CATALYST_PANEL_MAX_ITEMS`.

**The live catalyst feed** (`backend/catalysts/feed.py`, always on; `NOVA_CATALYST_FEED=0`
off; ADR 024 amendment) records SEC EDGAR's latest filings, GlobeNewswire, PR Newswire,
Newsfile and FDA into `catalyst_feed.sqlite3` under `NOVA_CATALYST_DIR`, else
`F:\Nova\catalysts` when F: is mounted, else `<cache>/catalysts` (owner
`catalysts/feed_store.py`; `PRAGMA user_version = 1`, unknown versions refuse): `items` and
`item_tickers` in the research store's shape, and `coverage (source, start_ts, end_ts)` --
unbroken reading of a source, extended only when a poll reached back to the previous one. A
feed source counts in `sources_answered` only where a span covers the whole window.
`/api/diagnostics` adds the `catalyst_feed` row (group `recorder`) with
`evidence.sources: {name: {last_ok, last_error, items, gaps, covering_since}}` and
`evidence.finnhub: {enabled, pending, symbols, last_ok, last_error, reads}` (the Finnhub reader).

The research store `F:\Nova\catalysts\catalysts.sqlite3` (`NOVA_CATALYST_DIR`; `PRAGMA
user_version = 1`, unknown versions refuse; owner `research/catalysts/`, never read by the
backend) holds `targets (ticker, session_date, window_start, cutoff, window_end, origin)`,
`items (item_id "<source>:<id>", source edgar | alpaca | finnhub | massive, published_ts,
title, summary, url, publisher, n_tickers, form, sec_items, fetched_ts)`, `item_tickers`,
`checks (ticker, session_date, source, status ok | error | unavailable | out_of_range,
n_items, detail, checked_ts)` and `verdicts` per rules version. SEC's bulk
`submissions.zip` and `companyfacts.zip` are kept beside it under `edgar/`, Nasdaq's halt
pages under `halts/raw/`. Nasdaq's halt history (2021-10 on) is loaded into the leaderboard's
`halt_events` (source `nasdaq_trade_halt_rss`) by `research/catalysts/backfill_halts.py`.

### Performance recorder (ADR 026)

Owner `backend/perf/`; always on, read-only (it measures, never throttles or
sheds). One **sample** per second, in memory for `PERF_RING_SEC` (1800 s):

`{schema_version: 1, ts, interval_sec, process: {cpu_pct: number | null,
threads}, loops: {ib | http: {cpu_pct: number | null, delay_max_ms: number |
null, stalled: boolean}}, ops: {NAME: {calls, busy_ms}}, gauges: {NAME:
number}, gc: {collections: [gen0, gen1, gen2], pause_ms, max_pause_ms}}` --
`cpu_pct` is CPU time over wall time (100 = one core; `process` covers every
thread, which share one GIL); `delay_max_ms` is the longest a 50 ms watchdog
callback waited on that loop in the interval (`null` before the watcher runs);
`ops` are the interval's deltas of `op_metrics` operations that ran (a sync
op's `busy_ms` is time on its thread, an async `ws.*` op's is fan-out wall
time; operations nest); `gauges` are queue depths and cumulative drop counters
(`*.dropped` never decreases in a process). A loop whose callback waited more
than `PERF_STALL_MS` is **stalled**; its **stall report** is `{schema_version:
1, id: "<started_ms>-<loop>", loop, started_ts, ended_ts, duration_ms,
samples, truncated, top_frame: string | null, stacks: [{count, frames:
["path:line function", ...]}], before: sample[], after: sample[]}` -- frames
outermost first, `top_frame` the most-sampled innermost frame inside the repo,
`before` / `after` the samples 30 s either side. A **stall summary** is the
report without `stacks` / `before` / `after`, plus `file: string | null`.

`POST /api/perf/client` takes one window's 5 s report (at most
`PERF_CLIENT_MAX_BODY_BYTES`; the sample desk never sends): `{schema_version:
1, window_id, role: "main" | "popout" | "browser" | "electron", visible:
boolean | null, interval_sec, ui_tag: string | null, frames: {count, slow,
p95_ms} | null, long_frames: {count, blocking_ms, max_ms, top: [{source,
invoker, ms}]} | null, sockets: {NAME: {messages, bytes}}, renders: {NAME:
count}, heap_mb: number | null, dom_nodes: number | null, processes: [{type,
window_id, pid, cpu_pct, working_set_mb}] | null}` -- `frames` counts
animation frames while visible (`slow` > `PERF_SLOW_FRAME_MS`), `null` while
hidden; `processes` only from the Electron main process. The server stamps
`received_ts` and answers `{ok: true}`.

`GET /api/perf/live?seconds=N` (default 300) -> `{schema_version, generated_at,
recorder: {running, since, dir, write_dropped, stall_files_skipped,
write_error}, samples[],
stalls: summary[], clients: {window_id: report}}`. `GET /api/perf/stalls` ->
`{schema_version, stalls: summary[]}` (this process, newest first); `GET
/api/perf/stalls/{id}` -> the report (404 unknown). Kept under
`<cache_dir>/perf/`: `YYYY-MM-DD.jsonl` (Eastern date), one JSON object per
line with `schema_version` and `kind: "sample" | "client" | "stall"` -- a
`sample` line aggregates `PERF_PERSIST_EVERY_SEC` (5) seconds (ops and gc
summed, `cpu_pct` averaged, `delay_max_ms` maxed, gauges last) -- and
`stalls/<id>.json`; both removed after `PERF_RETENTION_DAYS`. A reader skips
and counts a line of unknown `schema_version`, never guesses. `/api/diagnostics`
adds group `performance` (rows `perf_process_cpu`, `perf_ib_loop`,
`perf_http_loop`, `perf_stalls`, `perf_queues`, `perf_windows`,
`perf_handlers`; one `unknown` row while the recorder has no samples).

### Watchlist rows (operator decision 2026-09-23)

`GET /api/strategy/watchlist` entries keep `symbol`, `composite_score`,
`sub_scores` and `five_pillars`, and add the scanner row's own market facts --
`price`, `change_pct` (a fraction against the prior close, also past +100%),
`rel_volume`, `rvol_source`, `float_shares`, `has_news` (the scanner's article
flag) -- each `null` when unknown, never a placeholder, and `catalyst:
{verdict, category, strength, title, source, published_ts, news_pending} |
null`: today's verdict from `catalysts/live.py` (ADR 024), `null` while no
source has looked (unknown, not "no news"). Asking queues the Alpaca fetch in
the background (`strategy/watchlist_catalyst.py`); the route never waits on
the network. The Watchlist table joins the setup board (`/ws/setups`) and the
bot allowlist by symbol on the client; nothing on the Watchlist places.

**Any symbol's pillars (operator ask 2026-09-23).** `GET
/api/strategy/watchlist/{symbol}` (owner `strategy/symbol_pillars.py`,
read-only, no network wait) answers `{note, symbol, source, rank, entry}` --
`entry` a watchlist entry as above, graded from the symbol's own scanner row
when a board holds it (`source`: `gappers` | `gainers` | `losers` |
`afterhours` | `large_cap`, surfaced exactly as the Scanner shows it), else from
its live L1 quote decorated the same way (`source: "quote"`: price, volume and
the line's tick-9 prior close from `ibkr.ticks.last_quotes`, whose rows add
`prev_close` once IBKR sends it; float / RVOL from the fundamentals cache; the
catalyst verdict read before grading). `rank` is its 1-based place on the
ranked watchlist, else `null`. A fact nobody holds stays `null` and its pillar
fails with that reason. The quote panel's Watchlist strip uses the ranked entry
when there is one and this route for every other symbol.

### Bot playbook and the read-out gate (ADR 027, operator decision 2026-09-23)

The bot packs (halt-luld, quote-spike, volume, llm-decide), `POST
/api/bot/llm/spend` and the `nova-brain` sidecar are retired. The bot session
file is `schema_version: 4`; a v1-3 file loads with `active_pack`,
`pack_settings` and `llm` stripped. `GET /api/bot/session` drops those keys
and adds `setup` (the setup that plays: `first_pullback`), `setups: [{id,
scanner: boolean}]` (`first_pullback`, `gap_and_go`, `flat_top_breakout`,
`red_to_green`, `micro_pullback`; only a setup with a scanner can be chosen --
`PATCH {setup}` otherwise `400 BOT_SETUP_NO_SCANNER`), `readout` and `gates`.

`readout` (owner `setup_scanner/readout.py`, cached 30 s) is `{state:
"collecting" | "passed" | "not_passed" | "failed" | "unavailable", passed,
reason, go: {triggered, scored, win_pct, avg_net_r}, control: {...}, rules:
{kind, min_go, fail_go, min_net_r}}` over every `setups.db` row of kind
`first_pullback` that triggered: `go` are those whose tape was go at the
trigger, `control` those blind or wait (pooled). It passes when at least 50 go
setups triggered and their average net R is above +0.2 and above the
control's; it is judged on the first 100 go setups, and 100 without a pass is
`failed`. A closed store is `unavailable`. While it has not passed, raising to
Strategy lands not active, `POST /api/bot/session/arm` at Strategy and every
`POST /api/bot/action` are refused `409 BOT_READOUT_NOT_PASSED`, and
`live_fire_ready` is false. At Strategy a `buy_*` kind is also refused outside
07:00-10:00 ET on the venue's clock (`409 BOT_OUTSIDE_WINDOW`) and after one
bot entry that venue day (`409 BOT_DAY_TRADE_CAP`; entry audit rows carry
`inputs.venue_day`); exits and cancels are never held by either. Proposals
are accepted at Eyes and Strategy. `gates: [{id, ok, stage: "activate" |
"fire", detail}]` (owner `bot/gates.py`) are `level`, `allowlist`,
`desk_armed`, `depth_lines`, `readout`, `bot_trip`, `day_lock`,
`kill_switch`, `window`.

### Input Payload (Raw)

```json
{
  "symbol": "AAPL",
  "previous_close": 150.00,
  "current_price": 155.00,
  "gap_percent": 3.33,
  "volume": 1200000,
  "timestamp": "2026-04-14T08:30:00Z"
}
```

### Output / Delivery Payload

```json
{
  "health": {
    "status": "connected",
    "latency_ms": 45
  },
  "gappers": [
    {
      "symbol": "AAPL",
      "previous_close": 150.00,
      "current_price": 155.00,
      "gap_percent": 3.33,
      "volume": 1200000
    }
  ]
}
```

Capture market projections preserve missing facts: print-only rows have null
bid/ask/sizes/previous close; depth is empty without recorded books; daily OHLC
is null unless a replay source provides it. Loading, failed, and pre-first-event
capture selections have no market data to fall back to -- there is no synthetic
instrument (ADR 019), and `replay_source` is `none` when nothing is loaded.

### Practice venues and fills (ADR 019, ADR 020)

The desk venue is `live | paper | sim` (`desk-venue.json` `schema_version: 2`,
`{"venue": ...}`; owner `sim/mode.py`). **Paper is Nova's practice account on
the live feed** (ADR 020): orders enter `execution.service.execute` unchanged
and are filled by the practice broker against the live reference (fresh L1
last, live top of book, live tape prints for resting orders); the account is
the persistent ledger `practice-paper.json` (operator cache, `schema_version`)
with IBKR-like commissions and fees, enforced buying power, day P&L rolling at
04:00 ET and per-source attribution. **Sim trades the loaded replay** (ADR
019) on a scratch, event-sourced account: scrubbing backwards unwinds every
order and fill placed after the new playhead; unloading clears it. The IBKR
paper Gateway (4002) is legacy and never the meaning of the Paper venue.

`GET /api/practice/account?venue=paper|sim` and `POST /api/practice/reset`
carry the account (`account_id` `NOVA-PAPER` / `NOVA-SIM`, `starting_cash`,
`cash`, `buying_power`, `net_liquidation`, `gross_position_value`,
`realized_pnl` (lifetime, since the ledger opened), `unrealized_pnl`, `day_pnl`,
`realized_today` (net of fees, since the 04:00 ET practice-day boundary), `day_started_et`,
`commissions_today`, `positions[]`, `working[]`, `fills_today`,
`schema_version`, `updated_at`; Sim adds `replay_key` -- the ledger's replay binding as a list `[source, symbol, date, start?, end?]`, e.g. `["historical", "GDC", "2026-09-21", "09:15", "11:30"]` or `["capture", "GRML", "2026-09-21"]`, `null` with nothing loaded; never a string a client may call string methods on); `/api/ibkr/account`
and `/api/ibkr/positions` answer from it on the practice venues, where the
summary's `RealizedPnL` is **today's** realized (IBKR's own daily meaning) and
`DayPnL` is the ledger's day P&L -- the figure the bot breakers compare with
the day lock there, with no commission subtracted twice (QA W2);
`/api/ibkr/status` adds `venue` and reports `account_id` `NOVA-PAPER` /
`NOVA-SIM` there. A filled practice row carries `fill_estimated: true` and
`fill_basis: "quote" | "last_print" | "print_cross" | "stop_trigger" |
"last_mark" | "live_quote" | "live_print"`; a practice fill is never displayed
as a recorded print. Refusals: `SIM_NO_REPLAY`, `SIM_SYMBOL_MISMATCH`,
`SIM_NO_TRADES`, `SIM_NO_PRICE`, `SIM_ORDER_TYPE` (Sim),
`PRACTICE_NO_LIVE_PRINT` (Paper: no fresh last and no recent tape print --
never a guess), `PRACTICE_BUYING_POWER` (both), `PRACTICE_NO_SHORTS` (both:
a SELL is only ever risk-reducing -- a SELL beyond the held quantity or any
`short_entry` is refused "Nova does not support short entries yet") and
`PRACTICE_TIF_EXPIRED` (both: a `DAY` order expires at its session's close --
20:00 ET on Paper, the replayed window's end on Sim -- as an `expired` ledger
event with status `Expired`; `GTC` persists across days and restarts; the row
and its `placed` event carry `tif` and `expires_ts`). Recorded prints carry
`ts_source: "exchange" | "receive"` so a substituted arrival time is never read
as the exchange's own. Practice order rows stamp `submitted_at` /
`updated_at` / `filled_at` with the venue's time -- the replay playhead on Sim,
the clock a rewind unwinds by -- and a paused Sim playhead scrubbed forward
still fills resting orders on the prints it crossed. Rules and biases: `architecture/practice-fills.md`;
fees and margin: `architecture/practice-account.md`.

**Orders (Today) belongs to the desk's venue** (QA batch, 2026-09-22):
`/api/ibkr/orders/closed` on Paper and Sim is the practice ledger's own closed
rows **that closed during the venue's practice day** -- at or after the 04:00 ET
rollover of the venue's clock, the wall clock on Paper and the replay playhead
on Sim, judged by each row's `updated_at` (its close stamp; `practice/today.py`,
QA W4) -- newest first, with nothing joined or appended from the execution ledger
(`execution/closed_blotter.py`); the ledger itself keeps every row for the
Account history and the startup sweep, and working orders are never day-scoped.
A refused execution row and its receipt carry `mode` = the practice venue
(`paper` / `sim`) on Paper and Sim, like a filled practice row -- never the
Gateway label (QA R38, `execution/desk_mode.py`). The execution ledger holds every venue's
orders and its `mode` stamp is the venue for a practice send and the Gateway
port label (`live` / `paper`) for an IBKR send. On Live only rows stamped with
the session's own label (or unstamped legacy rows) are joined or listed, and
on the by-hand paper Gateway a Paper practice row is told apart by its
`(order_id, nova_placed_at)` pair. A leftover ledger row carries `limit_price`
for LMT / STP LMT and `stop_price` for STP / TRAIL (the trail amount), never a
stop as a limit; `filled_at: null` (the ledger keeps no wall-clock fill time)
and `updated_at` its last activity; a ledger `filled` row is never
`Inactive`. The fill-audit join (`execution/fill_audit_attach.py`) uses only
this desk's execution rows, a remembered audit only when its symbol and venue
stamp match the row, and a practice row's own `nova_placed_at`. A practice
order row has `commission: null` until it fills (a cancelled or expired row
keeps `null`); practice order ids are never reused -- not after a Sim unwind,
and not after a reset or a replay unload / load either: a replacing ledger
continues its predecessor's ids, and `practice-paper.json` carries an optional
`first_order_id` (read as 1 when absent) so they continue across a restart (QA
R41); a resolved practice order -- filled, cancelled, expired, unwound, reset,
or dropped with its ledger when the replay is unloaded or another one loaded
(QA R40) -- releases its `execution.inflight` commitment; and an order the
practice broker fills inside the send marks its own execution row `filled`,
since the broker's notice ran before that row carried the order id (QA R41).

**The ledger as history (the Account page):**
`GET /api/practice/history?venue=paper|sim&range=1D|5D|1M|3M|YTD|ALL`
(default `1D`; owner `practice/history.py`, a pure derivation from the ledger
events -- no live mark is ever read or invented) answers `venue`,
`account_id`, `range`, `range_start` (epoch of the first practice day the
range covers, `null` for `ALL`), `schema_version: 1`, `starting_cash`,
`ledger_opened_at` (ISO ET) and:

- `equity[]` -- `{ts, net_liquidation, cash, realized, unrealized}`, one point
  **after every `filled` and `rollover` event** inside the range, in event
  order, every held position marked at its own last fill price. Nothing is
  drawn between events, so a flat stretch is flat; the series is
  event-marked, so its last point can differ from the live-marked
  `net_liquidation` on `/api/practice/account`. The baseline before the first
  point is `starting_cash` at `ledger_opened_at`.
- `fills[]` -- `{ts, order_id, symbol, side, qty, price, source, bot_id,
  commission, fees, realized, fill_estimated: true, fill_basis}`; `fees` is
  the SEC + FINRA pass-through on that fill and `realized` that fill's own
  contribution net of its fees, read from the ledger's cost basis.
- `by_source[]` -- `{source, bot_id, realized, fills, commissions, fees}` per
  distinct `(source, bot_id)` stamp, first-fill order; the `realized` values
  sum to `components.realized`. Read from the stamps, never inferred.
- `daily[]` -- `{date, realized, commissions, fees, fills, archived}` keyed on
  the practice day (04:00 ET rollover, `practice/clock.day_start_ts`), dates
  ascending; a day with no fill has no row. Archived Paper ledgers' days are
  included flagged `archived: true`, so one date can carry two rows (a reset
  mid-day) and the calendar sums them.
- `archives[]` -- `{file, opened_at, closed_at, realized, days}` for every
  `practice-paper-<stamp>.json` beside the Paper ledger under the operator
  cache, read read-only, oldest first; `days` counts the practice days that
  hold a fill. A damaged or unknown-version archive is skipped with a logged
  warning and named in `warnings: string[]` -- never a 500.
- `components` -- `{realized, unrealized, commissions, sec_finra_fees,
  bot_realized}`; `bot_realized` is the realized on fills stamped `source:
  "bot"` or carrying a `bot_id`; `unrealized` is the event-marked figure at
  the end of the ledger.

`range` bounds `equity` / `fills` / `daily` at the practice-day start that
many **calendar** days before today's (`1D` = 1, `5D` = 5, `1M` = 30, `3M` =
90 -- a weekend inside the window simply holds no session), Jan 1 04:00 ET of
the practice day's year for `YTD`, nothing for `ALL`; today is the venue's
clock (the replay playhead on Sim). `by_source` and `components` cover **this
ledger's** fills inside the range -- an archived ledger is another account and
contributes `daily` rows and its `archives` entry only. Sim answers from its
scratch ledger with `archives: []`; nothing loaded is the shape with empty
lists, never a guess. Unknown `venue` or `range` is a 400. Constants:
`constants_practice.PRACTICE_HISTORY_*`.

### Sim at now is live -- the live edge (ADR 020 amendment, operator decision 2026-09-21 evening)

The Sim clock payload (`GET /api/sim/clock`) and `/api/ibkr/status` on the Sim
venue carry `live_edge: boolean` -- true while the playhead follows the wall
clock on today's Eastern date inside the session window (not paused, not
scrubbed, no past-day replay loaded). It is the single truth for what a Sim
tab shows and fills against. **At the edge** a Sim tab shows the live IBKR
feed exactly as a Paper tab does (quote, Level 2, Time & Sales, live bars),
holds a real depth line the way a Trader tab does (so `BOT_NO_DEPTH_LINE`
gates a bot identically), and the Sim scratch account fills against Paper's
live reference: any symbol with a live print is admitted
(`PRACTICE_NO_LIVE_PRINT` otherwise), `fill_basis` `live_quote` / `live_print`
at placement and `print_cross` / `stop_trigger` for resting orders on live
tape prints; `SIM_NO_REPLAY` / `SIM_SYMBOL_MISMATCH` apply off the edge only;
every fill stays `fill_estimated: true`. **Off the edge** every read is the
loaded replay, and with nothing loaded the desk is a stated absence. Orders
at the edge are stamped with the playhead (wall time there) and unwind like
any other when the operator scrubs back past them. `POST /api/sim/clock` may
carry `symbol` (the scrubbing tab): a scrub or pause that leaves the edge
with nothing loaded selects that symbol's usable Session Record for today
when one exists, keeping the playhead and the scratch account. "Follow wall
clock" returns to the edge. Paper remains the persistent-ledger venue.
Rules: `architecture/practice-fills.md` ("The live edge").

Off the edge a capture replay's Level 2 socket reserves the replay depth slot
the bot gate reads; a historical replay's Level 2 reads the snapshot instead,
so it holds the slot explicitly (QA R44): `POST /api/sim/history/depth-line
{symbol, hold: boolean}` (owner `sim/history_depth_line.py`) answers `{ok,
held, reason, symbols}`. `hold: true` reserves the slot only on a replay desk
and only for the loaded historical window's symbol (`ok: false` with the
`reason` otherwise); `hold: false` drops it unless a depth socket, a live line
or a recording still uses it. It opens no IBKR line and pushes or records no
book. The panel holds it while mounted and re-asserts it every
`SIM_HISTORY_DEPTH_LINE_REFRESH_MS`.

### Who may arm the desk (ADR 018 amendment, operator decision 2026-09-23)

`POST /api/ibkr/arm` takes `{armed: boolean, pin?: string, actor?: "operator" | "bot"}`
(`actor` defaults to `operator` and is a label, never a permission). `armed: false`
always succeeds. `armed: true` on Live needs the operator's PIN, checked by
`ibkr/arm_pin.py` against `NOVA_LIVE_ARM_PIN_HASH` in `.env`
(`pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>`, written by
`tools/set_live_arm_pin.py`; re-read on each check, so no restart). Paper and Sim
arm with no PIN. A refusal is `403 {detail, code}` with `code` one of
`ARM_PIN_REQUIRED | ARM_PIN_NOT_SET | ARM_PIN_INVALID | ARM_PIN_LOCKED`
(`ARM_PIN_MAX_FAILURES` wrong PINs in a row lock Live arming for
`ARM_PIN_LOCKOUT_SEC`). `/api/ibkr/status` and the reply add `arm_requires_pin:
boolean` (the desk's venue needs the PIN), `live_arm_pin_set: boolean` and
`armed_by: "operator" | "bot" | null`; `armed` is true only on the venue the latch
was armed on. The PIN is never in the repository or the frontend.

### Account identity on `/api/ibkr/status` (operator ask, 2026-09-21)

`account_id: string | null` is the first IBKR managed account of the connected
session (`DU…` paper, `U…` live) and `account_ids: string[]` all of them; both
are empty while disconnected. They name *what Nova is logged into*, next to
`broker_account_kind`; the header shows the id beside Cash / Margin. IBKR's API
never exposes the login username, so the account id is the identity Nova can
state truthfully.

### Prints that set a price (operator report, 2026-09-23)

Each live AllLast print on `/ws/ibkr/tape/{symbol}` gains two fields, and so does each Session Record print row: `unreported: boolean` (IBKR's `tickAttribLast.unreported`) and `sets_price: boolean`. `sets_price` is false when IBKR flags the print unreported, or when its sale conditions carry a code that never moves the consolidated high / low / last:

- `C` cash, `H` price variation, `I` odd lot
- `M` / `Q` official close / open, `N` next day
- `P` prior reference, `R` seller
- `U` extended hours out of sequence
- `V` / `7` contingent, `W` average price
- `4` derivatively priced, `9` corrected close

The owner is `backend/sale_conditions.py`; the codes live in `constants_tape.py`. Time & Sales shows every print. Every candle Nova builds from prints uses only the prints that set a price, volume included, because IBKR's own TRADES bars count the same prints. That covers the Trader's client 10Sec bar, `ibkr/tape_10sec`, the archive 1m builder, the recorder's bar buckets and a capture replay's print-built candles. A row without the fields (an older recording) is judged by its conditions.

The L1 last every quote reader takes (`ibkr/ticks_handler.py`) is IBKR's Last (tick 4, or 68 delayed). It is never the RTVolume or AllLast price that ib_async also writes into the one `ticker.last` it keeps per contract. A line that has not yet delivered a tick 4 falls back to `ticker.last`.

### Symbol directory for the header search (operator ask, 2026-09-23)

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

### Execution command (ADR 007 — sole broker mutation entry)

All buy/sell/cancel/replace requests enter `execution.service.execute` with:

```json
{
  "operation": "place | bracket | cancel | replace",
  "idempotency_key": "stable-client-or-ticket-key",
  "source": "manual | kill | cancel_working | flatten | benchmark | bot",
  "symbol": "AAPL",
  "side": "BUY",
  "qty": 1,
 "order_type": "MKT | LMT | STP | STP LMT | TRAIL",
 "limit_price": null,
 "stop_price": null,
 "target_price": null,
 "entry_price": null,
 "order_id": null,
 "short_entry": false,
 "tif": "DAY | GTC",
 "outside_rth": false,
 "intent": null
}
```

`STP LMT` requires both `limit_price` and `stop_price`. `TRAIL` uses `stop_price` as the IBKR trail dollar amount (`auxPrice`); trail percent is not a ticket field. `tif` defaults to `DAY` (`IBKR_ORDER_TIF_DEFAULT`), so a caller that omits it is unchanged; anything outside `DAY | GTC` is refused `TIF_INVALID`. `place` and every `bracket` leg carry `tif` and `outside_rth`; `replace` keeps the working order's own TIF. **Market orders need regular hours** (operator decision, 2026-09-21): a `MKT` place from a non-protective source is refused `MKT_OUTSIDE_RTH` ("use a limit at the ask") whenever the venue's clock is outside weekday 09:30-16:00 ET, NYSE holidays excluded -- no US exchange takes an unpriced order then and IBKR would hold it until the next open (Warning 399) while ignoring `outsideRth` on it (Warning 2109). The clock is the venue's (the replay playhead on Sim). Owner `execution/session_gate.py`; the practice broker repeats the check (`practice/order_rules.py`). Protective sources are exempt (flatten plans an extended-hours limit); `STP` orders are unchanged.

**The ticket's Flatten** (QA R32 / R42, 2026-09-22): `POST /api/ibkr/order` may carry `intent: "flatten"` -- the rail's Flatten, the quick-bar Flatten and the `exit_pos` / `cancel_and_exit` Nova Actions send it. The route sends it as source `flatten` with `ExecutionCommand.intent: "flatten"` (a protective source: never clamped by the test quantity gate and placeable while disarmed, like KILL), and the execution door accepts it, inside the execution lock, only when it closes shares not already being closed -- the side reduces the venue's own position, and the size does not exceed that position less the closing orders already working on the venue (open orders) or committed and not yet listed; no `short_entry` and no legs. Anything else is refused `FLATTEN_NOT_A_CLOSE` before any send ("cancel that order first, or use KILL" when a close is already working), so two flattens can never both fill into a short. The practice broker also cancels, at the fill, a SELL that would fill past what is held (`PRACTICE_NO_SHORTS`). A protective order that fills inside the send frees its in-flight commitment at once (QA R31).

**Manual-ticket protective legs** (operator decision on #91, 2026-09-20 -- supersedes "OCO / bracket stay off the manual ticket"): OCO stays off the manual ticket. A bracket reaches it only as the operator's optional default take-profit / stop-loss from Settings > Trade (`nova.trade.defaults.v1`), **off by default**. When on, an opening **Limit** entry (BUY while not short, or SELL with `short_entry`) posts `take_profit_price` + `stop_loss_price` with its `/api/ibkr/order` request, and the route sends `operation: "bracket"` (`entry_price` = the limit) through the same `execution.service.execute` -- never a second place path. Other entry types are refused while the defaults are on rather than sent unprotected; exits never carry legs; protective sources (`flatten`, `kill`, `cancel_working`) are refused a `bracket`. A bracket is checked like a place: whole shares, side agrees with `short_entry`, leg prices on the correct side of the entry, BuyingPower for a long entry, and no long bracket while the account is short that symbol.

Receipt includes stage timings (`validation_ms`, `persisted_ms`, `broker_sent_ms`, `broker_ack_ms`, `filled_ms`).
Paper and live share this path; only Gateway credentials/port and safety gates differ. `auto_live` remains rejected -- a spend command whose `source` is not one of the listed values (e.g. `auto_live`) is refused `SOURCE_INVALID`; so are `approve` and `auto_paper`, the retired Phase D executor's sources (ADR 025), while ledger rows that already carry them still read. Short opening requires `short_entry: true` plus `IBKR_SHORT_ENABLED` and fresh IBKR shortability (ADR 009).

**Kill switch** (D-037, ADR 025; owner `backend/kill_switch/`): a persisted latch (`kill_switch_state.json` under the operator cache, `schema_version: 1`; unreadable or unknown version reads tripped) that `execution.service.execute` checks before every `place` / `bracket` from a non-protective source, manual and bot included -- refused `KILL_SWITCH`; `kill`, `flatten`, `cancel_working` and every cancel still reach the broker. `GET /api/kill-switch` -> `{tripped, reason, ts}`; `POST /api/kill-switch` trips it (latch first, then every working order on the account is cancelled through the `kill` source) and answers the status plus `cancelled_order_ids` / `failed_cancel_order_ids`; `POST /api/kill-switch/reset` clears it and is the only thing that does. A trip writes a `kill_switch` receipt to the event log. The control is a card on the Bots page. The header's Emergency KILL (bot to L0, desk lock, cancel, flatten) is a separate composite. The Nova OS verdict, the `signal | confirm | auto_paper` ladder, the staged approval queue and `/api/strategy/executor/*` were removed (ADR 025).

---

## 4. 🔗 Integrations & Services

| Service | Purpose | Status |
|---------|---------|--------|
| Alpaca API | News + listing metadata (not price discovery) | ✅ Verified |
| IB Gateway (local) | Scanner discovery + market data + optional orders | ✅ Verified |
| Web UI (Localhost / Desktop) | Delivery dashboard for gappers | ✅ Verified |
| yfinance | Fundamental data (float, short interest, etc.) | ✅ Verified |

---

## 5. 📋 Behavioral Rules (Enforced)

### Advisory verification policy (owner override, 2026-09-20)

All CI and local verification is advisory for delivery. Ready PRs may merge while
checks are running, or after failed/cancelled/missing checks. Do not wait for tests,
builds, or Desktop pack before merging. Report observed results truthfully; red
checks remain visible and can be fixed later. This policy supersedes older
verification-before-merge wording in this constitution and its delivery rules.
Drafts, `do-not-merge`, forks and actual conflicts retain their existing holds.
Master protection blocks force-push and deletion (including admins), with **no
required status checks**. Trading runtime gates, opt-ins and `auto_live` NO-GO
remain unchanged. Conditional coverage is specified in `.cursor/rules/ci-scope.mdc`.

- **Market data / trading:** Scanner and prices are IBKR-only (see `single-market-data-feed.mdc`). Alpaca is news/listing metadata only. Orders are allowed only via gated `backend/ibkr/` (Invariant #7). Gateway port default is live (4001); the paper Gateway (4002) is legacy, by hand only, never an automatic fallback (ADR 020). Spend stays gated; `auto_live` remains NO-GO. Header Live / Paper / Sim are **venue** pills (ADR 020): **Live** places to IBKR; **Paper** is Nova's practice account on the live feed -- fake money, full live data, fills estimated locally, never an IBKR place; **Sim** replays a **real recorded or downloaded session** and fills locally on a scratch account that unwinds when the playhead is scrubbed back (ADR 019); at the **live edge** -- the Sim clock following the wall clock on today's date, not paused, not scrubbed, no past day loaded (`live_edge` on the clock payload and on `/api/ibkr/status`) -- a Sim tab shows the live IBKR feed exactly as a Paper tab does and the scratch account fills against the live reference, and scrubbing back leaves the edge for the loaded replay (today's Session Record when one exists, a stated absence otherwise; ADR 020 live-edge amendment). The IBKR paper Gateway (4002) is legacy with no desk button -- `POST /api/ibkr/gateway-mode {"mode":"paper"}` by hand is its only door. The venue never changes the bot: operator and bots are gated identically everywhere, and a bot fires only on an allowlisted symbol whose depth line the backend itself holds (`409 BOT_NO_DEPTH_LINE` otherwise); after a Sim rewind (`practice_rewind`) bots re-read the ledger. There is no synthetic instrument: a Sim desk with nothing loaded is empty off the live edge, and live at it. `NOVA_BROKER=sim` is bootstrap only. Switching to Live restores the IBKR paths.
- **Desk venue vs spend arming (ADR 018, #302):** two facts with opposite lifetimes, never one dial. The **venue** (Paper / Live / Sim) is durable -- `sim/mode.py` owns `desk-venue.json` under the operator cache (`schema_version`, unknown version refuses loud), and it wins over the `NOVA_BROKER` bootstrap default. **Spend arming never survives a process start**, in any venue: `IBKR_ORDERS_ENABLED` / `IBKR_LIVE_TRADING_CONFIRMED` say this desk is *permitted*, the runtime latch in `ibkr/safety.py` says it is currently *armed*, and a place needs both. Arming is an explicit act through one door, `POST /api/ibkr/arm`, and one rule in `ibkr/safety.arm` (ADR 018 amendment, operator decision 2026-09-23): **Live arms only with the operator's PIN, checked by the backend** against a hash in `.env` (`NOVA_LIVE_ARM_PIN_HASH`, set with `py -3 tools/set_live_arm_pin.py`; none set = Live refuses to arm); **Paper and Sim arm with no PIN** -- the padlock in one click, a bot through the same endpoint. The latch is stamped with the venue it was armed on and reads disarmed on any other, so a practice arm is never a Live arm. Never an `.env` edit, never inferred from a connect, reconnect or self-heal, and never re-armed by any automatic path. A venue change disarms. Protective sources (`flatten`, `kill`, `cancel_working`) and cancel are exempt: a disarmed desk must always be able to get flat. Only the *settled* venue persists -- an in-flight gateway-mode switch stays process-local in `gateway_heal.py` so ADR 013's unattended reconnect is unchanged.
- **Market Open Halt**: The gapper dashboard stops updating its data feed once the market formally opens.
- **Configurable**: API keys and base URLs must be configurable via UI.
- **PR-first delivery after every task:** Code, config, CI, security, and rule changes MUST follow §5.1 (clean start from `origin/master`, ready PR finish line). Direct `master` pushes are limited to status-only operations or explicit user instruction. Complete `.github/pull_request_template.md`, link the issue truthfully (`Closes` only for full completion; `Refs` for partial work), verify, commit, push the branch, and open a **ready** (non-draft) PR. **GitHub Actions merges ready PRs** without waiting for CI (`tools/pr_delivery.py`). Do not wait for the human to say merge. Draft or label `do-not-merge` is the hold, and only under §5.1. After that PR is merged or closed, **delete the head branch** (`git fetch --prune` then `py -3 tools/stale_pr_branches.py`; use the guarded `pr_delivery.py delete-closed --ref <branch>` only for a verified safe tip). GitHub `delete_branch_on_merge` plus `.github/workflows/pr-delivery.yml` are the backup sweep. Never leave merged or superseded branches on origin. Never delete `master` or a branch that still has an open PR. **Master branch protection** (no force-push, no deletion, no required CI checks) is the required GitHub setting; verify with `py -3 tools/master_branch_protection.py check` and do not claim it exists unless that command exits 0. Public Nova unlocks that setting on GitHub Free. A private personal repo still needs GitHub Pro. The public source home is `aaltaay/Nova`. `aaltaay/Nova-public` is a private archive.
- **Backlog work packages:** The backlog is organised into ranked work packages -- one **GitHub milestone** per package, every open issue in exactly one. Current narrative in GitHub Issues/milestones; authored package configuration in `knowledge/backlog-packages.json`; milestones are its projection (`py -3 tools/backlog_triage.py sync`). Agents asked "what's next" run `py -3 tools/backlog_triage.py next` -- it returns one package, one PR batch, and the acceptance criteria. **Batch related issues into one reviewable PR**; do not open a PR per issue. New issues get a package plus the `deferred` / `P0`-`P3` / kind / `domain:*` labels -- `backlog_triage.py check` reports the gaps, and `.github/workflows/backlog-triage.yml` sweeps weekly and fails when any remain. There is no pinned rollup issue -- `py -3 tools/backlog_triage.py report` answers "what is the state of the backlog" on demand, from GitHub. Gated work needs an operator decision -- record the question on the issue, never guess the policy.
- **Nova Delivery board:** Canonical project is https://github.com/users/aaltaay/projects/1 (user project number `1`, owner `aaltaay`, id `PVT_kwHOAXJK5M4Ab7Vq`). Do not recreate it. `.github/workflows/nova-delivery-project.yml` adds new issues and same-repo PRs. Agents must also run `gh project item-add 1 --owner aaltaay --url <html_url>` when the token has `project` scope, and default Status to Todo unless already In Progress. Priority stays on labels `P0`..`P3`. Classic `GITHUB_TOKEN` and the Cloud Agent GitHub App typically lack `project` scope; owner `gh` as `aaltaay` can mutate; Actions uses repo secret `NOVA_PROJECT_TOKEN`. On 403, report the limitation -- never claim the item exists.
- **Next-move footer** (replaces the Better ask / Follow-up ask paragraphs, 2026-09-20): every substantive user-facing reply ends with an optional one-sentence **Better ask:** and a numbered **Next move** menu the operator answers with a digit. Lanes in this order: `[thread]` (continue this reply), `[ship]` (the human step that gets Nova out the door), `[backlog]` (the batch `backlog_triage.py next` would hand out), `[decide]` (the operator decision that unblocks the most issues). Exactly one line is starred; every line is a pasteable prompt. The `[ship]` / `[backlog]` / `[decide]` lines are copied from `py -3 tools/next_moves.py seed` (the session brief injects it), never from memory. Never offer `auto_live`, a live-gate flip, a claimed or gated batch, or a per-issue PR. Template, failure / question modes, skip rule: `.cursor/rules/next-move-footer.mdc`; check a draft with `py -3 tools/next_moves.py lint`. Specialist subagent reports keep the Lifecycle line instead. Skip only trivial exchanges (pings, tiny confirmations, status polls) -- never pad.

### 5.1 Session lifecycle (Deliver)

**Branch preservation (#369):** A closed PR's branch name is never proof that its current tip is disposable. Cleanup must preserve and report tips not contained in `origin/master`; this safety rule overrides head-deletion and clean-clone requirements below. Squash-only or closed-unmerged tips require explicit review, not automatic deletion. Remote deletion must compare-and-delete the verified SHA so a concurrent push survives. A later `git push` reporting `* [new branch]` may have recreated an already-merged head: check PR state and move new work to a fresh branch.

These gates are **MUST**. They override casual phrasing such as "quick fix" or "just tweak." Only an **explicit** user override ("stay on this branch", "leave as draft", "commit locally only") can waive them. If work still ships, state that waiver in the PR body.

**A. Clean start -- before any edits**

1. `git fetch origin`.
2. Create or switch to a **new** focused branch from `origin/master` only. Never branch from a dirty local `master` tip. Never continue another feature branch unless the user explicitly names that branch.
3. If the worktree has uncommitted or unrelated dirty files: do **not** proceed on top of them. Reset or clean tracked files you do not own in this task so they match `origin/master`, or abort and report the dirty paths. Never "just keep working" on mixed dirty state.
4. Cloud and desktop agents: "isolated" means a clean tip of `origin/master` plus a new branch. Local dirty IDE state is not a valid base.

**B. Mandatory finish -- end of every coding session or task**

1. Verify (tests and build appropriate to the change).
2. Commit intentional changes on the focused branch.
3. Push the branch.
4. Open a **ready (non-draft)** PR targeting `master`, filled from `.github/pull_request_template.md`. Attach the issue/PR to [Nova Delivery](https://github.com/users/aaltaay/projects/1) when the token allows.
5. Draft or `do-not-merge` only when the user explicitly asked to hold, or a hard external blocker (for example, needs live IBKR proof) is documented in the PR -- not because CI is still running.
6. Do not end the session with only local commits, unpushed commits, or "I'll open the PR later." The PR URL is the finish line.
7. Keep existing rules: Actions auto-merge when available; `Closes` vs `Refs`; delete the head after merge or close; all verification advisory.
8. **Leave it clean.** No modified, staged or untracked files, no `git stash`, no leftover scratch worktree; `py -3 tools/repo_hygiene.py status` is OK for what you own. Stage explicit paths, never `git add -A`. The Claude Code Stop hook (`repo_hygiene.py stop-gate`) refuses the first dirty stop; `repo_hygiene.py fix` and the nightly `NovaRepoHygiene` task reclaim merged local branches and stale worktrees (`workspace-hygiene.mdc`).

Always-on copies: `.cursor/rules/commit-push-deploy.mdc`, `.cursor/rules/github-delivery.mdc`, `.cursor/rules/workspace-hygiene.mdc`, `.cursor/skills/github-delivery/SKILL.md`.

---

## 6. 🔧 Coding Standards (Enforced)

### 6.1 Constants Policy

- **Authoritative values** live in backend domain modules (`constants_scanner.py`, `constants_hod_momo.py`, `constants_ibkr.py`, `constants_archive_news.py`, `constants_nova_os.py`) and frontend `constantGroups/` (or feature-local constants).
- `backend/constants.py` and `frontend/src/constants.ts` are **compatibility barrels** — re-exports only; do not add new definitions there.
- No magic numbers. No inline strings in `main.py` / `App.tsx`. Import from domain modules or barrels.
- Keep backend/frontend mirrors in sync for shared values.
- New constants go in the owning domain/feature module FIRST, then re-export from the barrel if needed.
- Environment variable overrides are permitted, but the default MUST come from a domain constants module.

### 6.2 Naming

- Python: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for constants.
- TypeScript: `camelCase` for functions/variables, `PascalCase` for components/types, `UPPER_SNAKE` for constants.
- Files: `snake_case.py` for Python, `PascalCase.tsx` for React components, `camelCase.ts` for utilities.

### 6.3 Error Handling

- Use structured logging (`logging.getLogger(__name__)`) in Python.
- Never swallow exceptions silently — at minimum log a warning.
- **The money path fails the gate on silence.** In `backend/execution/`,
  `backend/ibkr/`, `backend/practice/`, `backend/sim/`, `backend/kill_switch/`,
  `backend/bot/` and `frontend/src/ibkr/` an `except …: pass`, an
  `except …: return []` / `{}`, or an empty `catch` is a `*_money` finding, because
  a desk that swallows an order, position or account read is lying about its
  state. Log it, turn "unknown" into a stated unknown (never "empty", "flat" or
  "abandoned"), or -- when silence is the correct behavior (a timeout that ends a
  wait, an idempotent `list.remove`, a parse that falls through to the next
  format) -- say so at the site:
  `except asyncio.TimeoutError:  # maintainer: allow-swallow the timeout ends the wait`.
  File-wide allowlists never apply there (`tools/maintainer_lib/swallow.py`).
- Frontend: surface errors in UI debug panels, not just console.

### 6.4 Testing

- Backend: pytest for API behavior and pure Python logic.
- Frontend: Vitest + React Testing Library.
- New modules should include at least a minimal test.

### 6.5 Dependencies

- Python: pinned in `requirements.txt`.
- Node: `package-lock.json` committed, use `npm ci` in CI.

### 6.6 Secrets & Security

- Never commit secrets, API keys, or full `.env` files.
- No secrets in log messages.
- Use `.env.example` for documented safe examples.

---

## 7. 📝 Documentation Requirements (Enforced)

### 7.1 CHANGELOG.md -- RETIRED. The PR body is the record.

There is no changelog. `CHANGELOG.md` is archived under `_archived/` and is not
maintained, generated, or required. Do not recreate it, and do not add a
changelog entry, fragment, or collation step to any workflow.

- **A PR that changes behavior carries its entry in its own body:** **What** /
  **Why this approach** / **Verified by**, per
  `.github/pull_request_template.md`. That is the record, and the merged PR is
  its permanent home.
- **No PR?** (direct push, ops diagnosis, audit conclusion) -- write the
  narrative under `knowledge/task-log/` (§7.2b). Nothing else is needed.
- **Why retired:** the entry already exists in the PR body. A second generated
  copy added a file nothing read, a workflow that could silently fail to open
  its PR (it did -- master drifted 11 PRs behind without anyone noticing), and a
  `merge=union` attribute to stop the paperwork causing merge conflicts (#344).
  Removing the mirror removes all three.
- Existing history is untouched and stays readable in the archive.

### 7.2 Bug-fix evidence

Record the symptom, cause, fix, and verification in the relevant PR or issue.
Keep useful regression tests. Do not create a separate problem ledger or footer.

### 7.2b Task narrative (PR body first, `knowledge/task-log/` when there is no PR)

- Every completed material task (parent or specialist) needs a reasoning narrative. **Default home is the pull request body** -- fill `.github/pull_request_template.md`: What / Why this approach / Verified by / Related issue.
- No PR (direct push, ops diagnosis, audit conclusion)? Append a dated file under `knowledge/task-log/` and prepend `INDEX.md`. Scaffold: `py -3 tools/task_log_new.py --slug <kebab> --title "…"`.
- **Why this approach** is mandatory in either home -- capture tradeoffs and rejected alternatives, not only the diff. Never write both homes for one job.
- Rule: `.cursor/rules/task-log.mdc`.
- Lifecycle footer includes `task_log=<PR URL>|<path>|skipped|n/a` and `deferred_log=<#NNN or D-NNN>|none|skipped|n/a`.

### 7.2c Deferred tracker (GitHub Issues)

- **Mandatory for every agent** (parent + all specialists). Rule: `.cursor/rules/deferred-log.mdc`. Source of truth is GitHub Issues labeled `deferred` -- https://github.com/aaltaay/Nova/issues?q=is%3Aissue+label%3Adeferred . `DEFERRED_LOG.md` is the how-to, not the to-do.
- **Before any fix:** run `py -3 tools/deferred_log.py status` (alias `priorities`) and search open `deferred` issues. If an existing issue already covers the ask, work from that issue (honor `parked` / Unblock / Next). Do not start a parallel fix that ignores it. When the human asks "what's on the to-do / what's missing / priorities," that command is the answer.
- Open (or comment on) a GitHub issue after parking a known bug or a feature you will not build this session -- same session.
- Close an issue only when its entire stated scope is complete and verified. Partial fixes use `Refs #NNN`, get an evidence comment, and leave the issue open. Follow `.cursor/skills/github-delivery/SKILL.md` for owner, Project, Milestone, relationship, Development-link, and close-reason rules.
- **Durable id is the GitHub issue number (`#NNN`).** Title an issue plainly -- no `D-NNN` prefix, no allocation step. GitHub mints `#NNN` atomically, so two agents filing at once can never collide. `D-NNN` is a **legacy alias**: the ~90 issues that carry one keep it, the tooling still parses and displays it, and history (`CHANGELOG.md`, `PROBLEM_LOG.md`, test docstrings) is never rewritten. Never mint a new `D-NNN`.
- Labels: `deferred` + `P0`..`P3` + `bug`/`enhancement`/`decision` + `domain:<name>`. Body fields: Kind, Severity, Effort, Why parked, Blast radius, Unblock, Next, Evidence. Refresh the offline index in the creating PR when convenient; it is a read cache only, and no correctness now depends on it.
- Lifecycle footer **MUST** include `deferred_log=<#NNN or D-NNN>|none|skipped|n/a`. Agent-memory Backlog is not the SSOT. Product-phase NEXT stays in `Nova-Roadmap-Status.md`.

### 7.3 .cursor/rules/

- MDC rules are peers of this constitution. They provide fine-grained, glob-scoped enforcement.
- When logic changes, update or add the relevant MDC rule BEFORE writing code.

---

## 8. 🚀 Run & Deploy

Operator runbook for syncing the trading PC to master, cold-restarting IB
Gateway and arming the unattended premarket: `docs/live-desk-sync.md`.

### Local Dev (Windows)

```text
# From repo root — browser UI:
Run Nova.bat

# Desktop (Electron + local API sidecar):
Run Nova Desktop.bat
# or: cd frontend && npm run electron:dev

# Windows installer:
cd frontend && npm run electron:pack

# Or manually:
# Terminal A (backend/): py -3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
# Terminal B (frontend/): npm run dev
# Open: http://localhost:5173
```

### Deploy

- **Backend:** local only right now -- no cloud host (not Railway, not another PaaS). Run via `Run Nova.bat`, Desktop sidecar, or local uvicorn on `127.0.0.1:8000`.
- **Public site:** not in this repo. `nova.altaystudio.com` is built from [`aaltaay/nova-site`](https://github.com/aaltaay/nova-site), which owns the page, its screenshots, the AI-in-trading digest and the Vercel deploy. Nothing here builds, deploys or tests it.
- **Frontend (app UI):** local Vite / Desktop only (`http://localhost:5173`). Do not host the trading SPA on the public domain.
- **Desktop:** Electron + local API sidecar. **Installer only** (#347): local pack produces `frontend/release/Nova-Setup-vNNN.exe` plus `latest.yml` + `.blockmap` -- the in-app update feed. The portable EXE is retired; it could never self-update. Application-affecting PRs run the advisory `Desktop pack` GitHub Actions job, which uploads those three files; docs/site-only PRs skip packaging under `.cursor/rules/ci-scope.mdc`. Every commit that lands on master gets its `vNNN` tag, and an application-affecting one also gets a GitHub Release (see below).
- **Releases are automatic (operator decision, 2026-09-23 -- supersedes #347's tag-only publishing):** every commit that lands on master -- a human push, or PR delivery's dispatch after an Actions merge (#346) -- is tagged `vNNN` (its commit count) by `Desktop pack`, which tags the commit through the API. An application-affecting commit packs the installer and publishes it as the `vNNN` GitHub Release with the installer, `.blockmap` and `latest.yml`; a docs/site-only commit gets the tag and no Release, because a Release without `latest.yml` would break the update feed. A Release is marked latest only when no higher `vNNN` Release exists, so a slow run never rolls the feed back. The tag is pushed with `GITHUB_TOKEN`, so it starts no second run. A hand tag still works: `py -3 tools/bump_version.py --ensure-tag --push-tag` on an up-to-date `master`, and the pack refuses a tag that is not that commit's revision. Re-run one with `gh workflow run desktop-pack.yml --ref vNNN`. GitHub's Source code zip/tar is automatic and is not the app.
- **In-app updates (#347):** the installed desk checks GitHub Releases shortly after launch, downloads a newer installer in the background, then offers **Restart to update** / **Later**. It never installs or restarts on its own -- not on quit, not on a timer. `NOVA_UPDATE_CHECK=0` (desk `.env` or process env) turns the automatic check off; Help > Check for Updates still works. Builds are unsigned, so SmartScreen warns on a fresh download.
- **The installer download is resumable (2026-09-23):** electron-updater checks and installs, but Nova fetches the installer itself (`frontend/electron/updateDownload.mjs`) in 8 MB Range chunks, each retried on its own (1 s up to 2 min, about 4 min per chunk). What arrived is kept across failures and desk restarts under `%LOCALAPPDATA%\nova-updater\nova-partial\` -- `<installer>.part` plus `<installer>.part.json` `{schema_version: 1, version, sha512, size}`, discarded when the release, size or schema changes or the finished file fails the release sha512. The verified file goes into electron-updater's `pending` cache with its `update-info.json`, and electron-updater hashes it again before it offers Restart to update. A download that gives up reads "Download of vNNN stopped at N% -- Resume" and Resume continues from the kept part; an installer already downloaded (Later, then a restart) is not fetched again. Every update line is also written to `%APPDATA%\nova\logs\update.log` (rolls at 1 MB). Why: a link that corrupts a TLS record every few dozen MB made electron-updater's one-shot 150 MB download fail every time (`net::ERR_SSL_PROTOCOL_ERROR`).

---

## 9. 🔄 Self-Annealing Protocol

When ANY error occurs during a task:

1. **STOP** — Do not apply a band-aid.
2. **Analyze** -- Search relevant GitHub issues/PRs and run `py -3 tools/deferred_log.py status` (GitHub Issues labeled `deferred`) for prior matching entries. If an open/parked issue already covers it, work from that issue (or leave it parked) -- do not start a parallel fix.
3. **Root Cause** — Identify the actual cause, not the symptom.
4. **Patch** — Fix the root cause in the correct module (not in `main.py`).
5. **Test** — Verify the fix works (build, run, or test).
6. **Update SOP** -- Document the cause and fix in the PR/issue (if fixed) or open/update a GitHub Issue labeled `deferred` (if parked), and update relevant MDC rule if needed.
7. **Deliver** -- follow §5.1: verify, commit on the focused branch created from `origin/master`, push, and open a **ready (non-draft)** PR. The PR URL is the finish line. Use `Closes #NNN` only when the full issue is complete; otherwise use `Refs #NNN`. After the PR is merged or closed, confirm the head is gone (`stale_pr_branches.py`; the guarded delete command only for a verified safe tip).

---

## 10. 🚨 Compliance Audit (Current Violations)

No open constitution compliance rows. `architecture/` (ADRs 001–009) and automated tests (pytest + Vitest) exist. Product/security open work lives in `Nova-Roadmap-Status.md` and `Security-Status.md`. Live-doc drift is gated by `py -3 tools/doc_invariants.py` (CI).

---

## 11. 🔧 Maintenance Log

| Date | Change | Author |
|------|--------|--------|
| 2026-09-23 | Who may arm the desk (ADR 018 amendment, operator decision: "I want the bot to be able to unlock [Paper / Sim] themselves through an endpoint, but I don't want the live trade to ever get unlocked without my permission"): one door (`POST /api/ibkr/arm`) and one rule (`ibkr/safety.arm`) -- Live arms only with the operator's PIN, now checked by the backend against a PBKDF2 hash in `.env` (`tools/set_live_arm_pin.py`), with a lockout after wrong PINs; Paper and Sim arm with no PIN, from the padlock in one click or a bot. The PIN had been a constant in the public frontend source, compared in the browser, while the endpoint armed Live for any local caller. The latch is stamped with its venue, so a practice arm never reads as a Live arm. The frontend's per-tab unlock flag and its cross-window sync are gone: every window reads the backend latch. Also from the same after-hours test run: a running recording is never finalized by another process's startup, tests never resolve the F: archives, Vite's dependency cache moved out of the shared `node_modules`, and Flatten on a flat practice position says it is not a close. §3 and §5 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Movers get the news that moved them (operator report: "most stocks don't have news, and they are moving"). Audit of the day's boards: 24 of 28 checked movers had no release or filing at all, so an empty News column is often the truth; the desk's own misses were a backend still running code from before the verdict reached the rows, a Windows Update restart that cost the wire feed the whole premarket, Benzinga "what's going on" pieces whose summaries named the cause (BENF, ARTL, BFRG) filed as movers lists, and screens / plural lists / cover-page addresses mislabelled. Rules v6 reads a one-ticker rewrite's stated cause; Finnhub company news joins the live verdict (`catalysts/live_finnhub.py`: answers for the window after the fact, carries Yahoo copies of GlobeNewswire / PR Newswire / ACCESS / Business Wire releases; its Benzinga copies are dropped for their four-hours-early clock, #516, in research too). Honest clocks move the research's leaderboard coverage (none found 23% -> 40%) but not the first-pullback split. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | In-app updates survive a lossy link (operator report: "Update check failed -- net::ERR_SSL_PROTOCOL_ERROR" on v959): the check worked, the 150 MB installer download failed every time. This PC's Wi-Fi corrupts a TLS record every few dozen MB (Windows curl `SEC_E_DECRYPT_FAILURE` from GitHub, Hetzner and OVH; 6 GB over loopback TLS clean), and electron-updater restarts a failed download from zero. `frontend/electron/updateDownload.mjs` now fetches it in resumable, individually retried chunks, keeps the part, checks the release sha512 and hands the file to electron-updater's cache; the Help menu names a stopped download as one ("stopped at N% -- Resume"); `update.log` records every step. §8 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Code-shape rules measure behavior, not a snapshot (operator ask: "'All files are under 400 lines' -- is this an actual rule? ... how do we create better rules to manage the scalability of this project?"). §2 rewritten: the hand-kept file trees become ownership statements next to the code (backend package docstrings, `frontend/src/FOLDERS.md`) that the checker keeps complete, printed by `tools/module_map.py`; the hard 400-line cliff -- which bunched ten files at 395-400 lines -- becomes a soft limit that asks for a one-concern reason, a no-growth check without one, and an 800-line ceiling; constants tables are exempt; the .tsx 300 rule (which contradicted §2.3) is gone; feature-slice deep imports are frozen per file (340 on the day) instead of checked for 9 of 34 slices. §6.3: silent failures on the money path fail the gate; 22 sites fixed or given a reason, three of them real misreports (a practice flatten reported flat when its re-read failed, the startup sweep could call a filled order abandoned when `ib.fills()` failed, a partly unreadable commission total was shown as the total). CI runs `maintainer_checks.py --gate`. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | The Bots page as approved (mockup v4; operator report: "my screen looks nothing like the mock up + half of buttons don't work", "I want to see that L2 stuff in my header"): Bots is a shell page like Account, not a tab squeezed between the HOD strip, the positions dock and the quote panel. Every control works or says why not: the gate chips carry the link that opens them (unlock the padlock, open a symbol's Level 2 in a pinned Trader tab, see the read-out, add a symbol, reset the kill switch), choosing Strategy with the padlock locked says so, the setup radios and each setup's level switch are real (disabled with the reason where no scanner exists), "+ Add a setup" explains the door and copies the catalogue path, the sleeve is sliders that PATCH once let go, and the breakers draw today's P&L. Symbols say who holds the line with Last and Change; proposals keep the ones the scanner withdrew (closes now on the audit stream); the timeline adds the setup scanner's own day (setups.db); Today adds bot P&L from the practice ledger. The header carries the bot pill ("Bot L2 First pullback · Not active") and the rail a state dot. The quote panel folds to a strip on the right like the Focus list, streaming nothing while folded, and grades any symbol's Five Pillars (`GET /api/strategy/watchlist/{symbol}`). An API older than ADR 027 is named as such instead of "every gate is open". The course vendor's name left the UI. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Automatic release tags (operator ask: "after every commit we make to master, can we create a release tag"): `Desktop pack` tags every master commit `vNNN` and publishes an application-affecting one as a GitHub Release with the installer and update feed; docs/site-only commits get the tag only. Master runs group by commit so a burst of merges tags every one, and a Release is marked latest only when it is the highest. Supersedes #347's operator-tag-only publishing; the installed desk now offers an update after each application merge. §8 amended. | User Directive + Claude Code |
| 2026-09-23 | The catalyst verdict on the desk (ADR 024 amendment, operator report: "still just seeing garbage"): the Gainers' top three all showed one Benzinga market wrap as their news, IPDN's panel called it "moved price 90%", and real releases (HCTI's PR Newswire LOI, BENF's 8-K) showed nothing -- the verdict fed only the setup scanner. Scanner rows now carry `catalyst` (`catalysts/board.py`); the News column, "Has news" chip, Trader tab chip, HOD flame and the Watchlist pillar read it; the Trader's News panel reads `GET /api/catalysts/{symbol}` (verdict + labelled items, lists folded away). Rules v5: share consolidations are reverse splits, circuit-breaker notices are halts not news, "beat the market" is not an ATM offering, debt elimination and customer wins count, a movers-section URL needs a placed class; the SEC headline joiner stops cutting on "and". `has_news` keeps its meaning. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | The bot plays the operator's setups (ADR 027, operator decision: "no, I don't think we need the old packs -- remove"; "keep the Strategy L2 + all setups from my material"; approved Bots mockup v4): the halt-luld / quote-spike / volume / llm-decide packs, `POST /api/bot/llm/spend` and the `nova-brain` sidecar (Electron, `Run Nova.bat`, `Start-NovaBrain.ps1`) are removed; the session (schema 4) carries `setup`, `setups`, `readout` and `gates`. Strategy waits on the pre-registered first-pullback read-out (`setup_scanner/readout.py`, Bot-Trading-Plan §2g): raising to Strategy lands not active, Activate at Strategy and every L2 fire are refused `BOT_READOUT_NOT_PASSED` until 50 triggered go setups beat +0.2R net and blind / wait; L2 entries keep the material's 07:00-10:00 ET window and one trade a day. The Bots page is rebuilt (hero with level, gates and Activate; the playbook with first pullback's rules, tape gate and read-out; symbols with Level 2; sleeve and breakers; one proposals inbox; the activity timeline; today and the scoreboard) and the header's second bot row is gone. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Watchlist redesign (approved mockup v2): rows add the scanner row's market facts (`price`, `change_pct`, `rel_volume`, `rvol_source`, `float_shares`, `has_news`) and today's catalyst verdict (`strategy/watchlist_catalyst.py`, ADR 024); the table shows pillar letters with n/5, Last, % Chg, RVOL, Float, News, a score bar, the setup state from `/ws/setups` and the bot allowlist dot, with filter chips and a summary line; the side panel lists the pillars with reasons, the setup block and the allowlist toggle. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Why the Gateway needed a phone login (#14): a Windows Update restart at 02:29 ET ended the Gateway's saved login and Windows waited at the sign-in screen until 09:22, so no morning task ran and nothing said why. `ibkr/relogin_reason.py` + `ibkr/windows_restarts.py` name the cause (a restart and who asked, or a fresh start) in `/api/diagnostics`, the morning scripts' logs and alerts, and `tools/premarket_verify.py relogin`; `tools/premarket_verify.py` reads #14's two criteria; Nova's IBC launchers set `DAYOFWEEK` so IBC keeps a week of logs on Windows 11. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Prints that set a price (operator report: PLTR's 10-second chart grew wicks Webull does not show): the wicks were FINRA `4 W` (derivatively priced, average price) and odd-lot prints $2-3 under the market, reported for volume and painted by Nova as prices. One pure rule (`backend/sale_conditions.py`: IBKR's `unreported` flag plus the non-price sale-condition codes) now feeds every candle built from prints -- the client 10Sec bar, `ibkr/tape_10sec`, the archive 1m builder, the recorder's bar buckets, capture replay -- and the tape print payload carries `unreported` / `sets_price`. The L1 last is IBKR's tick 4 Last, not the `ticker.last` that ib_async overwrites from RTVolume and every AllLast print. Tape-built bars now match IBKR's own 10-second TRADES bars (worst miss $8.50 -> $0.18 on AAPL; volume ratio 1.00). §3 and ADR 012 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Performance recorder (ADR 026, operator ask: "measure the laginess ... figure out what the bottlenecks are"): `backend/perf/` records, every second, each loop's CPU share and worst callback delay, the process CPU (one GIL for every thread), busy time per hot handler (`op_metrics` gains a running total), queue depths and drops (the depth / tape viewer queues' silent drop-oldest now counts) and GC pauses; a watchdog samples a stalled loop's stack until it recovers and keeps the report with 30 s either side. Every desk window and the Electron main process post a 5 s report (frame pacing, long animation frames with the script named, socket rates, render counts, per-process CPU). Kept 7 days under `<cache_dir>/perf/`, written by one writer thread, never from a loop; `/api/perf/*`, a Performance group in `/api/diagnostics`, and `tools/perf_report.py` read it. Its first live run caught `second_factor.current_state()` starting PowerShell (~250 ms) on the HTTP loop on every `/api/ibkr/status` poll; the IBC log now decides first and the process is checked only while a 2FA prompt is open. Code-read suspects stay unfixed until a recorded open ranks them. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Nova OS retired (ADR 025, operator decision on #481, option a): the BUY / WAIT / NO BUY verdict (judged on Gap and Go, which failed gate 1), the `signal` / `confirm` / `auto_paper` ladder, the staged approval queue, the Phase D executor and its restart recovery, the decision replay (`/api/archive/replay|walk|review`) and the Automation hotkeys are removed; Watchlist keeps Watchlist / Setups / Journal / Backtest and the Trader dock loses its Nova OS tab. The kill switch latch moves unchanged in meaning to `backend/kill_switch/` with `/api/kill-switch` and a card on the Bots page. Execution sources `approve` / `auto_paper` are refused `SOURCE_INVALID`. The event log, the NYSE holiday table and the walk-away rules stay; who the walk-away rules gate is left to the operator. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Catalysts, the primary sources (ADR 024 amendment): an always-on live catalyst feed records SEC EDGAR's latest filings (with the 8-K / 6-K press release), GlobeNewswire, PR Newswire, Newsfile and FDA into `catalyst_feed.sqlite3` with proven coverage spans (a poll extends a span only when it reached back to the previous one), merged into the live verdict; a Nasdaq T1 / T12 halt sets `news_pending`; the News pillar is unknown for news pending or an unplaced `company_news` headline; `/api/diagnostics` adds `catalyst_feed`. Nasdaq's halt history (2021-10 on) is in the leaderboard's `halt_events`; research gains point-in-time SEC shares outstanding and FINRA short interest. Business Wire / Accesswire have no free feed and stay indirect. Rules v4. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Catalysts (ADR 024): one pure classifier (`backend/catalysts/classify.py`, `constants_catalysts.py`) for the backfilled history and the live desk -- noise (movers lists, law firms, opinion, roundups), routine, negative (dilution, delisting) and catalyst (strong / weak by class); a symbol-day's verdict reads only items published after the prior 16:00 ET close and by its cutoff, and says `none_found` only when a source looked. The setup scanner's News pillar passes only on a real catalyst and is `null` when unknown (`catalysts/live.py`); `pillars.headline` is the headline, not a timestamp. The history is backfilled onto `F:\Nova\catalysts` from SEC EDGAR (bulk index + filed press releases), Alpaca, Finnhub's free year and the Massive archive (`research/catalysts/`), and the first pullback is re-run by catalyst class. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Header ticker search gets smarter (operator ask): `GET /api/symbols/directory` serves every listed US symbol with its company name (Alpaca listing metadata, cached 6 h); the search matches by ticker or company name across the whole listing after the desk's own symbols, filters with `/regex/` and `A*X` wildcards over symbols, shows recent look-ups on focus (Shift+Del forgets), and Tab completes. Enter still opens exactly what was typed when it could be a ticker; only a name-only match (APPLE -> AAPL) moves the default. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-22 | Scanner leaderboard (ADR 023, operator decisions 2026-09-22): one row per symbol per minute per board, recorded always (no button; 04:00-20:00 ET exchange days; enqueue-only, a worker writes) and rebuilt offline from the Massive minute flat files (`research/leaderboard/`, no hindsight: prior-20-session time-of-day RVOL, float only as known that day). Gaps are stated with their reason (`not_running` / `feed_down` / `not_recorded` / `outside_session`) and never carried across; halts come only from a new halt / LULD log (IBKR tick 49 + Nasdaq RSS). One pure ranking (`leaderboard/ranking.py`) for playback leaders, S5 and auto-record; auto-record records the leaders 07:00-10:00 on free Level 2 lines only and yields the moment the operator opens Level 2 or Record elsewhere. `POST /api/sim/clock {session_date}` moves Sim to a past day with nothing loaded; the Scanner and HOD strip follow the playhead off the live edge. `/api/history/dates?type=all`; `movers` reads the split files. Segment reason `auto`. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-22 | The setup scanner (ADR 022): one live first-pullback scanner replaces the old setups stream (`/ws/strategy`) and the Watchlist's Signals sub-tab. It follows the HOD Momo names on Nova's own one-minute bars through Watching, Leg up, Armed, Near, Triggered or Failed on the pre-registered P1 rules (94.9% parity with the research harness), reads the Level 2 and the tape the desk already holds at the trigger (`go` / `wait` / `veto` / `blind`; it opens no IBKR line), and raises a proposal only when a live setup is near and the tape says go: a ping, an alert card on every tab, a staged ticket at most. Nothing in `setup_scanner/` imports an order path. Every armed setup is scored in `setups.db` the way the backtest scored its trades. The Phase D executor no longer receives signals. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-22 | Test quantity gate binds Live only (operator decision on #444, option 1: "keep enforcing one quantity for the live so we never mess it up, and remove that restriction for paper and sim"): the Live default cap is 1 share (`IBKR_FORCE_ONE_SHARE_QTY`, `IBKR_QTY_CAP` in `.env` still overrides it); Paper and Sim send the size asked, buying power still enforced. An unreadable venue counts as Live, and the IBKR send refuses a size still above the cap (`QTY_CAP_LIVE`) -- a venue switched mid-command, or a bracket sized at the send from strategy risk. `/api/ibkr/status` `qty_cap` is null on Paper / Sim; the Live ticket says "Live cap: sends N of M shares". Supersedes the same day's 10-share cap on every venue. | User Directive + Claude Opus 5.5 |
| 2026-09-22 | HOD Momo tradeable floor (operator: "I need to see things I can trade"): the master gate refuses any symbol under `min_volume` shares today (100k), `min_price` ($1) or, when RVOL is known, `min_rvol` (1.5) before any strategy runs -- reasons `master_liquidity:volume|price|rvol|no_volume`; `GET/POST /api/hod-momo/config` `master` carries the three floors and the Master Gate panel edits them; a persisted `min_rvol` of 0 from the retired master RVOL migrates to the floor once. MI (13k shares, RVOL 0.19) no longer reaches the board on "Approaching HOD". | User Directive + Claude Fable 5.1 |
| 2026-09-22 | Test quantity gate becomes a cap of 10 shares on every venue (operator decision on #444: "max 10 shares, still ignore 100"): `execution/qty_gate.py` sends a size at or under `IBKR_FORCE_ONE_SHARE_QTY` as asked and cuts a larger one to it; `/api/ibkr/status` adds `qty_cap`; the ticket's confirm and footer say "sends N of M shares". Constant names kept for the execution record's `forced_one_share` stamp. Protective sources stay exempt. | User Directive + Claude Fable 5.1 |
| 2026-09-22 | QA pass two -- Scanner / header / layout batch: cached scanner rows keep `quote_quality` so a REST reload never serves IBKR's prior close as a live price (C50); name-only rows state `volume: null` (C37); the universe and after-hours rows name their RVOL source; restored after-hours rows measure change from price, not gap (C36); pre-fix HOD alerts restore their invented 0.0% change as null; the HOD inspector and blocklist routes take a slash; the Strategy grades read the surfaced rows (W6); bar-derived sensors carry `bars_as_of` (W16). The desk: the header sheds per REC chip (D1), scanner row actions stick to the board edge (D2), the Trader rail's Level 2 and Time & Sales fit their panes (D3, R28), an unknown status is never a Gateway outage (D10). §3 amended. | User Directive + Claude Opus 5 |
| 2026-09-22 | QA pass two -- Account page, practice ledger, Sim / replay, the ticket: `/api/ibkr/orders/closed` on Paper / Sim lists only the rows closed in the venue's practice day (W4, `practice/today.py`); a refused practice execution is stamped with its venue (R38, `execution/desk_mode.py`); an undownloaded stretch of a historical window is refused `SIM_NO_PRICE` and a protective close there fills at the last mark (R34); the historical snapshot adds `session_open` and `stats_scope` so the quote card's Gap% is the session's and Vol / High / Low are stated absent for a midday window (W7); a replay unload frees its working orders' commitments (R40), practice order ids continue across a reset / unload (`first_order_id` in `practice-paper.json`) and an order filled inside the practice send marks its row `filled` (R41); `POST /api/sim/history/depth-line` lets the historical Level 2 hold the replay depth slot the bot gate reads (R44). §3 and `architecture/practice-fills.md` amended. | User Directive + Claude Opus 5 |
| 2026-09-22 | The ticket's Flatten never closes the same shares twice (QA R42, P0 regression from #454): the check moves from the route into the execution door (`execution/flatten_intent.py`, inside the execution lock) and subtracts the closing orders already working or committed, so a second Flatten while the first rests is refused `FLATTEN_NOT_A_CLOSE` instead of filling the account short; `ExecutionCommand` gains `intent`. The practice broker cancels a SELL that would fill past the held quantity (`order_rules.fill_refusal`). The quick-bar Flatten / `exit_pos` / `cancel_and_exit` send the intent too, so they are no longer clamped to 1 share (R32). The practice account summary rolls to the venue's practice day before answering, so the breaker's first poll of a new day never reads yesterday's day P&L (R45). §3 amended. | User Directive + Claude Opus 5 |
| 2026-09-22 | Practice day P&L for the breakers (QA W2, W3): the practice `/api/ibkr/account` summary's `RealizedPnL` is today's realized (IBKR's daily meaning, was lifetime since reset) and it carries `DayPnL`; `bot/day_pnl` compares `DayPnL` with the day lock on practice venues without subtracting commissions again, so a ledger down $50 since its reset can no longer trip the soft breaker at the first poll of a new day. `/api/practice/account` adds `realized_today`; the header's Day's Realized and its hover use it. §3 amended. | User Directive + Claude Opus 5 |
| 2026-09-22 | The ticket's Flatten is a protective flatten: `POST /api/ibkr/order` `intent: "flatten"` is checked against the venue's own position and sent as source `flatten` (never clamped by the one-share gate), refused `FLATTEN_NOT_A_CLOSE` otherwise (QA R32). A practice order that fills inside the send frees its commitment at once, so KILL / flatten / bot sells no longer leave shares "already sent" (R31); the flatten partial-close guard reads the sent size from the execution record (R33). §3 amended. | User Directive + Claude Opus 5 |
| 2026-09-22 | QA batch -- Scanner / HOD Momo / desk honesty: REST and `/ws/scanner` share one row pipeline (`scanner_surface`); rows carry `rvol_source`; `GET /api/scan/envelope` keeps a persistent-authoritative desk's mode / health / feed_error current; socket frames never carry a bare NaN; HOD alert ids come from the raise time, `change_pct` may be null, `last_enriched` is epoch seconds; integration details are ASCII. The desk gates every scanner row through one shape check, names failed routes, and states absences instead of inventing values. §3 amended. | User Directive + Claude Opus 5 |
| 2026-09-22 | QA batch fix/qa-sim-replay (Sim venue, replay, recording, practice ticket): replay status adds `replay_loading` (`replay_ok: null` while a capture loads); `POST /api/sim/replay` answers the clock envelope; Sim clock payloads add `replay_quote` (a capture's market at the playhead, `covered: false` in a gap); capture reads never cross a gap and refuse practice orders there; recorded quote rows load; odd lots never fill; SIM1 rows unusable; print-less failed sessions unusable; listing counts / segments / spans include the running segment and data written past the last segment; `missing_sec` excludes operator stops; the restart finalizer stops at the last write; `/api/capture` `errors` and `/api/ibkr/status` `capture_errors` per symbol; complete candle jobs cover their window; a dead download reads `interrupted`; practice rows carry venue time; a paused forward scrub fills. §3 amended. | User Directive + Claude Opus 5 |
| 2026-09-22 | QA batch (orders / account / safety): Orders (Today) belongs to the desk's venue -- the closed-orders overlay and the fill-audit join are scoped by the execution ledger's `mode` stamp, a practice desk lists its own ledger only (four filled Paper orders read "Inactive, filled 0" on Sim); leftover rows map the requested price by order type and never show placement as the fill time; practice rows carry `commission: null` until a fill, keep order ids unique across a Sim unwind, and release their in-flight commitment when resolved (a filled resting SELL used to stay "already sent"). The sample desk (`?view=sample`) sends nothing to the backend and reads none of its live state (`sample_data/sampleNetworkGate.ts`). §3 amended. | User Directive + Claude Opus 5 |
| 2026-09-22 | Operator-reported desk fixes: `/api/capture/sessions` rows carry `spans` (whole epoch seconds per recorded segment) so the Sim scrubber draws a thin recorded lane under a downloaded replay; the playhead tag moves under the band so the header no longer hides it. §3 amended. | User Directive + Claude Opus 5 |
| 2026-09-22 | Desk diagnostics (ADR 021): `GET /api/diagnostics` + `/bundle` -- a grouped checklist of facts (process root, `.env` path and whether it exists, integration keys and their source, Gateway ports / IBC 2FA / session / last IB error / attach retry, market-data entitlement and lines, recorder keepalive, practice files, UI-vs-API revision), each row with state, cause, fix and evidence. `ibkr/attach_retry.py` records every attach attempt on a bounded schedule and names the human step. Case: an agent-worktree API with no `.env` answered `:8000` and the checklist blamed the operator's configuration. The checklist UI now renders it inside the Trading prerequisites gate (derived rows stay as the API-down fallback); the dev server refuses to start an API from a git worktree or without `.env`, passes `NOVA_ENV_PATH`, and reports `GET /__nova/api-status`; a missing `.env` is a startup error and a named health detail. §3 amended. | User Directive + Claude Fable 5.1 |
| 2026-09-21 | The practice ledger as history: `GET /api/practice/history?venue&range` (`practice/history.py`, pure derivation from the event-sourced ledger) serves the redesigned Account page an event-marked equity series (a point after every fill and rollover, held positions marked at their last fill price, nothing between events), the fills with their `source` / `bot_id` stamps, the by-source split, practice-day rows including archived Paper ledgers flagged `archived`, the archives list and the P&L components. Archives beside `practice-paper.json` are read read-only; a damaged one is a logged warning in `warnings[]`, never a 500. §3 amended. | User Directive + Claude Fable 5.1 |
| 2026-09-21 | Market orders need regular hours: a non-protective `MKT` outside weekday 09:30-16:00 ET is refused `MKT_OUTSIDE_RTH` on every venue (`execution/session_gate.py`, repeated in `practice/order_rules.py`), judged by the venue's clock (Sim: the playhead). Nasdaq offers no unpriced orders in its extended sessions and IBKR holds an RTH-only MKT until the next open (399) while ignoring `outsideRth` on it (2109); the practice broker used to fill one instantly at the far quote (GRML at 8.86 after the close, a 3.6% spread), teaching a habit Live refuses. The ticket greys Market out outside regular hours and moves a Market default to Limit; a Sim tab with nothing loaded offers the operator's own Session Record before a download and says what Sim is. | User Directive + Claude Fable 5.1 |
| 2026-09-21 | Sim at now is live -- the live edge (ADR 020 live-edge amendment, re-accepting ADR 019's withdrawn amendment; operator decision, evening). The Sim clock payload and `/api/ibkr/status` on Sim carry `live_edge`: while the playhead follows the wall clock on today's date a Sim tab shows the live IBKR feed as a Paper tab does and holds a real depth line, the scratch account fills against Paper's `LiveReference` (`practice/reference.SimReference`, `PRACTICE_NO_LIVE_PRINT` at the edge, `SIM_*` refusals off it), the live matcher fills its resting orders, and every market-data gate keys on `sim/mode.is_replay_desk` instead of `is_sim_mode`. Scrubbing back leaves the edge for the loaded replay; a scrub off the edge with nothing loaded selects the tab's Session Record for today (`sim/live_edge.py`, `POST /api/sim/clock {symbol}`) keeping the playhead and the account. "Live wall clamp" becomes "Live edge"; the empty-Sim notice is quiet at the edge. Paper stays the persistent-ledger venue. §3 and §5 amended. | User Directive + Claude Fable 5.1 |
| 2026-09-21 | ADR 020 second pass: the IBKR paper Gateway (4002) is legacy, by hand only (`POST /api/ibkr/gateway-mode`), never an automatic fallback -- `IBKR_PAPER_GATEWAY_FALLBACK = False` gates follow-Gateway's live -> paper leg (a paper login beside a live session is read-only and carries no tape), and its desk button and "Use paper Gateway" CTA are removed. Bot scope is enforced in one place: a bot fires only on an allowlisted symbol whose depth line the backend holds (`409 BOT_NO_DEPTH_LINE`, "open its Level 2 or record it"). A Sim scratch-account unwind publishes `practice_rewind` on the bot audit stream and `last_rewind` on the session payload; bots re-read the ledger. Invariant #7 and §5 amended. | User Directive + Claude Fable 5.1 |
| 2026-09-20 | Marketing site split out to [`aaltaay/nova-site`](https://github.com/aaltaay/nova-site): `site/`, the `ai_news_*` digest tooling, its tests, the `ai-news.yml` cron and the Vercel integration all leave this repo. They cost Nova a Vercel preview on every backend PR and a digest pull request **every ten minutes** -- bot churn on a trading repo, for a page that shares no code with the desk. The new repo commits the digest straight to `main` (no branch protection, so the PR workaround is gone) and is public, because a private repo cannot run ~4,300 Actions minutes a month. §4 drops the Vercel row; §8 points at the new home. | User Directive + Claude Opus 5 |
| 2026-09-20 | Per-row scanner Exchange (#90): `backend/ibkr/exchange_lookup.py` buys `row["exchange"]` with ONE paced `qualifyContractsAsync` round trip per NEW symbol, modelled on `ibkr/listing_flags.py`. Never awaited on admit -- `hydrate_rows` only queues, so ADR 010 name-only admission is unchanged; once per symbol per session; backfill only when empty; unknown venues stay blank through `normalize_ib_exchange` so the filter keeps failing open. | User Directive + Claude Opus 5 |
| 2026-09-20 | Scanner table width lock (#276) closed: the shared `.table-wrapper--scanner` `table-layout: fixed` shell already shipped in PR #278 and covers all seven surfaces; the operator lifted the live-desk `do-not-merge` hold. `scannerTableCol.test.ts` now enforces the two acceptance lines that were only stylesheet comments -- every surface uses the shared shell + colgroup, and every shipped column declares an explicit width role. | User Directive + Claude Opus 5 |
| 2026-09-20 | #309 implemented as option (b): `backend/l2/` feeds recorded Level 2 into the one Sim replay surface instead of getting its own scrubber. `sim/history_depth.py` reads the newest book at or before the playhead second (floored, so no lookahead) and `history_playback.snapshot()` publishes `depth` + `depth_available`. Nothing is fabricated: an unrecorded second says so in the ladder rather than showing an empty book, `bid`/`ask` stay null, and a missing, locked or damaged `l2.db` degrades to "not recorded". | User Directive + Claude Opus 5 |
| 2026-09-20 | Ticket TIF is a real per-order field (#91): `ExecutionCommand.tif` (DAY default, GTC), validated in `execution/validate.py`, carried into the IB order and all three bracket legs, persisted in `nova.trade.defaults.v1`; `replace` resends the working order's own TIF. Settings gains **optional** default TP/SL (off by default) that send an opening Limit entry as `operation: "bracket"` through the same `execution.service.execute`. §3 amended per the operator decision on #91 (supersedes "OCO / bracket stay off the manual ticket"). | User Directive + Claude Opus 5 |
| 2026-09-20 | Desktop delivery settled (#347): installer only (portable retired -- it could never self-update); in-app updates via electron-updater's GitHub provider, background download with an operator-chosen "Restart to update" and no install on quit; master merges build and verify the installer plus its `latest.yml` feed but publish nothing -- a GitHub Release comes only from an operator-pushed `vNNN` tag that the pack verifies against the tagged commit. | User Directive + Claude Opus 5 |
| 2026-09-20 | **SIM1 removed** (ADR 019, #315/#310/#340/#309): the synthetic instrument, its looping tape, fabricated book, seeded bars and scanner row are deleted, and the recorder loses every SIM1 exemption -- all recordings are IBKR-sourced, must pass AllLast admission, and an empty segment finalizes `failed`. The Sim venue now trades the loaded replay (historical download or recorded capture): MKT/LMT/STP fills follow `architecture/practice-fills.md`, each marked `fill_estimated` with its `fill_basis`, and protective sources can always close a held position at its last mark. With nothing loaded the desk is empty rather than fabricated. | User Directive + Claude Opus 5 |
| 2026-09-20 | Backlog Map #361 retired. A weekly-refreshed cache of a backlog that changes daily is wrong six days out of seven: it claimed 46 open issues against an actual 12, listed 33 closed issues as open, and routed agents at the retired `BACKLOG.md`. Removed the issue, `sync-map`, `render_map_section` / `splice_map`, the `backlog-map` meta-label filter, and both workflow steps that fed it. The weekly sweep now fails on hygiene gaps instead of commenting on a cache; `backlog_triage.py report` is the rollup. | User Directive + Claude Opus 5 |
| 2026-09-20 | `CHANGELOG.md` **retired** at the owner's request and archived under `_archived/`, completing the ledger retirement. The generator goes with it: `ledger-collate.yml`, `tools/changes_collate.py` / `changes_fragments.py` / `changes_new.py`, `.changes/`, the always-on `change-log.mdc`, and the `CHANGELOG.md merge=union` attribute. The PR body is the only record. Evidence the mirror was not earning its keep: the 09:11 collate run succeeded, pushed its branch, never opened its PR, and left master 11 PRs behind with nobody noticing. §7.1 rewritten. | User Directive + Claude Opus 5 |
| 2026-09-20 | ADR 018 implemented (#302): desk venue and spend arming split into two latches with opposite lifetimes. Venue persists in `desk-venue.json` (owner `sim/mode.py`, `schema_version`, refuses unknown loud, wins over `NOVA_BROKER`); a runtime latch in `ibkr/safety.py` starts every process disarmed in every venue and is armed only by the operator at the existing header padlock (`POST /api/ibkr/arm`). `spend_permitted` (env) and `armed` (runtime) are separate status fields. Venue change disarms; `flatten`/`kill`/`cancel_working` and cancel are exempt. No new UI -- the padlock's `sessionStorage` flag moved to the backend, which also makes pop-out windows and the bot API read one answer. | User Directive + Claude Code |
| 2026-09-20 | Retired the backlog narrative and problem ledger at the owner's request. Archived snapshots are inactive; GitHub Issues/PRs replace their required reads/writes. Removed problem fragments, lifecycle enforcement and regeneration. | User Directive + Codex |
| 2026-09-20 | Next-move footer replaces the Better ask / Follow-up ask paragraphs: a numbered lane menu (`[thread]` `[ship]` `[backlog]` `[decide]`) answered by digit, grounded by `tools/next_moves.py seed` (roadmap NEXT + `backlog next` batch + gated decision + open P0s) and injected by the session brief, which also regains the roadmap line (its regex still matched the retired `Active ops` label). Template in always-on `next-move-footer.mdc`; `next_moves.py lint` + `test_next_moves.py` guard shape, lane order and forbidden phrases. | User Directive + Claude Fable 5.1 |
| 2026-09-20 | Owner explicitly made all verification advisory: merge ready PRs even with running/failed checks; remove required status checks and Desktop wait. Keep force-push/deletion protection and runtime trading gates. Select coverage from the diff; docs/site skip application work, unknown/shared paths run full coverage. #342. | User Directive + Codex |
| 2026-09-20 | Branch cleanup must prove current-tip ancestry, retain unmerged/recreated heads, and use a SHA lease for remote deletion. Safety overrides mandatory head cleanup (#369). | Codex |
| 2026-09-20 | `CHANGELOG.md` is **generated** from merged PR bodies (`ledger-collate.yml` + `tools/changes_collate.py`); agents no longer prepend to it. Fragments under `.changes/unreleased/` are the no-PR escape hatch. `merge=union` on the three ledgers is a transitional net. §7.1 rewritten. #344 WS2. | User Directive + Claude Opus 5 |
| 2026-09-20 | Backlog organised into 11 ranked work packages (one GitHub milestone each, all 46 open issues assigned). `BACKLOG.md` + `knowledge/backlog-packages.json` + `tools/backlog_triage.py` (`next` / `report` / `check` / `sync` / `sync-map`); weekly sweep workflow; pinned Backlog Map #361; budget-aware 2-3 agent wave runner. PRs batch related issues (46 issues -> 25 PRs). | User Directive + Claude Opus 5 |
| 2026-09-19 | Workspace hygiene (WS5 of #344): §5.1 B step 8 "leave it clean"; always-on `workspace-hygiene.mdc` (never stash, one worktree per task, explicit `git add` paths); `tools/repo_hygiene.py status\|fix\|stop-gate` inspects the clone (nothing did before); Claude Code SessionStart brief + blocking one-shot Stop hook; nightly `NovaRepoHygiene` task. | User Directive + Claude Fable 5.1 |
| 2026-09-19 | Version is derived from git, never committed: `VERSION` is a gitignored build artifact, `frontend/package.json` stays `0.0.0-dev`, and the version git hooks are deleted. Rule: **hooks validate, never mutate the index**. WS1 of #344. | User Directive + Claude Opus 5 |
| 2026-09-19 | Deferred ids: GitHub `#NNN` is the durable id; `D-NNN` is a legacy alias that still parses. `next-id` removed (allocation raced -- 8 duplicated ids across 16 issues). `deferred` issues no longer need a `D-NNN` title to be visible. §7.2b / §7.2c / §9 updated. | User Directive + Claude Code |
| 2026-09-19 | Header Paper / Live / Sim practice harness: SIM1 tape + local fills, no Gateway places. Env `NOVA_BROKER` is bootstrap only. | User Directive + Cursor Agent |
| 2026-09-18 | Manual ticket order_type gains `STP LMT` and `TRAIL` (trail $ via stop_price / auxPrice). OCO/bracket stay parked. | User Directive + Cursor Agent |
| 2026-09-17 | ADR 007 source list gains `bot` (localhost bot API, ADR 016). Same execution door; L3 parked. | User Directive + Cursor Agent |
| 2026-09-11 | Nova Delivery board is https://github.com/users/aaltaay/projects/1. New issues/PRs auto-add via workflow; agents attach metadata; 403 is reported, never a new project. | User Directive + Cursor Agent |
| 2026-09-11 | Session lifecycle (§5.1): clean start from `origin/master`; every coding session MUST end with a ready (non-draft) PR. Casual "quick fix" phrasing does not waive. | User Directive + Cursor Agent |
| 2026-09-11 | Public source home is `aaltaay/Nova`. Marketing site CTA points here. `Nova-public` is a private archive. Master protection no longer blocked on "keep private." | User Directive + Cursor Agent |
| 2026-09-11 | GitHub Actions merges ready PRs and deletes closed heads (`pr_delivery.py`). Agents do not wait for a human merge ask. Master protection policy + apply tool also shipped. | User Directive + Cursor Agent |
| 2026-09-11 | Desktop pack builds NSIS installer + portable EXE. Master/main GitHub Release attaches both. Source zip/tar is not the app. | User Directive + Cursor Agent |
| 2026-09-11 | Desktop pack CI uploads `Nova-Setup-vNNN.exe` on every PR. Public revision is `vNNN` (commit count). Master/main creates git tag `vNNN` only. | User Directive + Cursor Agent |
| 2026-09-11 | GitHub `delete_branch_on_merge` is on. Agents still confirm the head is gone (`stale_pr_branches.py`) and the guarded delete command only for a verified safe tip. | User Directive + Cursor Agent |
| 2026-09-11 | After a PR is merged or closed, every agent must delete the head branch in the same session. `github-delivery.mdc` item 8 + `tools/stale_pr_branches.py`. | User Directive + Cursor Agent |
| 2026-09-10 | GitHub delivery is PR-first for code/config/CI/security/rules. Added complete-only issue closure plus conditional Project/Milestone/relationship metadata and strict quality gates through `github-delivery`. | User Directive + Cursor Agent |
| 2026-09-08 | Deferred tracker SSOT is GitHub Issues labeled `deferred`. `DEFERRED_LOG.md` is how-to only. Invariant #6, §7.2c, §9 updated. | User Directive + Cursor Agent |
| 2026-09-08 | Task narrative default home is the PR body (`.github/pull_request_template.md`: What / Why this approach / Verified by / Related issue); `knowledge/task-log/` covers no-PR work. Roadmap note trimmed to a status page (closed detail in `Nova-Roadmap-Archive.md`). §7.2b / §12 updated. | User Directive + Cursor Agent |
| 2026-09-08 | Deferred tracker is GitHub Issues labeled `deferred`; `DEFERRED_LOG.md` is how-to only. Invariant #6 / §7.2c / §9 updated. | User Directive + Cursor Agent |
| 2026-08-31 | Public domain is a marketing page (`site/` on Vercel). Live scanner stays local Vite / Desktop. §4 / §8 updated. | User Directive + Cursor Agent |
| 2026-08-31 | DEFERRED_LOG.md is the to-do / what's-missing list (`deferred_log.py status` / `priorities`); agents must search it before any fix; D-010 parked chart Trend Line. | User Directive + Cursor Agent |
| 2026-08-26 | DEFERRED_LOG.md: parked bugs/features with same respect as PROBLEM_LOG; Lifecycle `deferred_log=`; always-on `deferred-log.mdc`; session brief lists open P0/P1. | User Directive + Cursor Agent |
| 2026-08-25 | Graphify rule always-on; agents must use `tools/graphify_ask.py` (token-savings meter). Rebuild skill stays on-demand. | User Directive + Cursor Agent |
| 2026-08-18 | Gateway connection default is live (4001); paper (4002) is fallback. Invariant #7 and §5 updated -- spend gates unchanged; `auto_live` still NO-GO. | User Directive + Cursor Agent |
| 2026-08-06 | Engineering methodology graft: Superpowers verification/plan teeth + Addy interview/doubt/review as Nova-adapted skills + always-on MDCs; `tools/engineering_skills_audit.py`; domain constitution + zero-hop preserved. | User Directive + Cursor Agent |
| 2026-08-05 | Doc invariants: `tools/doc_invariants.py` + CI gate; §5 trading wording + §10 compliance table corrected; posture-change rule in `doc-invariants.mdc`. | User Directive + Cursor Agent |
| 2026-08-05 | Deploy truth: Railway retired from live docs. Backend is local-only (no cloud host); Vercel remains optional for static frontend only. §4 / §8 updated. | User Directive + Cursor Agent |
| 2026-07-29 | Token economy: §12 no longer embeds full .mdc copies (stale duplicates of live rules). Replaced with a compact index pointing at `.cursor/rules/*.mdc`. Attachment modes: always-on vs glob vs agent-requested. Do not create `.cursorrules`. | Cursor Agent |
| 2026-07-28 | Short-entry invariant (Phase K / ADR 009): Invariant #7 amended -- SELL is risk-reducing unless explicit `short_entry` + `IBKR_SHORT_ENABLED` + fresh IBKR shortability; `auto_live` still NO-GO. | User Directive + Cursor Agent |
| 2026-07-28 | Co-Pilot Coaching Footer extended: §5 now requires two end-of-reply paragraphs -- **Better ask:** (request feedback + one new thing) and **Follow-up ask:** (a concrete next question about this problem/answer + why it is the highest-value follow-up). | User Directive + Cursor Agent |
| 2026-07-28 | Constitution single-sourced: `AGENTS.md` is now the sole constitution text (the two mirrors had drifted -- ADR 007 execution-command schema and stale agent table existed only in `gemini.md`; ADR 007 block ported here). `gemini.md` reduced to a legacy alias that `@`-imports this file; `constitution.mdc` / `self-annealing.mdc` pointers updated. | User Directive + Cursor Agent |
| 2026-07-28 | Co-Pilot Coaching Footer: §5 now requires a short end-of-reply **Better ask:** coaching note (how the request could have been asked better + one new thing learned); skip trivial exchanges at agent judgement. | User Directive + Cursor Agent |
| 2026-07-23 | PROBLEM_LOG mandatory for every agent: strengthened `problem-log.mdc`; Lifecycle requires `problem_log=`; contract regex + subagentStop reminder; agent prompts + ops docs updated. | Cursor Agent |
| 2026-07-18 | Phase G3: `hotkeys` specialist Owned; typed Nova Actions (cancel/exit/Ask±/Bid±); one dispatcher; Trading quick-bar; `auto_live` NO-GO. | Cursor Agent |
| 2026-07-18 | Task log archive: `knowledge/task-log/` + always-on `task-log.mdc`; Lifecycle `task_log=`; scaffold `tools/task_log_new.py`. Captures why/tradeoffs after every material job. | Cursor Agent |
| 2026-07-18 | Agent naming standardization: `nova-router`→`router`, `nova-agent`→`docs`, `security-sentinel`→`security`, `widgets-agent`→`widgets`, `news-catalyst`→`news`; canvases aligned to `agent-<id>`; fleet map Mode column; registry reordered. | Cursor Agent |
| 2026-07-18 | Fleet gap-fill: scaffolded `execution` (audit-only + `execution-continuity.mdc`), `ibkr-ops`, `backtester` (absorbs VectorBT skill cluster), `market-feed`, `news`, and top-of-fleet `daddy` dispatcher; flipped `Agent-Fleet-Map.md` Unowned→Owned / Orphan→Owned; routing + docs + contract updated to 14 agents. | Cursor Agent |
| 2026-07-18 | Agent Fleet Router: `Agent-Fleet-Map.md` domain/skill ownership matrix; `tools/agent_fleet.py` read-only crack index (+ tests); Nova Home "Fleet cracks" rollup; `router` specialist (report-only triage, `agent-router` dashboard); `sessionStart` hook (`tools/session_brief_hook.py`) leads every chat with top-3 cracks; `specialist-routing.mdc` gains an unowned-domain escalation path; fixed missing `hod-momo` in `AGENT_TITLES`. | Cursor Agent |
| 2026-07-16 | Webull Widget Parity Specialist (`widgets`): source-backed stock/day-trading capability map, continuity rule, and dedicated `agent-widgets` dashboard; selected implementations preserve manual controls and IBKR safety. | Cursor Agent |
| 2026-07-16 | Unified agent lifecycle OS: `.cursor/agent-system/` contract+registry; memories in `.cursor/agent-memory/`; specialist-routing + subagentStop hook; agent_contract / sync_agent_surfaces / create_nova_agent tools + CI job; docs/agent-operations.md. | Cursor Agent |
| 2026-07-16 | Docs (`docs`): docs + canvas steward; Diátaxis / markdownlint-cli2 / Vale / Lychee pins; `docs-continuity.mdc`; `tools/nova_docs_inventory.py`; dashboard = Nova Home; merged unmanaged `nova-security-audit` into `agent-security`. | Cursor Agent |
| 2026-07-16 | Security-sentinel baseline enrichment: compensating controls seeded for SEC-001–SEC-006 in `security/findings-registry.json`; `Security-Status.md` open-findings table + verification ledger populated; `security-memory.md` run log updated. Findings open — no product fixes. | Cursor Agent |
| 2026-07-15 | Maintainer sentinel subagent: `.cursor/agents/maintainer.md` + `maintainer-memory.md` (read-only auditor for file limits, secrets, swallowed errors, deps); deterministic `tools/maintainer_checks.py` + tests; `pip-audit` added to `requirements-dev.txt`. Invoke: “Use the maintainer subagent to audit the repo.” | Cursor Agent |
| 2026-07-15 | Audit hygiene pass: `main.py` trimmed to 194 lines (CORS middleware setup extracted to `app_lifespan.configure_cors()`); stale `run-app.mdc` / file-size docs corrected to reflect Nova branding and real line counts; silent-except hygiene fixes in `cache.py`, `logging_setup.py`, `run_api.py`, `routes/news.py`, `news/enrich.py`; new tests for `routes/trading.py`, `ibkr/account.py`, `scan_runners.py`; `requirements.txt` pins recorded for previously-unpinned packages; scratch `_repro_test.py` removed. | Cursor Agent |
| 2026-07-14 | `frontend/src/App.tsx` reduced to 68 lines (Phase 7). Both main.py and App.tsx file-size targets met. | Cursor Agent |
| 2026-07-14 | `backend/main.py` reduced to 199 lines (Phases 1–6 product-health extraction). Compliance audit §2.3 / §10 updated: main.py target met. | Cursor Agent |
| 2026-07-10 | Invariant #7 amended: Alpaca scanning stays read-only; IBKR opt-in module (`backend/ibkr/`) now permitted for paper/live order execution, gated by `IBKR_ENABLED` + `IBKR_LIVE_TRADING_CONFIRMED` flags. Constitution updated first per §1.8. | User Directive + Cursor Agent |
| 2026-04-27 | Complete constitution rewrite — added modularity laws, file limits, compliance audit, self-annealing protocol, coding standards | Antigravity + User Directive |
| 2026-04-27 | Added mandatory git commit & push rule | User Directive |
| 2026-04-13 | Project Constitution initialized | System Pilot |
| 2026-07-15 | Phase A skills library: vendored vectorbt/backtesting/security skills into `.cursor/skills/` + Obsidian [[Skills-Library]] / [[Reference-Repos]] indexes. | Cursor Agent |

---

## Agent Skills Library (Nova Master Roadmap Phase A)

Discoverability for vendored Cursor skills (research/backtest advice only — **never** bypass IBKR execution, single-market-data-feed, or `auto_live` NO-GO):

| Resource | Path |
|----------|------|
| **Skills catalog** | `knowledge/obsidian/00-System/Skills-Library.md` |
| **Study-only repos** | `knowledge/obsidian/00-System/Reference-Repos.md` |
| **Local skill files** | `.cursor/skills/` (pins in `SOURCE-PINS.txt`) |

Pre-existing: `karpathy-guidelines`, `graphify`. Phase A adds: `backtest`, `optimize`, `strategy-compare`, `vectorbt-expert`, `backtesting-frameworks`, `llm-trading-agent-security`.

**Engineering methodology graft (2026-08-06):** Nova-adapted process skills (domain constitution still wins; zero-hop preserved):

| Skill | Path | Role |
|-------|------|------|
| `verification-before-completion` | `.cursor/skills/verification-before-completion/` | Evidence before done/fixed claims (always-on MDC twin) |
| `writing-plans` | `.cursor/skills/writing-plans/` | Bite-sized plans for Plan mode / multi-file work |
| `interview-me` | `.cursor/skills/interview-me/` | One-question requirements interview |
| `doubt-driven-development` | `.cursor/skills/doubt-driven-development/` | Adversarial review of non-trivial claims |
| `code-review-and-quality` | `.cursor/skills/code-review-and-quality/` | Five-axis review before ship |
| `github-delivery` | `.cursor/skills/github-delivery/` | Issue metadata, [Nova Delivery](https://github.com/users/aaltaay/projects/1) board, clean start from `origin/master`, ready-PR finish line, Actions merge, delete head after merge/close, strict gates |

Always-on rules: `verification-before-completion.mdc`, `engineering-methodology.mdc`, `github-delivery.mdc`. Audit: `py -3 tools/engineering_skills_audit.py`. Lineage pins in `.cursor/skills/SOURCE-PINS.txt`. **Not imported:** default subagent-per-task, always-hard brainstorming, replacing `AGENTS.md`.

### Specialized Cursor subagents

Wiring: `.cursor/agent-system/registry.json` · memory: `.cursor/agent-memory/` · ops: `docs/agent-operations.md` · validate: `py -3 tools/agent_contract.py`.

**Zero-hop default:** every subagent below is **opt-in only** — invoke by name when you explicitly want it. The parent Auto session classifies and does multi-domain work in-session by default (no automatic dispatch); see `.cursor/rules/specialist-routing.mdc`.

| Agent | Invoke | Dashboard |
|-------|--------|-----------|
| **router** | “Use the router subagent to triage this” | [agent-router](canvases/agent-router.canvas.tsx) |
| **execution** | “Use the execution subagent to audit trading execution” | [agent-execution](canvases/agent-execution.canvas.tsx) |
| **hotkeys** | “Use the hotkeys subagent to …” | [agent-hotkeys](canvases/agent-hotkeys.canvas.tsx) |
| **ibkr-ops** | “Use the ibkr-ops subagent to diagnose IB Gateway” | [agent-ibkr-ops](canvases/agent-ibkr-ops.canvas.tsx) |
| **market-feed** | “Use the market-feed subagent to fix feed coherence” | [agent-market-feed](canvases/agent-market-feed.canvas.tsx) |
| **hod-momo** | “Use the hod-momo subagent to continue HOD Momo parity” | [agent-hod-momo](canvases/agent-hod-momo.canvas.tsx) |
| **backtester** | “Use the backtester subagent to work the backtest product” | [agent-backtester](canvases/agent-backtester.canvas.tsx) |
| **news** | “Use the news subagent to work the news pipeline” | [agent-news](canvases/agent-news.canvas.tsx) |
| **widgets** | “Use the widgets subagent to map Webull widgets to Nova” | [agent-widgets](canvases/agent-widgets.canvas.tsx) |
| **tester** | “Use the tester subagent to verify …” | `agent-tester.canvas.tsx` |
| **maintainer** | “Use the maintainer subagent to audit the repo” | `agent-maintainer.canvas.tsx` |
| **security** | “Use the security subagent to audit the repo” | `agent-security.canvas.tsx` |
| **docs** | “Use the docs subagent to review documentation” | [nova-home](canvases/nova-home.canvas.tsx) |



---

## 12. Cursor Rules (.mdc files)

Live rule bodies live only under `.cursor/rules/*.mdc`. Do **not** paste full rule text into this file (it double-loads and drifts). Do **not** create a root `.cursorrules` file -- scoped `.mdc` frontmatter is strictly better.

### Index (name -- purpose -- attachment)

**Always-on** (every request):

- `constitution.mdc` -- read AGENTS.md; hierarchy; common violations + context economy
- `specialist-routing.mdc` -- zero-hop default; specialists opt-in only
- `single-market-data-feed.mdc` -- IBKR-only prices; quote-panel symbol gates; HOD pool rules
- `ibkr-gateway-login-warning.mdc` -- loud-warn when Gateway needs login/2FA
- `nova-roadmap-continuity.mdc` -- Master Roadmap phase continuity
- `engineering-standards.mdc` -- Tailwind direction, tests, CI, deps, patterns
- `karpathy-guidelines.mdc` -- think / simplify / surgical / verify
- `deferred-log.mdc` -- check GitHub Issues (`deferred`) before any fix; park known bugs/features; to-do via `deferred_log.py status` / `priorities`
- `task-log.mdc` -- reasoning narrative after material work (PR body first; file when no PR)
- `commit-push-deploy.mdc` -- clean start from `origin/master`; verify, commit, push, open a ready PR; Actions merges it; delete head after merge (+ deploy when applicable)
- `doc-invariants.mdc` -- posture-change same-commit live homes; CI `doc_invariants.py`
- `self-annealing.mdc` -- root-cause fix protocol on any error
- `verification-before-completion.mdc` -- no done/fixed claims without fresh evidence
- `engineering-methodology.mdc` -- soft TDD + plan/interview/doubt/review skill map
- `github-delivery.mdc` -- issue metadata, [Nova Delivery](https://github.com/users/aaltaay/projects/1) board, clean-start + ready-PR session gates, Actions merge of ready PRs, delete head after merge/close, strict gates
- `persisted-state.mdc` -- cache files need owner + invalidation + schema_version
- `workspace-hygiene.mdc` -- never stash; one worktree per task; finish with a clean tree; `tools/repo_hygiene.py status|fix|stop-gate`
- `graphify.mdc` -- vault/decision questions: `py -3 tools/graphify_ask.py query` + savings meter
- `next-move-footer.mdc` -- numbered Next move menu at the end of every substantive reply; seed `py -3 tools/next_moves.py seed`; lint `next_moves.py lint`

**Glob-scoped** (attach when editing matching files; `alwaysApply: false`):

- `backend-modularity.mdc` -- `backend/**/*.py` -- no logic in `main.py`
- `frontend-modularity.mdc` -- `frontend/src/**/*.{ts,tsx}` -- no logic in `App.tsx`
- `file-size-limits.mdc` -- backend + frontend src -- soft 400 with a one-concern reason, no growth without one, 800 ceiling
- `centralized-constants.mdc` -- backend + frontend src -- tunables in domain modules
- Continuity rules (already glob): `hotkeys-continuity`, `docs-continuity`, `execution-continuity`, `widgets-continuity`, `security-continuity`

**Agent-requested** (name + description always visible; body fetched on demand):

- `browser-testing.mdc` -- web verification / Playwright / agent-browser
- `run-app.mdc` -- how to run/open Nova locally
- `nova-os-continuity.mdc` -- Nova OS engine phases (retired, ADR 025; history)

Karpathy full text: `.cursor/rules/karpathy-guidelines.mdc` (also `.cursor/skills/karpathy-guidelines/`).
Browser testing full text: `.cursor/rules/browser-testing.mdc`.
