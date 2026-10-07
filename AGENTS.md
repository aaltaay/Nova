# 🏛️ AGENTS.md — Project Constitution (Law)

> **Single source of truth.** Every agent reads this file; `CLAUDE.md` imports it.
>
> **Status:** ENFORCED — Active governance document
> **Last Updated:** 2026-09-29
> **Project:** Nova — Stock Alert Automation System
> **Enforcement:** Every AI agent (Cursor, Antigravity, any LLM assistant) MUST read this file before writing ANY code. Violations are NEVER acceptable.

---

## Retired ledgers (owner instruction, 2026-09-20)

`BACKLOG.md`, `PROBLEM_LOG.md` and `CHANGELOG.md` are retired and archived under
`docs/archive/`. Do not read, update, regenerate, or require them during ordinary
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
| 7 | **Broker Execution Gate** | Alpaca-sourced scanning is permanently read-only. Trade execution is permitted ONLY through the explicit opt-in `backend/ibkr/` module. Gateway connection default is **live** (port 4001). The IBKR paper Gateway (4002) is **legacy**: by hand only (`POST /api/ibkr/gateway-mode {"mode":"paper"}`), never an automatic fallback -- `IBKR_PAPER_GATEWAY_FALLBACK` is off by default because a paper login beside a live session is read-only and carries no tape (ADR 020). Spending still requires `IBKR_ENABLED=true` and `IBKR_ORDERS_ENABLED=true`; live money also requires `IBKR_LIVE_TRADING_CONFIRMED=true` in `.env`. No other module may place orders. **Short entry (ADR 009, ADR 048):** every SELL is risk-reducing unless an explicit `short_entry` opt-in on the execution command passes the one short check (`backend/short_sale/`): a limit price, never while the account holds the stock long, a margin account with $2,000 of equity, IBKR's tick-236 borrow from the cache covering the order plus the short held and in flight, and margin with a 25% liquidation cushion. Live also needs `IBKR_SHORT_ENABLED=true`, which only the operator sets, last, after the Live short proof (ADR 048); Paper and Sim refuse every opening short (`PRACTICE_NO_SHORTS`) until ADR 048's step 2. A BUY that covers a short is a close: never locked by the day lock, never held to buying power, never past flat. Never infer shorts from side + flat position. `auto_live` remains NO-GO, and a bot never trades Live. |
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
`last: null`) load as quotes; a print that does not set a price (odd lots and
the rest of "Prints that set a price" below) never sets a capture's last or
fills a practice order. A listing row whose manifest `source`
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
`fidelity` includes `l2_offered`, `l2_coalesced` (every book IBKR sent that the recording did not keep, at the IBKR bridge or by event time; ADR 033), `invalid_timestamp_rows`,
`timestamp_regressions`, `last_stream_ts`, `tape_resubscribes` and
`tape_losses: [{at, cause: "ib_error" | "stale", detail}]` (the recording's
tape line lost while it ran, newest last, at most `CAPTURE_TAPE_LOSS_KEEP`;
both carried across segments of the day, #525). Diagnostics are counts except
`legacy_schema` / `l2_decimated` (booleans), `last_stream_ts` (per-stream event
timestamps) and `tape_losses`.
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

**The tape line (#525).** A recording can lose its AllLast line while its book
keeps coming (IPDN and WHLR, 2026-09-23 09:46:40). `ibkr/tape_line.py` maps
every AllLast request id to its symbol, so an IB error names its line with or
without a contract; a non-warning error on a live line's own request id ends
that line (cancelled, so the next request is a real one -- ib_async hands back
a line it still has registered), and every end is logged at WARNING. The
recording's producer (`/api/capture` `sessions[SYM].producer`, which also
carries `line_since`, when its line opened) then reads `disconnected` with
`ended: {at, cause, code, message, req_id}`. `capture/tape_watch.py` also calls a line dead when no print
came for `CAPTURE_TAPE_STALE_SEC` while the book updated within
`CAPTURE_TAPE_BOOK_FRESH_SEC` (a quiet name looks the same; asking again is
harmless). Either way the keepalive asks for the tape only -- the depth line is
left alone -- once IB's 15 s same-instrument rule allows
(`CAPTURE_TAPE_RENEW_DELAY_SEC`), backing off by `CAPTURE_TAPE_RESUBSCRIBE_MIN_SEC`
over a streak of outages (a quiet name that prints now and then), and says so:
a `capture_stopped` row with `reason: "tape"` (never a segment reason: the
recorder did not stop; one row per streak) whose `resumed` turns true when a
print arrives on a new line, `reacquired`
on the session, and the manifest's `fidelity.tape_losses` /
`tape_resubscribes`. A halted name is never a dead line (#722; MI on 2026-10-05
was LULD-halted twice and its line was dropped and asked for again through both):
while `ibkr.halt_status.halted_now` says the symbol is halted, no outage opens and
an open one's new line is not dropped again (a pending ask still goes out, so the
reopening finds a line), and the silence counts from the last moment it was seen
halted. A Record hold younger than `CAPTURE_HOLD_ORPHAN_GRACE_SEC`
is a start in flight and is never released as an orphan by a status poll. A
resume never holds IBKR's lines for a start the recorder would refuse (#698): with
`CAPTURE_MAX_CONCURRENT` other symbols recording it opens no line (the attempt is
logged and counted), and a start refused after its lines opened releases them.

**Time & Sales comes back by itself (#698, operator report 2026-10-02: "should that
be fully self-healing?").** At 07:54 ET three recordings and two resumes that never
let go held IBKR's tick-by-tick lines; IBKR refused AMOD's with 10190 after the
request, and the socket sat on a dead line reading ERROR until the operator switched
tabs. Owner `line_lending/tape_heal.py`. While a `/ws/ibkr/tape/{symbol}` socket
watches a symbol whose AllLast line IBKR refused or ended (or a heartbeat finds it
down), one task per symbol brings it back: after a cap refusal (10190) it first
cancels every line no viewer watches (`tape_line.release_idle`: a closed socket's
line lingers 16 s for a remount, still counting against the cap), then, for the tab
in front by the focus sensor (else a socket opened with `front=1`, or a panel
outside a Trader tab), has auto-record give back its lowest-ranked line
(`auto_record.make_room_for(symbol, tape_refused=True)`); a recording the operator
started is never touched. It asks again once IBKR's 15 s same-instrument rule allows,
plus `LINE_LENDING_TAPE_HEAL_BACKOFF_SEC` after refusals in a row (at once when a
hidden tab comes to the front), never while IBKR is not ready, and never stops while
a socket watches. The socket's frames: IBKR's own `{"type": "error", message}`, then
the healer's `{"type": "error", message, retry_at}` (what it freed, or who holds the
lines, and when it asks again; epoch seconds), and `{"type": "subscribed"}` once the
new line stood `LINE_LENDING_TAPE_HEAL_CONFIRM_SEC` without IBKR ending it. The desk
reads RETRYING while `retry_at` is set, and any print clears a stale error.

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
`counts`, `last_write_ts`, `dir`, `reacquired` -- lines asked for again after a
Gateway drop or a lost tape), `capture_resume: object[]`
(`symbol`, `pending`, `attempt`, `max_attempts`, `next_at`, `reason`, `gave_up`,
`gave_up_reason`) and `capture_stopped: object[]` -- per symbol, the last stop
the operator did not ask for (`symbol`, `at`, `reason`, `error`, `dir`,
`counts`, `resumed`; `reason` is a segment reason, or `tape` for a lost tape
line while the recording ran), kept until that symbol records again or the operator
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

### The replayed session's previous close (#542)

Owner `sim/prior_close.py`. The `prev_close` a Sim replay measures change and
Gap% from -- `replay_quote.prev_close`, a loaded capture's quote and ticker
projections (one value per load, whichever row is read), the historical
snapshot's `prev_close` and the eyes' replays -- is, first answer wins:
IBKR's tick-9 close recorded with the Session Record (the most common positive
`prev_close` on its quote rows from 04:00 ET of that day); the leaderboard's
`prev_close` for that symbol-day (recorded rows before reconstructed ones, the
day's most common value; read read-only, so a read never creates the store);
IBKR's regular-hours daily close of the prior session, stored with a
historical download of that symbol-day; else `null` -- a stated absence, no
change and no Gap%. Never the prior session's 15:59 one-minute close (the last
trade before the closing auction) and never a stored daily bar (fetched with
extended hours, it closes on the last after-hours trade).

Session Record quote rows add `prev_close: number | null` -- IBKR tick 9 on the
symbol's live L1 line when one is open (Record's own tape and depth lines
carry no close), `null` otherwise. Historical download jobs add `prior_close:
{close, date, source: "ibkr_rth_daily"} | null` -- IBKR's daily TRADES close
with `useRTH` dated the exchange session before the job's day, asked once per
run before the first page and paced like one; `null` when IBKR's series lacks
that session (never an older close), absent until IBKR has answered. The live
ticker snapshot's `prev_close` falls back to the L1 line's tick 9, then today's
leaderboard, and is `null` rather than a daily bar.

### Massive flat files in Sim replay (ADR 046, operator ask 2026-10-06)

"u wanna populate the data inside the sim? that way when we go back in time, the data we downloaded all of
its information gets picked up?", then "1 go also do the bid and ask." A historical window comes from an IBKR
download or from the operator's Massive flat files (owners `sim/massive_files.py` the files,
`sim/massive_read.py` the import itself, `sim/massive_import.py` + `sim/massive_worker.py` its job and process,
`sim/massive_store.py` the store, `sim/history_quotes.py` the NBBO, `sim/massive_days.py` the days on disk; on the
desk `frontend/src/sim/massiveDaysStore.ts` and the Sim panes).

- **The files.** `NOVA_MARKET_DATA_DIR` (default `E:\Nova\massive`), laid out as Massive serves them:
  `<root>/<trades_v1 | quotes_v1 | minute_aggs_v1>/YYYY/MM/YYYY-MM-DD.csv.gz`, one gzip CSV per dataset per day,
  every ticker, sorted by ticker. A file counts only whole (a `.part` still arriving does not).
- **Choosing the source.** `POST /api/sim/history` and `POST /api/sim/history/select` add `source: "auto" | "ibkr"
  | "massive"` (default `auto`). A download takes the Massive files when the day's trades file is on disk, else
  IBKR; `kind` does not matter for Massive (one import fills trades, bars and quotes). A selection keeps a
  Massive import of the window, else an IBKR download of it, else takes the Massive files when on disk -- and
  **starts the import** when none is running or complete, loading the window empty until the desk's quiet
  re-select folds it in. `POST /{job_id}/pause` and `/resume` route by the job's store; a Massive resume
  imports the window again from the start.
- **Jobs.** The listing (`GET /api/sim/history`) returns IBKR downloads and Massive imports together, most
  recently updated first. Every job carries `source` (`ibkr_historical` | `massive`). A Massive job is shaped
  like a download (`id`, `kind: "trades"`, `status`, `ranges`, `count`, `volume`, `progress_pct`, `eta_seconds`,
  `stale`, ...) with `precision: "nanoseconds"` and adds `stage: "reading" | "saving" | null`, `stages:
  {trades_v1, quotes_v1, minute_aggs_v1: percent} | null`, `scan_pct`, `bar_count`, `quote_count`,
  `quote_status: "complete" | "none" | "not_downloaded" | null`, `files: {trades, quotes, minute_aggs}`,
  `elapsed_sec`. `status` is `queued | running | complete | failed | paused | interrupted` (a running job
  rewritten by no live import for 60 s). The listing adds `massive: {available, reason, root, store,
  trade_days, quote_days, first, last, store_error}` -- `store_error` names why the import store could not be
  read (its imports are then not listed), null when it could.
- **Days on disk.** `GET /api/sim/history/massive/days` -> `{schema_version: 1, available, reason, root, days:
  [{date, trades, quotes, minute_aggs}]}`, newest first, the folder walked at most once a minute;
  `GET /api/sim/history/massive/{date}` -> `{date, available, reason, trades, quotes, minute_aggs}` (422 for a
  bad date; `available` false with the reason when that day's trades file is not on disk).
- **The import.** Its own process (`python -m sim.massive_worker --job-id ID`, frozen `nova-api.exe
  --massive-import --job-id ID`), below normal priority, one at a time; the three files are read side by side,
  each to the end of the ticker's block, every row parsed with the csv module. The window's prints (typed),
  1-minute bars that lie wholly inside it and NBBO rows -- plus the quote standing at the window's open -- are
  written in one transaction. More than 500,000 prints (`SIM_HISTORY_MAX_SELECTION_PRINTS`) or 4,000,000 quotes
  (`SIM_MASSIVE_MAX_SELECTION_QUOTES`) is refused with the reason before anything is written. A day without its
  quotes file imports trades and bars with `quote_status: "not_downloaded"`; a download or selection after
  that file arrives imports the window again, and the window imported before keeps playing until the new one
  replaces it. Pause ends the process (`paused`); a process that ends otherwise leaves `failed` with its exit
  code.
- **The store.** `<root>/sim/replay.sqlite3`, its own `PRAGMA user_version = 1` (unknown versions refuse):
  `jobs (id, payload)`, `prints (job_id, ordinal, ts, ns, price, size, exchange, exchange_id, conditions,
  correction, trf_id, sequence, tape, sets_price)`, `candles (job_id, ts, payload)`, `quotes (job_id, ordinal,
  ts, bid, bid_size, bid_x, ask, ask_size, ask_x, conditions, indicators)`. The IBKR download store is never
  touched.
- **Prints.** `ts` is the SIP time in epoch seconds (float), `ns` the nanoseconds; each adds `exchange_id`,
  `correction`, `trf_id`, `sequence`, `tape`, `sets_price` and `unreported: false`. `sets_price` is true when the
  conditions miss `SIM_MASSIVE_NO_PRICE_CONDITIONS` (2, 7, 10, 13, 15, 16, 20, 21, 22, 29, 37, 38, 52, 53) and the
  correction is 0 or 12; corrections 1, 7, 8 show and set nothing; 10 and 11 are dropped. Last, volume, high,
  low, candles and practice fills read only prints that set a price.
- **The snapshot** adds, for every window, `bid_size`, `ask_size`, `bid_exchange`, `ask_exchange`, `quote_ts`,
  `quote_source: "massive_nbbo" | null`, `quote_status` and `sides_nbbo: integer` (all null / 0 for an IBKR
  download). For a Massive window `bid` / `ask` are the last NBBO row at or before the playhead, never after;
  each tape print's `side` / `bid` / `ask` come from the last NBBO row strictly before it by the live tape's
  rule, `side_source: "nbbo"`; with no recorded book `depth` is the NBBO as one level per side, `l1_fallback:
  true`, `source: "massive_nbbo"`. The selection adds `source`, `quote_status`, `quote_count`, `bar_count`.
- **Fills and charts.** A Massive window's practice reference carries `bid` / `ask`: a marketable order fills at
  the far side (`fill_basis: "quote"`). Its candles come from its own prints and its own 1-minute bars only --
  never the IBKR chart store, which a Massive import never writes.
- **On the desk.** The Sim Day calendar marks a day whose trades are in the files (a bar under the number; the
  title says whether its bid/ask is there) and lets it be opened, whatever else is on file. A Sim tab on such a
  day offers **Load from files** with no Gateway gating; its import has its own slot (an IBKR download of
  another window does not block it), Stop pauses it, and the window loads when it completes. The quote card and
  the ticket take `bid` / `ask` (a Market order is priced at the far side), Time & Sales dims prints with
  `sets_price: false` and says its colours come from the NBBO, and the Level 2 note reads "Best bid / ask
  (NBBO) at HH:MM:SS ET · no depth in the files", or why there is no quote (not downloaded yet, on disk now --
  load again, none in the window). The quiet re-select keeps the loaded window's source and reloads a Massive
  window once, when an import of it completes with something the loaded copy lacks.

### Agents find stock-days and show them in the Sim (ADR 050, operator ask 2026-10-06)

"Go to a small-cap stock that increased, where the high of the day was 300% ... punch it in on the simulator so I
could see it", then "this is just going to be for agents for now ... like some secret endpoints that they can
manipulate and show me." Owners `backend/day_movers/` (the index), `backend/agent_desk/` (the routes, commands,
dictionary), `research/movers/` (the builder), `frontend/src/agent_desk/` (the desk side), `tools/nova_agent.py`
and `.claude/skills/nova-sim-navigator/`. Nothing here places, stages or cancels an order, or arms the desk.

- **The index.** `<NOVA_MARKET_DATA_DIR>/movers/day_movers.sqlite3` (`PRAGMA user_version = 1`; an unknown
  version refuses), written only by `research/movers/` through `day_movers.store`:
  - `sessions (session_date PK, prev_date, tickers, rows, minute_bars, builder, built_ts, note)` -- one per
    session built: `tickers` the day bars that session, `minute_bars` 1 when the minute file was read.
  - `movers`, primary key (session_date, symbol): `kind, prev_date, prev_close, prev_volume, split_factor,
    split_listed, split_suspect, open, high, low, close, volume, pm_high, pm_low, pm_volume, ah_high, ah_low,
    ah_volume, day_high, day_high_ts, day_low, day_low_ts, dollar_volume, first_ts, last_ts, high_pct, low_pct,
    close_pct, gap_pct, up10_ts, up20_ts, up50_ts, up100_ts, up300_ts, down10_ts, down20_ts, down50_ts`.
    - `kind`: the Massive reference type (`CS`, `ADRC`, `WARRANT`, ...; null when the reference has none).
    - `prev_close`: the official close of `prev_date`, the session before in the files, times `split_factor` for
      a split Massive lists or `confirm_splits.py` proved executing in between (`split_listed` 1); null when the
      stock did not trade that session, never an older close. `prev_volume` is that session's volume on today's
      share basis.
    - `open` / `high` / `low` / `close` / `volume`: the day bar -- regular hours, the official close.
    - `pm_*` 04:00-09:30 ET, `ah_*` 16:00-20:00 and `day_high` / `day_low` 04:00-20:00 come from the minute bars,
      with the start of the first minute that printed each (`*_ts`, epoch seconds); `dollar_volume` is the
      minutes' close x volume; `first_ts` / `last_ts` the first and last minute that printed.
    - `*_pct` are fractions against `prev_close` (`gap_pct` from the 09:30 open; null without a prior close);
      `upN_ts` / `downN_ts` the first minute whose high reached +N% (whose low reached -N%).
    - `split_suspect` 1 when the open is 1.8x or more (0.7x or less) the prior close and no split is listed.
    - A row is kept when the high is +10% or the low -10%, the close or the gap is 5% either way, or a split
      suspect; without a prior close, when the day's high is 20% over its low.
  - `sec_shares (symbol, cik, as_of, filed, shares, form)`: shares outstanding a filing reported as of `as_of`,
    from SEC's companyfacts (`research/movers/export_sec_shares.py`; several share classes keep the largest).
  - `splits (symbol, execution_date, split_from, split_to)`: the split list the builder adjusted prices by.
- **Routes** (`/api/agent`, loopback clients only; every write needs `X-Nova-Api-Key` even on loopback;
  percentages on this wire are percent points):
  - `GET /api/agent` -> `{schema_version: 1, endpoints: [{method, path, does}], index: {ok, error, path,
    sessions, first, last, files_last, behind, missing, rows}, dictionary: {entries, error}, desk: {listening,
    last_poll_ts, window_id}, rules: string[]}` (`behind`: minute-file days newer than the newest session built;
    `missing`: minute-file days not built; both null when the folder cannot be listed).
  - `GET /api/agent/movers` -> `{schema_version: 1, query, units: "percent", count, rows[], summary, excluded,
    coverage, notes[]}`. Query: `from`, `to`, `symbol`, `kinds` (default `common`: `CS`, `ADRC`, and a ticker of
    1-4 letters the reference has no type for), `price_min` / `price_max` (the prior close), `high_min` /
    `high_max`, `low_min` / `low_max`, `close_min` / `close_max`, `gap_min` / `gap_max` (percent), `close_pos_min`
    / `close_pos_max` (0 = closed at the day's low, 1 = at its high), `giveback_min` / `giveback_max` (the share
    of the run over the prior close given back by the close, 0-1), `high_after` / `high_before` (`HH:MM` ET),
    `volume_min`, `dollar_volume_min`, `float_max` (shares), `float_unknown` (`exclude` | `include` | `only`),
    `replayable` (only days whose trades file is on disk), `splits` (`exclude_likely` default | `include` |
    `only_suspects`), `sort` (`newest` | `oldest` | `high` | `low` | `close` | `gap` | `volume` |
    `dollar_volume`), `limit` (default 25, at most 500). A row is `{date, symbol, kind, prev_close, open, high,
    low, close, volume, dollar_volume, day_high, day_high_et, day_low, day_low_et, pm_high, ah_high, high_pct,
    low_pct, close_pct, gap_pct, close_pos, giveback, first_et: {up10, up20, up50, up100, up300, down10, down20,
    down50}, replayable, split: null | "listed" | "suspect" | "likely_split", float: {shares, source:
    "recorded" | "enrichment" | "sec_shares_outstanding" | null, as_of, proof: "pass" | "fail" | "unknown"} |
    null}` (`float` only when `float_max` is asked). A split suspect is a `likely_split` when it traded no more
    shares than `prev_volume`, and no split at all (`null`, a real overnight move) when it traded 3x or more
    (#772). `summary` covers every match, not only the rows returned: `{matched,
    closed_above_prior_close, closed_above_open, closed_top_third, closed_bottom_third, median_high_pct,
    median_close_pct, median_giveback}` (shares of `matched`, in percent). A search matching more than
    `AGENT_MOVERS_MAX_SCAN` stock-days answers `too_broad: true` with the count only. `GET
    /api/agent/movers/{date}/{symbol}` -> `{schema_version, row, coverage}` (`AGENT_NOT_IN_INDEX` 404).
    Refusals: `AGENT_INVALID` 400 with `field`, `AGENT_INDEX_UNAVAILABLE` 503 (not built, or unreadable).
  - `POST /api/agent/show {symbol, date, at?: "run" | "drop" | "high" | "low" | "open" | "premarket" | "HH:MM",
    confirm?: boolean}` -> 202 `{command}`. A run or a drop parks five minutes before its first +20% (else +10%)
    mark; a mark the stock already stood at within five minutes of its first print is where it opened, so the
    next mark it reached later (+50%, +100%, +300%) is taken, else the day's high (low). The window loaded is
    135 minutes from the quarter hour 30 minutes before the park (so the charts show what came before), with 60-
    and 30-minute windows to fall back on when the Sim's print or quote cap refuses it. Refusals are `{detail: {reason, error, ...}}`: `AGENT_INVALID` 400 (also a day not over yet),
    `AGENT_NOT_ON_FILE` 404 (no trades file for that day), `AGENT_NO_DESK` 409 (no main desk window listening),
    `AGENT_AT_STAKE` 409 with `at_stake: {venue, safe, items: [{kind, venue, symbol, text}], unknown: [{kind,
    error}]}`. A new show replaces one not finished (`cancelled`).
  - `POST /api/agent/move {to?: "high" | "low" | "run" | "drop" | "open" | "premarket" | "HH:MM", by_min?: number,
    paused?: boolean, confirm?: boolean}` -> 202 `{command}`; `AGENT_NOTHING_LOADED` 409 unless the Sim holds a
    window. A target outside the loaded window loads one around it (`AGENT_AT_STAKE` as a show's).
  - `GET /api/agent/commands/{id}?wait=` -> `{command}`, waiting up to `wait` seconds (at most 30) for a change;
    `GET /api/agent/commands` the newest; `POST /api/agent/commands/{id}/cancel`. A **command** is `{id, kind:
    "show" | "move", status: "queued" | "running" | "done" | "failed" | "expired" | "cancelled", created_ts,
    updated_ts, args, plan, step, steps: [{step, ts, text}], result, error, claimed_by}`. A show's `plan` is
    `{symbol, date, at, anchor_et, park_et, park_ts, park_words, window, fallback_windows, switch_venue,
    in_index}` and a move's `{symbol, date, paused, target_ts, target_et, target_words, loaded_start_ts, window,
    fallback_windows}` (`park_words` / `target_words`: where it lands, in words), a window `{start, end, start_ts,
    end_ts}` (ET `HH:MM` and epoch seconds). A command no desk window takes within `AGENT_COMMAND_CLAIM_SEC`
    (15 s) expires. One a window took and never reported on within `AGENT_COMMAND_FIRST_REPORT_SEC` (10 s) goes
    back in the queue -- a reloaded or closed window's poll can still be waiting on the server -- at most three
    times, and the desk's poll gives a command back at once when its request is gone; one the desk stops
    reporting on for `AGENT_COMMAND_LEASE_SEC` (90 s), or still running after `AGENT_COMMAND_STALE_SEC`, fails.
  - `GET /api/agent/desk` -> `{schema_version: 1, venue, live_edge, sim: {session_date, playhead_et, paused,
    loaded: {source, symbol, date, start, end} | null} | null, focus: {page, symbol, window_id} | null,
    listening, at_stake}`.
  - `GET /api/agent/dictionary` -> `{schema_version: 1, error, entries[]}`; `POST /api/agent/dictionary {entry}`
    adds or replaces an operator entry by `id`; `DELETE /api/agent/dictionary/{id}`.
  - The desk's side (keyed, the long poll too): `GET /api/agent/desk/next?wait=&window_id=` (the main window's
    long poll, `{command | null}`, the command now `running` and its) and `POST /api/agent/desk/commands/{id}
    {status: "running" | "done" | "failed", step, text, result?, error?}` -> `{command}` (a command already
    cancelled or expired answers as it is, and the desk stops).
- **The dictionary** (operator: "If I'm obviously asking for a command ... I want it to be added to our
  dictionary"): `<cache_dir>/agent-dictionary.json` = `{schema_version: 1, entries: [{id, phrases: string[],
  means, call: {method, path, params?, body?}, then?, notes?, added_by, added_at, updated_at}]}`, written through
  a temp file and a rename. Seed entries live in code (`seed: true` on the wire); an operator entry with a seed's
  id replaces it. An unknown version or an unreadable file reads as the seeds with the error stated, and writes
  are refused `AGENT_DICTIONARY_UNREADABLE`. Nova defines no shape words: an agent turns words into the numbers
  above, asks when they have no agreed meaning, and saves what the operator confirms.
- **At stake** (operator: switch "when nothing is at stake"; owner `agent_desk/safety.py`): on the venue the
  desk would leave, a position or a working order (Paper's ledger, Live's IBKR cache), the Bot on, an open bot
  or Nova trade, a Nova stock mode or approval, or the desk armed; and, when the show or move loads another Sim
  window (which starts the Sim's scratch account over), the Sim account's positions and working orders. A check
  that cannot be read is at stake too. `confirm` is sent only after the operator agreed in the chat.
- **The desk side.** Only the main window (never a Trader pop-out, the sample desk or the demo) long-polls for
  commands. It runs them with the desk's own steps -- venue, Sim day, Trader tab, the Massive window, the wait
  for its import, the playhead (paused) -- reports each step, and shows a notice of what it is doing. A window
  refused for the print or quote cap is retried with the plan's narrower windows.
- **Float** (operator: proven, else unknown; owner `day_movers/floats.py`): `float_max` passes on the float
  Nova knew that day (the desk's enrichment snapshot in `archive.db`, 2026-07-28 on) at or under the limit, or
  on `sec_shares` at or under the limit -- a float cannot exceed the shares outstanding: the newest count filed
  by the session, as of a day on or before it and at most `DAY_MOVERS_SEC_SHARES_MAX_AGE_DAYS` (120) before it,
  put on the session's basis through the splits listed in between. Shares issued after the count are not in
  it, and the answer carries its `as_of`, `filed` and `age_days`. A snapshot over the limit fails; anything
  else is unknown, never today's float.

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

### Which backend answers (operator report, 2026-09-24)

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

### Where Nova keeps its data (operator ask, 2026-09-24)

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

### Why the Gateway needed a phone login; premarket evidence (#14)

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

**The gap is never yesterday's** (operator report, 2026-09-24: GCTK read
+9.9% on the Focus rail all premarket while it traded +103% on its prior
close). IBKR's open tick (14) names the previous session's open until the
regular session opens, so it counts as today's open only from 09:30 ET on an
exchange day (`ibkr/open_tick.py`, for the streaming line and
`snapshot_quotes`). Before then a Gainers / Losers row's `open` and
`gap_percent` are `null` (unknown, never 0); a repriced row takes the quote's
open over one it stored. A Gappers row's `gap_percent` is its `change_pct` --
the move against the prior close -- in its roster rows and in every
`price_patch` tagged `gappers` (`gapper_view.patch_for_table`); the patch used
to carry the Gainers row's open-based gap, so the Gappers table, the Focus rail
and the Trader tab showed yesterday's open-to-close move, frozen, and flipped
to the real move on each roster replace.

**Live rows state their halt** (#487, operator decision 2026-09-24): every row
`surface_rows` serves carries `halted: boolean | null` -- is the symbol halted
now -- read when the row is served, from memory only
(`ibkr.halt_status.halted_now`: no network or database wait, safe on the IB
loop). IBKR decides where Nova holds a live L1 line (session ready) whose
incoming tick 49 has reported: `0` is `false`, `1` / `2` `true`, `-1` or no
report yet no answer -- the Level 2 header's precedence. Otherwise the Nasdaq
Trade Halt RSS decides while it is answering (its last read succeeded and is
younger than `NASDAQ_TRADE_HALT_RSS_FRESH_SEC`): an open row (no trade
resumption, or one still ahead) is `true`, no open row `false` -- except while
the read lists a market-wide circuit breaker, which carries no end time, so
nothing reads `false` then. Anything else is `null`: not known, never "not
halted", and a halt is never inferred from quiet tape. It is a view over the
row, stamped on the served copy and never written into the cache (ADR 008);
The scanner socket also sends `halt_patch` (#571): `{type: "halt_patch",
rows: [{symbol, halted: boolean | null}], ts}` when tick 49 changes, on an RSS
refresh (including removals or an unavailable feed), and when an RSS answer
ages out. It updates only the served halt overlay, including a frozen table;
cache rows, membership, prices, metadata and timestamps stay untouched. A
history desk ignores live halt patches. The Scanner's Halted chip filters live and
played-back boards alike -- it keeps `true` and `null` and drops `false` -- and
a row stated halted shows the HALTED mark.

### Float credibility and short-interest dates (#532)

Every float and short-interest figure is Yahoo's (`fundamentals.py`). The
fundamentals payload (`fetch_fundamentals`; the ticker detail's `fundamentals`)
keeps `shares_outstanding` and adds `held_percent_insiders` (Yahoo's
`heldPercentInsiders`, a fraction: 0.128 = 12.8%), `short_interest_ts` (Yahoo's
`dateShortInterest`: epoch seconds of the FINRA settlement the short interest
is from), `float_contradicted: boolean | null`, `float_contradicted_reason:
string | null`, `short_above_float: boolean | null` and
`short_above_float_reason: string | null` -- each `null` when Yahoo gives none.
`short_ratio` is Yahoo's own ratio (short interest over Yahoo's average
volume), never FINRA's days to cover. A float is **contradicted**
(`fundamentals.float_credibility`, pure) when it is under
`FUNDAMENTALS_FLOAT_MIN_NON_INSIDER_SHARE` (0.5) of shares outstanding x (1 -
insiders): `true` when that fires, `false` when shares outstanding and insiders
are known and it does not, `null` otherwise; the reason names the counts. A
float above shares outstanding is never flagged -- the share count is the stale
field there and it cannot pass a low-float gate falsely. **Short interest above
the float is a warning, never a gate** (operator decision 2026-09-24: "make sure
it never blocks those setups, just gives an on-screen warning"):
`fundamentals.short_above_float` (pure) is `true` when short interest exceeds
the float, `false` when both are known and it does not, `null` otherwise. It
cannot tell a stale float from shares lent more than once, which is what a
heavily shorted name looks like, so no gate reads it: the desk shows the short
interest as "9.0M!" in amber with the reason first on its hover (scanner Short
Int., Fundamentals panel, Trader side column) and adds the reason to the float's
hover; `/api/why` facts carry `short_above_float` and the short-interest
check's `detail` adds the reason (its state is unchanged), as does the stock
read's short-interest row. Until 2026-09-24 (#532 follow-up) the same condition
also set `float_contradicted`, so a squeeze with more than 10M shares
outstanding could be refused a Low Float gate. Every scanner row
(`scanner_surface.surface_rows` -> `mover_enrich_view.decorate_rows`) adds
`shares_outstanding`, `short_interest_ts` (only while the row's
`short_interest` is the cached figure, else `null`: a date is never pinned on
another report), `float_contradicted` / `float_contradicted_reason` (judged on
the row's own float and shares outstanding) and `short_above_float` /
`short_above_float_reason` (the row's own float and short interest).

**Max-float gates read it** (#532 point 2, operator decision 2026-09-24: ship
it now). The fact that holds is float <= shares outstanding, so a contradicted
float passes a max-float gate only when `shares_outstanding` is at or under the
gate's limit; when shares outstanding is over the limit or unknown the float is
**unknown, and never a pass** -- not even where an unknown float passes. One
pure rule, `strategy/float_gate.float_for_gate(float, limit, contradicted,
shares_outstanding) -> (passes, reason)`, for every gate; a float whose check is
`false` or `null` (unchecked) is judged exactly as before. HOD Momo's
`max_float` (the "Low Float" strategies) refuses it `float:contradicted(shares_out=
<count>><limit> | unknown)` and queues no second Yahoo read; `TickerSnap` carries
`float_contradicted` / `shares_outstanding`, set with the float they describe
(the fundamentals enrichment loop and the after-hours runner; a float given
without its check -- a HOD replay's archived float -- is unchecked). The setup
grade's float pillar is `null` (unknown, never failed) and a template's stock
filter keeps the setup out even with `unknown_passes` (replayed eyes read the
check from the recorded leaderboard row). The Five Pillars float
pillar fails with the reason as its `detail`, and the Contenders float score is
0 (a rescued float scores on shares outstanding, the most it can be).
`LEADERS_RULES` refuses it `float_contradicted`. HOD Momo `min_float` and the
scanner's Float chip (a view filter that keeps what it cannot judge) still
compare the float as shown. On the 2026-09-23 audit at a 10M line: SECZ (8.45M
float, 163.27M out), RNAZ (2.15M, 16.93M), WNW (156K, 26.33M) and LGCL are
refused; WHLR (54K, 568K), HAO and HKIT pass.

The desk shows a contradicted float as "54.0K?" with the
reason on hover, and short interest with its settlement date ("566.0K (Aug
31)"; the scanner's second line "8/31 · 6.9") and Yahoo's ratio named on hover
and in the quote panel's "Short Ratio (Yahoo)".

**A filed share issuance is a warning, never a gate** (operator decision on #700, 2026-10-02: "warn, don't
block"). Yahoo's float and share count lag an issuance by weeks: after AMOD's 8-K of 2026-10-01 issued
51,621,560 shares for 3,170 bitcoin, Yahoo still read 4,966,818 outstanding and a 630,935 float. Owner
`catalysts/issuance.py` (in memory; re-read off the loop every `CATALYST_ISSUANCE_REFRESH_SEC` from the live
catalyst feed's store, one filtered query; a store not on disk leaves it empty): per symbol, the newest SEC 8-K
of the last `CATALYST_ISSUANCE_LOOKBACK_DAYS` (30) with Item 3.02, or with Item 2.01 that the catalyst rules
label a raise (`classify.shares_issued`). Every scanner row (`mover_enrich_view.decorate_rows`) and the ticker
detail's `fundamentals` (REST and the socket's `detail_update`) add `shares_issued: {published_ts, source, form,
items, title, url} | null` and `shares_issued_reason: string | null` ("Shares were issued per the SEC 8-K of Oct
1 11:30 ET (Items 2.01, 8.01): Yahoo's float and share count predate it. A warning only: no gate reads it"). The
desk reads the float as "630.9K?" with that reason first on hover (scanner Float, Fundamentals panel, Trader side
column), the stock read's Float row reads "630.9K?" (`warn`) and its rotation "81.9x today?", and `/api/why`'s
float checks read unknown (below). The figure is still Yahoo's: `float_contradicted`, the HOD Momo floats, the
setup grade, `LEADERS_RULES` and every max-float gate are unchanged, and nothing parses a share count out of a
filing (PIPE shares may not trade until a resale registration, so the tradable float is not known either way).

### Scanner leaderboard: recorded, reconstructed, played back (ADR 023, operator decision 2026-09-22)

Owner `backend/leaderboard/`; store `leaderboard.sqlite3` (`PRAGMA
user_version=3`, unknown versions refuse; a version-1 or -2 store is migrated
in place by creating the two catalyst tables below and adding the `rows`
columns `float_contradicted` / `shares_outstanding` (#532) -- nothing existing
is rewritten, and a row stored before reads both as `null`) under `NOVA_LEADERBOARD_DIR`, else
`F:\Nova\leaderboard` when F: is mounted, else `<cache_dir>/leaderboard` --
beside, never inside, the capture root or the historical downloads. One
**leaderboard row** per symbol per minute per board:

`{symbol, minute_ts, board, source, rank, price, prev_close, change_pct,
volume, rvol, rvol_basis, float_shares, float_contradicted, shares_outstanding,
has_news, news_first_seen_ts, halted, gap_pct, exchange, market_cap, catalyst}`
-- `minute_ts` is a whole-minute epoch second
and the row is the board **as it stood at `minute_ts`** (a reconstructed row
uses only minute bars that closed by then; a recorded row is the desk's board
snapshotted within `LEADERBOARD_RECORD_SETTLE_SEC` after it). `source` is
`recorded | reconstructed`; `board` is `gappers | gainers | losers |
afterhours | large_cap` (recorded: the desk's lists through
`scanner_surface.surface_rows`, so blocklisted names never appear); a
reconstructed day writes `market` (the whole market, shown as Gainers),
`losers` and `gappers` ("A rebuilt day's lists" below). `change_pct` is a fraction against the
prior close, computed from `price` and `prev_close` and `null` when either is
unknown (a `close_fallback` row has no print: `price` / `change_pct` null).
`rvol_basis` is `daily_avg` (the desk's RVOL: volume over the average daily
volume) or `time_of_day_20` (volume so far over the same-minute average of the
prior 20 sessions); two bases are never compared. `float_shares` is as known
that day or `null`; `float_contradicted` (`boolean | null`) and
`shares_outstanding` are a recorded row's float check as the desk row carried
it that minute (#532, "Float credibility and short-interest dates"; a row
recorded on 2026-09-24 before the short-interest warning was split out may
carry `true` for short interest above the float alone),
`float_contradicted` `null` without a float; a reconstructed row carries
neither. `has_news` / `news_first_seen_ts` only from news seen by
that minute. Every unknown is `null`, never a placeholder. `halted` is derived
at read time from the halt log: `true` while a logged halt is open, `false`
only for a recorded minute whose halt feed was answering, else `null` (a live
row states it by the same rule from the live sources: "Live rows state their
halt" above).
`catalyst` is derived at read time too ("Catalysts in playback" below).

**Catalysts in playback** (#498). The research backfill's store is never read
by the backend (ADR 024), so `research/catalysts/export_leaderboard.py` copies
what playback needs into this store, per symbol-day it holds (its `targets`):
`catalyst_checks (session_date, symbol, window_start, window_end,
sources_answered, rules_version, exported_ts)` -- the window (the prior
session's 16:00 ET close to 20:00 ET) and the sources whose check was `ok`,
comma-joined, `''` when none looked -- and `catalyst_items (session_date,
symbol, item_id, published_ts, source, publisher, title, url, kind, category,
strength, dilution, rules_version)`, every item naming the symbol in that
window labelled by `catalysts/classify.py` at the export's rules version
(labels, not article text; Finnhub's Benzinga copies left out, #516). The
export replaces each symbol-day whole, one session day per transaction; it is
the tables' only writer. A board read gives each row `catalyst: verdict | null`
in the live desk's wire shape (`catalysts/live.WIRE_KEYS`), computed by
`leaderboard/catalyst_verdicts.py` with `classify.verdict_from_labels` -- the
live verdict's own ranking -- from the items published after the window opened
and at or before `at` (never after; the window's end when `at` is later), so
`rules_version` is the export's. `null` when the symbol-day was not exported,
or when no source looked and nothing was published by `at` -- unknown, never
"no news"; a checked symbol with nothing published yet is `none_found`.
`news_pending` / `halt_code` come from this store's `halt_events` (a Nasdaq T1
/ T12 halt that started inside the window with no resumption logged by `at`).
On the desk, after a merge that changes the rules or a new fetch, the operator
runs `py -3 research/catalysts/export_leaderboard.py` (research store
`F:\Nova\catalysts\catalysts.sqlite3`, leaderboard store
`F:\Nova\leaderboard\leaderboard.sqlite3`; `--db` / `--since YYYY-MM-DD`).

**Gap policy.** The recorder runs whenever the backend runs -- no button --
and writes, each minute 04:00-20:00 ET on exchange days, one `minutes` row
(`run_id`, `feed_live`, `halt_feed_ok`) and one `coverage` row per board
(`state: live | frozen | unavailable | feed_down`, `row_count`); a
reconstructed day writes `coverage` per board with `state: rebuilt` (`frozen`
for its Gappers from 09:30). A minute without a
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
`change_pct` (ties: volume, symbol; worst first under `worst_first`). Playback's `leaders`, the S5 offline
universe, the rebuild and live auto-record call the same function; presets are
`BOARD_RULES`, `LEADERS_RULES` ($3-10, float <= 10M or unknown, volume >=
100k, top 3), `S5_RULES` (top 3 with `time_of_day_20` RVOL >= 5),
`LOSERS_RULES` (a known change under 0, worst first) and `GAPPERS_RULES` (the
live premarket Gappers floor, `ibkr/gapper_view.row_qualifies`: price >=
`SCANNER_MIN_PRICE`, `change_pct * 100 >= GAPPER_MIN_GAP_PCT`). Under
`LEADERS_RULES` a contradicted float (#532) qualifies only on shares
outstanding <= 10M and is otherwise refused `float_contradicted` -- an unknown
float is admitted, a contradicted one is not, because its own counts say it is
likely larger than shown; a row without the check (reconstructed, or recorded
before schema 3) is judged as before. Playback and auto-record read the same
stored check, so they still agree on who led. A
recorded row's `rank` is the desk's own order of that list (Losers stay
worst-first); a reconstructed row's `rank` is its board's: `BOARD_RULES` on
`market`, `LOSERS_RULES` on `losers`, `GAPPERS_RULES` on `gappers` (from 09:30
the 09:30 order).

**A rebuilt day's lists** (ADR 023 amendment 2026-10-06; operator report:
"Don't we already have the data for this day ... Why do we not see gainers,
losers, and gappers for that hour?"). A rebuilt day kept only `market`, the top
100 risers each minute, shown as Gainers: 2026-09-09 held no row under 0% at
07:00, 09:45 or 16:30, so it had no Losers, and nothing projected its Gappers.
`research/leaderboard` writes three boards per minute from the same rows (every
universe symbol with a closed bar by the minute):
- `market`: the top `--top` by `BOARD_RULES`, plus every `LEADERS_RULES` /
  `S5_RULES` pick (unchanged);
- `losers`: the bottom `--top` by `LOSERS_RULES`, ranked 1 = worst;
- `gappers`: before 09:30 the top `--top` by `GAPPERS_RULES`, `gap_pct` the
  move (the live list's own number before there is an open); from the 09:30
  minute, built from premarket bars only, its membership and order are frozen
  as the live list freezes, and each later minute reprices those symbols
  (`state: frozen`).

Each board writes a coverage row every minute, so an empty list reads as empty,
never as not rebuilt. A day counts complete for `--skip-complete` only when all
three boards cover its 960 minutes. On the desk a rebuilt day fills Gainers,
Losers and Gappers; Losers and Gappers on a day rebuilt before say so. After
Hours and Large Cap are not rebuilt, and each says why: the live After Hours
list is IBKR's after-hours gainers, ranked on the move since the regular close,
which the rebuild does not measure; Large Cap needs a market cap as of the day,
which the files do not carry.

**Splits a rebuild confirms from SEC filings** (#772). A rebuilt day adjusts its
prior close and RVOL lookback for the splits in Massive's split list, so a split
missing there reads as a fake mover: PHGE's 1-for-10 reverse split on 2026-09-09
read +925%. `research/leaderboard/confirm_splits.py` adds the splits SEC filings
prove, and only those:
- **Suspects.** For each pair of sessions in a span, a common / ADR ticker whose
  open is at least 1.8x, or at most 0.7x, the prior close, with no split listed
  between them.
- **Filings.** The ticker's 8-K / 8-K/A with Item 5.03 or 3.03, or 6-K / 6-K/A,
  filed from 60 days before to 3 days after the session. The list comes from the
  bulk `submissions.zip` on F: (the live submissions JSON past the file's date);
  the documents (primary, then EX-99) are fetched from SEC and cached by accession.
- **What confirms.** A sentence about a reverse / forward split or a share
  consolidation states a ratio outside any range ("one-for-ten reverse stock
  split"); several ratios in a filing (a past split mentioned) leave the one the
  price agrees with. The split-adjusted open must be 0.5-2x the prior close, and
  a date the filing names beside "effective" / "split-adjusted" / "begin
  trading" must fall after the prior session and by the session. With no such
  date the band is 0.67-1.5x; a filing that names only other dates is refused.
  A suspect whose ticker has a split listed within 10 sessions is reported,
  never added: it would adjust twice.

Confirmed splits live in `F:\Nova\leaderboard\splits_confirmed.json` (beside the
store, `NOVA_LEADERBOARD_DIR`): `{schema_version: 1, updated_at, spans: [{start,
end, checked_at, suspects, with_filings, confirmed, refused}], splits: [{ticker,
execution_date, split_from, split_to, cik, form, items, accession, filed, url,
ratio_text, date_match: boolean | null, prev_session, prev_close, open,
price_ratio, adjusted_ratio, volume_ratio}], refused: [{ticker, execution_date,
accession, reason}]}` -- `split_from` / `split_to` in Massive's convention (a
1-for-10 reverse split is 10 / 1), `date_match` null when the filing names no
effective date. A run replaces its span's entries and keeps every other; an
unknown version refuses. `lb_io.load_splits` adds them to Massive's list
(Massive's entry wins on the same ticker and day), and `spot_check.py` reads
them too. The tool prints the rebuilt days a new split touches -- its day, and
the next 20 sessions the ticker traded (the RVOL lookback) -- for
`build_leaderboard.py --dates`.

**Routes.** `GET /api/leaderboard/days` -> `{schema_version, store: {path,
ok, error}, days: [{date, recorded: {minutes, first_ts, last_ts, boards} |
null, reconstructed: {minutes, first_ts, last_ts} | null}]}` newest first.
`GET /api/leaderboard/{date}?at=<epoch>&source=` -> `{schema_version, date,
at, source, minute_ts, covered, gap, boards: {BOARD: {state, rows[]}},
leaders: {board, symbols[], rules}, catalyst_symbols}` -- the board at the latest minute at or
before `at` (never after); `source` defaults to `recorded` when that day has
one, else `reconstructed`; `catalyst_symbols` counts the day's
`catalyst_checks` rows (`0`: no catalysts on file for the day, and the
Scanner's Catalysts tab says so in Sim). `GET /api/leaderboard/{date}/coverage?source=` ->
`{date, source, session_open, session_close, spans: [[start, end], ...],
gaps: [{start, end, reason}]}` (whole epoch seconds). `GET
/api/leaderboard/{date}/halts?until=<epoch>` -> `{date, events[]}`. `GET
/api/hod-momo/history/{date}` accepts `?until=<epoch>` (alerts raised at or
before it, by `created_ts`, else `timestamp`; the reply stays a bare list). `GET /api/history/dates?type=all` lists every date with any saved
board; `type=movers` reads the `gainers-` / `losers-` files. `/api/ibkr/status`
adds `leaderboard_recorder: {recording, ok, error, since, run_id}`.

**Auto-record.** The backend records, first, the setups of the templates in
play that are in a scored trade (`trade`), near their trigger (`near`) or armed
(`armed`) -- whenever any setup's template in play is inside its arming window
(07:00-11:30 ET by default; red to green 09:30-10:30; the 5-minute flat top 07:00-15:30; ADR 042: until then a
setup arming after 10:00 had no line, and red to green's triggers were never
"go") -- then, 07:00-10:00 ET only, the top
`LEADERBOARD_AUTO_RECORD_TOP_N` `LEADERS_RULES` names of the live Gainers
board (ADR 041: the tape at a setup's trigger and through its trade is what the
signal trials read). At 10:00 only the leaders' lines stop. A setup takes a
leader's line once that line has run
`LEADERBOARD_AUTO_RECORD_SETUP_MIN_KEEP_SEC`, never another setup's; a trade
keeps its line past its window until its scoring window ends. It records
through the Session Record path, using only **free** Level 2 lines
(`IBKR_MAX_DEPTH_SYMBOLS` total), and yields its lowest-ranked line the
moment the operator opens Level 2 on another symbol -- the operator never
loses Level 2 (operator decision 2026-09-22). It never starts, stops or
adopts a symbol the operator recorded by hand; its stops are planned
(`reason: "auto"`, excluded from `missing_sec` like `operator`), never a loud
unrequested stop; the operator pressing Record also takes a line back, and a
symbol the operator stopped is not retaken that day. A line it gives back to the
operator -- for Level 2, a Record, or a Time & Sales IBKR refused for its
tick-by-tick cap (#698) -- is cancelled at once, never after the tape's 16 s
remount linger, and stays theirs `LEADERBOARD_AUTO_RECORD_YIELD_HOLD_SEC` (30 s)
while their subscribe lands (on 2026-10-02 the next tick took TNON's line back
before AIXI's Level 2 had it). It never takes a slot a restart's resume is
bringing back (`keepalive.pending_symbols()`). **What it holds survives a
restart** (#698; owner `leaderboard/auto_record_state.py`): `auto-record.json`
in the operator cache, `{schema_version: 1, date: "YYYY-MM-DD" (Eastern), held:
{SYMBOL: {since: number | null, why: "trade" | "near" | "armed" | "leader" |
null}}, declined: string[], operator: string[]}` (`operator`: the recordings the
operator started or took over today; a file without it names none), rewritten on
every start, stop, operator take and operator stop; another day, an unknown version
or an unreadable file reads as empty (logged). After a restart a recording it names
that the keepalive resumed is auto-record's again (so it can rotate it or give it
back), and a symbol the operator stopped stays declined that day. **The stock you
look at always outranks a recording you did not start** (operator, 2026-10-02:
"when I view a stock or a ticker, the recorder will empty a space for me"): a
recording a restart brought back (`keepalive.restart_symbols()`) that the file does
not name as the operator's is auto-record's too, so it gives way to the operator's
Level 2 and stops at its window's close. At 10:36 that day the backend came up on
the first build with the file, the process before it never wrote one, and SDEV,
SSM and CELU -- all auto-record's -- read as the operator's: AZTA's Level 2 read
"Symbol cap reached" for over an hour. When every line is still in use, the
ladder's refusal names who holds each (`line_lending.view.cap_words`: recording,
another Level 2, lent, replay) and how to free one, and it asks again every 1, 2,
4, then 5 s -- it had asked every second. `NOVA_AUTO_RECORD=0`
turns it off. `/api/ibkr/status` adds `auto_record: {active, window,
windows: {open: "setups_and_leaders" | "setups" | "leaders" | "none", setups: {open,
start, end, by_setup: [{setup, start, end, open}], error}, leaders: {open, start,
end}}, symbols[], why: {SYMBOL: "trade" | "near" | "armed" | "leader" | "left"},
setups: [{symbol, why}], setups_error: string | null, leaders[], yielded[],
last_error}` (`setups_error`: the setup scanner could not be read -- stated,
never read as "no setups"); the operator taking a line back gives up the
lowest-ranked first (`left`, then `leader`, `armed`, `near`, `trade`); `/api/diagnostics` adds the
`leaderboard_recorder` and `auto_record` rows (group `recorder`).

**Retention: keep everything, guard the drive** (operator decision on #485,
2026-09-24). Nothing deletes leaderboard rows automatically -- recorded days
cannot be replaced, a rebuild takes about a minute a day, and SQLite gives no
space back without a `VACUUM` of the whole file. The store grows about 6-9 GB
a year. The `leaderboard_recorder` row's `evidence` adds `store_bytes`
(`leaderboard.sqlite3` plus its `-wal`; `0` before the store exists),
`free_bytes` (free space on the store folder's volume, `shutil.disk_usage`)
and `disk_error` (`string | null`), read on the checklist's worker thread. The
row is `warn` under `LEADERBOARD_FREE_WARN_BYTES` (50 GB) free and `fail`
under `LEADERBOARD_FREE_FAIL_BYTES` (10 GB), with the room left and the fix
(free space, or move `NOVA_LEADERBOARD_DIR`); a size or free space that cannot
be read is `unknown` with the reason, never `ok`. The drive's verdict only
ever makes the row worse: a write failure stays `fail`, and with room to spare
the row reads as before.

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
active set), `universe_symbols: string[]` (those symbols, sorted -- added
2026-09-24 for the watch list; a Sim eyes board lists its replay's symbol),
`seeding` (symbols still loading today's bars, IBKR's history included -- below), `scoreboard:
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
pillars: {price, change_pct, rvol, float, float_contradicted,
shares_outstanding, float_note, news, headline, catalyst} | null, tape:
{verdict: "go" | "wait" | "veto" | "blind", reasons: string[], line, metrics}
| null, proposal | null, outcome: "target_first" | "stop_first" | "open" |
null, bar_r, mfe, mae}`. An unknown pillar is `null`, never a failed one, and
no frame carries a bare `NaN` (`scanner_wire`). `float_contradicted` /
`shares_outstanding` are HOD Momo's float check (#532): a contradicted float's
pillar passes only on shares outstanding at or under the pillar's limit and is
otherwise `null`, and `float_note` (`string | null`, set at arm time with the
template's limit) says which; a template's stock filter reads the float by the
same rule and keeps out a contradicted float it cannot rescue, even with
`unknown_passes`. A proposal is `{id, setup_id,
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

**A symbol followed mid-session is seeded from 04:00** (2026-10-02: AMOD, followed at 07:51:22
after trading since 04:00, wrote its first first-pullback line at 08:23, 32 bars later). Owner
`setup_scanner/seeder.py`. The bar store holds a symbol's minutes only once a chart fetched them or its
Level 1 line built them, so a name admitted mid-morning had nothing before its line opened. When the
stored minutes start more than `SETUPS_SEED_LATE_START_SEC` (10 min) after 04:00, or there are none, the
symbol stays `seeding` while IBKR's 1-minute history of today is asked for (`hooks.live_history`: the
charts' paced `historical_service.request_bars`, background priority, on the IB loop; nothing is asked
when IBKR filled today's minutes and the stored ones start by then). Requests are asked one symbol at a time, oldest
first; at most one every `SETUPS_SEED_HISTORY_SPACING_SEC`; never while a chart's history loads; only
while fewer than `SETUPS_SEED_HISTORY_BUDGET` (30) of IBKR's 60 per 10 minutes went out. Then the
symbol is seeded from the store again. The Level 1 line's minutes since the follow keep their place,
so no minute counts twice. The minute now forming is never seeded. A name that leaves the followed set
keeps its place in the queue. History that does not come (two unanswered asks, or 10 minutes) is given
up, and the symbol is seeded with what the store has, as before. A hole later in the day is seeded as it
is: waiting would hold a name whose lanes are warm out of the open. The wire is unchanged.

**The tape at a trigger is the tape Nova saw** (operator report 2026-09-30:
"why didn't we trade it?" -- LGHL's first pullback triggered at 07:16:10 and
read WAIT, "burst of red", while 7.9k shares lifted the offer through the
trigger). A lane reads the tape for a setup coming `near` and for a trigger at
the moment it handles that price -- its host's clock, never before the price's
own stamp (`Lane.read_at`) -- and a read takes every print received before it
(`TapeFeed.prints` drains the print queue first). The L1 last carries IBKR's
whole-second trade time while prints carry their arrival (#563), so a read
that ended at the stamp left out the prints that crossed the trigger: on the
Session Record, LGHL reads WAIT at 07:16:10.000 (1,454 shares at the bid, none
at the ask) and GO at 07:16:10.856, when the trigger arrived (124 prints,
7,882 shares at the ask). A replay already read at the end of the price's
second. Every tape read's `metrics` adds `read_at` (epoch seconds its window
ends at): a `setups.db` row without it read the earlier window, and nothing
stored is rewritten. `triggered_at`, the scoring and a trigger's age keep the
price's own stamp; that stamp's lag is #667.

**Every setup's scanner (ADR 031, operator decisions 2026-09-24).** The bull
flag, the flat-top breakout and red to green get detectors beside the first
pullback's (`setup_scanner/bull_flag.py`, `flat_top.py`, `red_to_green.py`;
rules pre-registered in ADR 031), on the same ladder of states, the same tape
gate and the same scoring; since 2026-10-02 Gap and Go too (`gap_and_go.py`, the
research's A2 rule, ADR 031 amendment: the pre-market high, armed at the 09:30
open when the open is under it, broken by 10:00, stop `min(20c, 4%)` under the
entry, one try a day; a new setup starts Off on every venue); since 2026-10-06 the 5-minute flat top
(`flat_top_5m.py`, "The 5-minute flat top" below). The board is `schema_version: 2`: every row and
proposal adds `setup_type: "first_pullback" | "bull_flag" | "flat_top_breakout"
| "flat_top_5m" | "red_to_green" | "gap_and_go"`; a row adds `failed_at: number | null` and its `setup` adds
`detail: object | null` (the setup's own facts: `entry_mode`, `broke_at` and the touches for
the flat-top breakout ("The flat top counts its touches" below), `open` and `red_bars` for red to green, `pole_bars` for the
bull flag, `pm_high`, `pm_high_t`, `open`, `open_t` and `stop_rule` for Gap and Go);
`kind` is one of `first_pullback | second_pullback | bull_flag |
second_bull_flag | flat_top_breakout | second_flat_top_breakout | flat_top_5m |
second_flat_top_5m | red_to_green | gap_and_go`
(the kind without `second_` is the first of that setup on that symbol that day);
`leg` is the setup's context (`{t, high, low, pct, bars?}`: the leg, the pole, the
impulse into the high of day, the open and the red phase, or Gap and Go's
pre-market high with `low` its stop); rows are capped
per setup (`SETUPS_BOARD_MAX_ROWS` each). The top-level `template` /
`templates_watched` move into `setups[]`, one entry per setup with a scanner:
`{id, level: 0 | 1 | 2, chosen: boolean, proposing: boolean, template: {id, rev,
name, params_hash} | null, templates_watched, window: {start, end, state:
"before" | "open" | "after"}, counts: {watching, forming, armed, near,
triggered, failed, filtered, proposed}}` -- `forming` counts the symbols now in
`leg` or `pullback`, the rest count today's rows (`proposed`: rows that raised a
proposal). The top-level `proposing` is true when any setup proposes. A setup
proposes only at effective Eyes or above (ADR 042: the lower of the master
`level` and its own `setup_levels[setup]`; the board's `setups[].level` is the
effective level and `chosen` is always false, kept one release); at Off it
watches and scores, silently. A proposal the bot or Auto-entry will take carries
`taken_by: "bot" | "auto_entry"`, one that is not a trade `not_a_trade:
{reasons}` (and `grade`, `pillars`, `spread`); both are still raised, and the
desk locks their Stage with the reason. `setups.db` is schema 3: rows add `setup_type` and `detail`
(JSON); a schema-2 file migrates in place, its rows the first pullback's (schema
1 migrates through 2); row ids keep their form for the first pullback and add
`@<setup_type>` for the others, before any `~TEMPLATE_ID` (a later setup on a key
whose row holds a trade adds `#N` to the key: "One row per trigger" below). `GET
/api/setups/scoreboard` and `GET /api/setups/rows` take `setup=` (default
`first_pullback`) and answer for that setup's template in play; both add
`setup_type` to their answer. `GET /api/setups/rows?setup=all` answers every
setup's template in play at once, oldest armed first (the Bots page timeline;
with `template=all`, every template's rows).

**The grade you can see (operator report, 2026-09-29).** "So why does it think
this is a good trade when it's obviously not?" -- AVAT's first pullback
triggered at 08:06 on one pillar of five (grade C), and the Trader's plan still
read TRIGGERED twenty minutes after its stop printed. The % change pillar was
unknown on 17 of 43 first-pullback arms and 20 of 42 flat-top arms since 09-23:
HOD Momo's snapshot carries a change only when its IBKR snapshot returned a
prior close. `setup_scanner.grade.read_pillars` now measures it from the
scanner board row's `prev_close`, else the L1 line's tick-9 prior close, when
the snapshot has none (`null` when neither knows). Board rows and `GET
/api/setups/symbol/{symbol}` lanes add:
- `graded: "armed" | "forming" | null` -- where `grade` / `pillars` come from:
  the setup's arm-time read (`armed`), or, while the pattern is forming (`leg`
  / `pullback`) with no setup armed, the read taken when its current leg made
  its high (`forming`: the lane reads the pillars on each `leg` event and the
  `leg` journal line carries them as `grade` / `pillars`).
- `phase: "armed" | "near" | "triggered" | null` -- under a `filtered` row,
  where the pattern itself stands (`null` on every other row). A `filtered` row
  stays on the board while its pattern is armed or near, and for 30 minutes
  after it triggered (the triggered rows' window), no longer five minutes from
  its arming; its `distance` is set while armed or near. It still reads no tape,
  never proposes, is never scored and never reaches the bot. Its re-arm is
  journalled (`rearmed`, the new levels), and a `state` line that says
  `triggered` carries `triggered_at`, so a playback draws the same row.
- `trigger_tape: {verdict, reasons} | null` -- the tape gate's read at the
  trigger (`null` before one, and on a filtered setup).
- `outcome_at: number | null` -- when the scoring's first touch (target 1 or
  the stop) printed; `scored` journal lines carry it.

### The flat top counts its touches (ADR 031 amendment, operator ask 2026-10-06)

"Make it something special like this ... when it starts forming. I doubt real life is going to be perfect as this, so
we may need a drift or a ratio to still consider flat top." Owners `setup_scanner/flat_top_shape.py` (the shape, pure),
`setup_scanner/flat_top.py` (the states); on the desk `frontend/src/stock_read/flatTopShapes.ts`.

- **The rule.** The level is the high of day.
  - A **touch** is a candle whose high is within the tolerance under it: `ft_touch_pct` of the level (0.5%) or
    `ft_touch_dollars` ($0.01), whichever is more. A candle a little over the earlier touches, inside the tolerance,
    is a touch too: the level drifts up to it and keeps its row.
  - The base runs from the **first touch**, the earliest candle in the zone after an impulse into it. Every later
    close stays within `ft_band` under the level and every low on the EMA.
  - At least one touch after the first makes no new high (a retest): highs rising a cent at a time are a move.
  - It is drawn forming from its second touch (state `leg`, `forming.waiting: "N more touch(es)"`, `forming.bars` the
    touches). It arms at `ft_min_touches` (3) on a base of `ft_min_consol`-`ft_max_consol` (2-20) candles. A flat top
    that began longer ago is stale.
  - The hold entry reads the zone as the level: a candle whose low stays in it and that closes green over the high
    holds. Only a close under the zone fails it.
- **The research's P2 is a setting.** `ft_base_start: "last_high"`, one touch, no tolerance and a 6-candle base
  (`flat_top_shape.P2_RULE`) run it exactly. A stored template without the new parameters reads `catalogue.LEGACY`
  (P2's values), never the new defaults. The catalogue's tables moved to `setup_templates/params.py`; `catalogue.py`
  keeps the validator.
- **Revisions.** The built-in default's revision is per setup (`SETUP_TEMPLATE_DEFAULT_REVS`, `setup_default_rev`): the
  flat top's is 2 and its read-out starts over. The 5-minute flat top became a strategy of its own the same day
  ("The 5-minute flat top" below).
- **On the wire.** A flat top's `leg` adds `touches: [[t, high], ...]` (oldest first) and `zone` (the lowest high that
  touches), and `bars` counts the base. Its armed `detail` adds `touches`, `zone`, `min_touches` and `broke_bar_t`
  (the break's candle, hold entry). A triggered hold adds `hold_bar_t` and `hold_high`. A row, journal line or
  episode written before has none of them.
- **On the desk.** The drawing follows the operator's sketch:
  - a violet level from the first touch to the right edge, dashed while it forms;
  - a ring on each touch, the last ring counting them ("4 touches", "2 of 3 touches");
  - the base boxed;
  - a green triangle over the candle that broke it, and a green box around the candle that held it;
  - its name in the edge column ("FLAT TOP = HOD 5.50" until it breaks).

  A flat top that is not the plan's lead is a dimmed violet without labels, and a failed one is grey. A past flat top
  keeps its rings, faint. The 5-minute flat top draws the same way on the 5-minute chart, and its trigger line reads
  "5m FLAT TOP". Every pane's Key adds the flat top's marks.
- **Unchanged.** The 1-minute flat top plays as before. No flat-bottom short: Nova opens no shorts (Invariant 7).

### The 5-minute flat top (ADR 031 amendment, operator ask 2026-10-06)

"Make the 5-minute flat top a Paper buy with a 1-minute hold entry, as the material trades it." The material reads
the flat top on the 5-minute chart and buys the 1-minute pullback that holds it after the break. Owner
`setup_scanner/flat_top_5m.py`; on the desk `frontend/src/stock_read/flatTopShapes.ts` and `fiveMinuteShapes.ts`.

- **A sixth strategy**, `flat_top_5m`: its own Off / Eyes / On per venue (starting Off), templates, read-out (kind
  `flat_top_5m` / `second_flat_top_5m`), bot rules and window, like every setup. Nova's bot buys it at On, on Paper
  and Sim only.
- **A 1-minute lane, a 5-minute pattern.** Its lane is fed the scanner's minutes, so the tape gate, the liquidity
  check, the scoring and the bot are the minutes'. Its detector makes 5-minute candles of them
  (`five_minute.candles`; one is over once its last minute or a later one is in) and reads the flat top on those by
  the flat top's own rules ("The flat top counts its touches" above): `bar_sec` 300, arming 07:00-15:30.
- **The entry is the 1-minute hold.** After a price over the flat top, it is the first of the next `ft_hold_bars` (5)
  minutes after the break's own that holds the touch zone and closes green over the high. Entry is one cent over its
  close, the stop is the pullback's low (`ft_hold_stop`: `pullback`, or `candle` for the hold minute's low), and the
  dollar caps read that risk. A minute closing under the zone fails it. It is scored on 1-minute candles from the
  hold minute. Its rows carry no 5-minute read (`tf5_*` null): its pattern is that chart, and trial T8 reads
  1-minute setups.
- **The built-in 5-minute flat-top lane is gone** ("The 5-minute setups" below keeps the first pullback and the bull
  flag), and auto-record's setups window now runs to 15:30 ("Auto-record" above).
- **On the wire.** It comes in the stock read's and the symbol view's `setups` with `timeframe: "5m"` and `rules`
  adding `hold_bar_sec`. Its `detail.broke_bar_t` and `hold_bar_t` are minutes. The past setups at `?tf=5m` fold its
  lines; `?tf=1m` leaves them out.
- **On the desk.** The 5-minute chart draws it as the flat top, its hold named "1m hold" in its 5-minute candle.
  Once it arms, the 1-minute chart draws its level from the first touch, the break and the hold minute. At Off it
  draws nothing, like every strategy.

### One row per trigger (ADR 022 amendment, 2026-10-02)

AMOD's first pullback triggered at 08:48:04 and was stopped at 08:48:13. At 08:49 a candle tied the
leg's high, and the detector armed the same leg again as the second pullback. The lane named rows by
the leg, so it wrote the new levels and `kind: second_pullback` over the trade's row
(`AMOD-2026-10-02-1790945160`), and the read-out, which counts the first of the day, lost the trigger.
A row is one setup up to its trigger and the trade after it (owner `setup_scanner/lane_ids.py`):

- **A later setup on a key gets its own row.** An arming on a key (the leg, the pole, the base, the
  open) whose row holds a trigger opens `SYMBOL-DATE-KEY#N`: N is the attempt on that key (2, 3,
  ...), then `@SETUP` and `~TEMPLATE_ID` as before. The first attempt keeps the id it always had.
  Nothing arms, re-levels or triggers a row that holds a trigger.
- **Readers keep treating the id as opaque.** The board, the symbol view, the scoreboard, the
  read-out, the triggers audit, the Sim playback, the past setups and the bot only match ids, and
  none parses one. A trigger event and its proposal carry the new row's id, so an Approve given to
  the first attempt never sends the second.
- **A restart never writes over a trade.** A lane making a symbol's detector asks `setups.db` which
  of today's rows on that symbol hold a trigger (its template and setup) and leaves those ids alone.
- **A detector made mid-day remembers the day.** That happens after a restart, when a symbol leaves
  the universe and comes back, or when a template is edited. The detector starts from the day's
  triggers on its symbol in that lane, from memory, else from `setups.db`. A later setup then reads
  as the second, the setups-a-day cap holds, and red to green's one try stays spent: GOW
  (2026-09-30) triggered twice on one id after its detector was made again.
- **Rows written before keep their ids and are not repaired by this change.**

### Too thin to trade (ADR 022 amendment, operator decision 2026-10-01)

"There's no way I will ever trade something like that with a 20-cent spread ... the volume is almost
dead": LPA, Gainers #41 at +10%, armed five setups and drew them like trades. It had traded $1.0M all
day by its first trigger and $42K in the five minutes before it, with 100 shares at the inside and the
next offer 18 cents up. Owner `setup_scanner/liquidity.py` (pure; constants `SETUPS_THIN_*`). A stock is
**too thin** at a moment when any check fails:

- **day**: under $2M traded today (from 04:00 ET), measured as the day volume times the volume-weighted
  average price of its minutes;
- **pace**: under $100K traded in the last five closed minutes;
- **book**: with a Level 2 book and a size (the desk venue's risk per trade over the setup's risk a
  share), buying that size walks the asks more than 0.25R past the best ask.

A check Nova cannot make is unknown -- never thin, never a pass. A **reading** is `{state: "ok" | "thin"
| "unknown", reasons: string[], failed: ("day" | "pace" | "book")[], unknown: {day?, pace?, book?: string},
day_dollars, pace_dollars, pace_sec, walk: {qty, best_ask, last, avg, over_ask, shown, short, r} | null,
as_of, limits: {day_dollars, pace_dollars, walk_r}}`; `ok` needs the day and the pace both known.

- **The lanes** (`setup_scanner/lane_liquidity.py`) read the active setup:
  - when it arms, when it first comes near, at each closed minute while it is armed or near, and at its
    trigger, from the lane's one-minute bars, the day volume in its pillars, the host's newest fresh
    book and the desk's risk per trade (`LaneHost.risk_usd`, the venue sleeve's, re-read every
    `SETUPS_THIN_SIZE_TTL_SEC`; a replay has none and never judges the book);
  - the pillars add `volume` (shares today: HOD Momo's snapshot live, the leaderboard row on a replay).
- **On the wire.** Board rows and `GET /api/setups/symbol/{symbol}` lanes add `liquidity: reading |
  null` -- the armed setup's, frozen at its trigger; null before it arms, on a filtered setup, and from
  rows stored before.
- **What it changes.**
  - A thin setup never proposes.
  - Its trigger event adds `liquidity`, and NOT A TRADE (`trade_verdict`) adds "too thin to trade: ..."
    for the bot, Auto-entry, Approve and the plan.
- **The journal.** The `armed`, first `near` and `triggered` lines carry `liquidity`, and a `liquidity`
  line records a changed verdict between them, so the Sim playback folds the same rows.
- **The store.** `setups.db` is schema 5: rows add `liquidity` (JSON, the reading at the trigger once
  it triggered). A schema-4 file migrates in place, and its rows read unknown.
- **The read-out** leaves a setup thin at its trigger out of both pools and adds `thin_left_out:
  integer | null`. The scoreboard summary's `by` adds `liquidity` (`ok` | `thin` | `unknown`).
- **The stock read** (`stock_read/plan_liquidity.py`) reads the stock now, from the read's volume, the
  chart's stored minutes and the Trader's Level 2 walked for the plan's risk. Minutes that end more
  than `SETUPS_THIN_BARS_STALE_SEC` ago leave the pace unknown.
  - The Plan adds `liquidity: reading | null`, and its `checks` start with `liquidity`.
  - The In play group adds the row `liquidity` ("Liquidity": "Too thin" / dollars / "Not known"), and
    its tile reads "Too thin" when thin.
- **On the desk**, a thin setup is greyed, never hidden:
  - the setup cards and the Setups board add a "Too thin" chip with the reasons and the rule on hover;
  - the plan reads TOO THIN;
  - the 1-minute badge reads "SETUP · TOO THIN TO TRADE", with no track and no call to enter, even after
    it played out;
  - the charts draw no plan for it (no zones, no plan-only lines, its lane faded) and Level 2 marks no
    plan level. A level an order stands behind is still drawn.

### The 5-minute chart on a 1-minute setup (trial T8, operator decision 2026-09-30)

"Sometimes the 1-minute setup aligns well with the 5-minute setup ... I want to make sure we are utilizing
all of that"; on the choice: "Show it and test it". Owner `setup_scanner/five_minute.py` (pure). A **5-minute
read** is `{agrees, above_ema9, macd_up, close, ema9, macd_hist, candles, as_of}`: 5-minute candles made on
the clock from 04:00 ET of the scanner's own closed one-minute bars (a candle counts once its five minutes are
over; five minutes without a bar make none), `above_ema9` the last complete candle's close over the 9-period
EMA of the 5-minute closes, `macd_up` the 5-minute MACD (12, 26, 9) histogram over 0, `agrees` both; the EMAs
seed with the first close (`series.ema`), `as_of` the last complete candle's start. `null` before the first
5-minute candle is complete. Every lane reads it at each closed minute:
- Board rows and `GET /api/setups/symbol/{symbol}` lanes add `tf5: read | null` and `tf5_at: "trigger" |
  "armed" | "forming" | null` -- the read at the trigger once the setup triggered, else when it armed, else
  (forming, no setup armed) when its leg made its high. The `leg`, `armed` and `triggered` journal lines carry
  `tf5`, so the Sim playback draws the same row.
- `setups.db` is schema 4: rows add `tf5_armed` and `tf5_trigger` (JSON); a schema-3 file migrates in place,
  its rows read as unknown. The scoreboard summary's `by` adds `tf5_at_trigger` (`agrees` | `against` |
  `unknown`).
- The stock read's plan adds a check `{id: "tf5", state: "info", text: "5m agrees: over its 9 EMA 16.95, MACD
  up (trial T8)"}` -- the 5-minute chart now, from the read's own session minutes by the same rule.
- On the desk the Bots page's setup cards and Watchlist › Setups add a **5m** column: "5m ✓" (green) or
  "5m ✗" (grey, never a warning colour), the hover saying which part failed, when it was read and that it is
  in trial. Nothing places, stages, gates or blocks on it.
- In sample (the harness's 1,050 bar-level trades, `F:\Nova\eyes\studies\mtf-alignment-2026-09-30`) it
  leaned the right way and did not hold: pooled +0.10R (95% CI -0.08 to +0.28), and the agreeing trades still
  lost (-0.27R). Trial T8 (`knowledge/signal-trials-3.json`, "Signal trials" below) decides whether "5m
  against" ever becomes a warning.

### The 5-minute setups (operator decisions 2026-09-30)

"We need 5-minute strategies ... sometimes I see slow stocks moving upwards, and you can see clear patterns in
the 5-minute chart, but they're not clear in the 1-minute chart"; on the IOVA mockup: build it this way, chart
only, a chip and the trigger line on the 1-minute, arming 07:00-15:30. Owner `setup_scanner/five_minute_lane.py`.
- **The lanes.** One built-in lane per setup in `SETUPS_5M_SETUPS` (the first pullback and the bull flag; the flat
  top's became a strategy on 2026-10-06, "The 5-minute flat top" above) runs beside the template lanes: the setup's own detector on 5-minute candles made of the scanner's
  minutes (`five_minute.candles`: on the clock from 04:00 ET, complete once their five minutes are over). The
  detector reads only when a candle completes, and a price inside a forming candle carries that candle's open.
  Its rules are the default template's except:
  - `bar_sec` 300, arming until 15:30 (`SETUPS_5M_ENTRY_CUTOFF_ET`);
  - a risk up to 6% of the entry (`stop_cap_pct`: the 2026-09-29 study's 5-minute rule; every detector's risk
    check reads `detector.stop_cap`);
  - the scoring exit counts 5-minute candles, and the first touch, MFE and MAE are read over 60 minutes
    (`SETUPS_5M_SCORE_WINDOW_MIN`).

  Template id `5m` (rev 1, name "5-minute", `params_hash` over those rules): its scoreboard rows end `~5m`, so
  no read-out, trial (T7, T8) or bot reads them, and a setup's `templates_watched` never counts it.
- **It never plays.** A 5-minute lane raises no proposal, tells the bot nothing, and has no Setups board row
  and no Bots page card. It reads the tape gate and scores like any lane. Its journal lines carry `template:
  "5m"` and `playing: false`, and the Sim playback leaves it out of a setup's counts.
- **The wire.** `GET /api/setups/symbol/{symbol}` adds `setups_5m` (the built-in 5-minute lanes, shaped like
  `setups`, `level` 0, `chosen` false), and every lane adds `timeframe: "1m" | "5m"` (the candles its pattern reads:
  the 5-minute flat top in `setups` is `5m`); `rules` adds `stop_cap_pct`, `bar_sec` and `hold_bar_sec`. The stock
  read adds `setups_5m` (never a plan's lane). `GET /api/stock-read/{symbol}/past-setups?tf=5m` folds the 5-minute
  lanes' lines and the 5-minute flat top's (`EpisodeFold("5m", 300)`: the candle a line is about is a 5-minute one), measures what came after over 60 minutes and adds `timeframe`; a
  `tf` other than `1m` or `5m` is a 400.
- **On the desk** (`frontend/src/stock_read/fiveMinuteShapes.ts`; a live lane's drawing moved to
  `laneShapes.ts`, which with `pastShapes.ts` takes the candle's length):
  - The 5-minute pane draws the 5-minute lanes as the 1-minute pane draws its own. The most advanced is in
    colour; the rest are faded, and their labels make room. The ones that ended stay faint, with how they
    ended and what came next. Every label starts "5m", and the lead's trigger, stop and target are dashed
    lines with axis labels. A hover card is titled "5-minute".
  - The 1-minute pane shows a built-in 5-minute setup armed or near its trigger as a legend chip ("5m bull flag ·
    near 13.80") and one dashed trigger line, nothing else.
  - Each pane's Key lists them.
- **What is known.** The bar-level 5-minute versions lost less than their 1-minute twins over five years, and
  still lost (2026-09-29). On IOVA 2026-09-29 the 1-minute scanners saw 33 setups and triggered one. On
  5-minute candles the same rules triggered four: the first touched its target first, two were stop first, and
  one was still open at 10:10. Nothing trades on them; their rows collect the evidence.

### The tape flow score and the flush exit (ADR 034, operator ask 2026-09-24)

"Can my bots detect if we are seeing flush like this so we can exit a position
or burst of greens where we can enter ... just a small piece of the final
decision." Owner `setup_scanner/tape_flow.py` (pure). A **flow reading** is
`{score: number | null, label: "burst" | "flush" | "neutral" | "quiet" |
"blind", readings: {imbalance, pace, drift, book}, metrics: {window_sec,
ask_shares, bid_shares, ask_prints, bid_prints, between_shares, pace_ratio,
baseline_sec, drift_pct, bid_depth, ask_depth, best_bid, best_ask}}`: each
reading from -1 (sellers) to +1 (buyers) and `null` when Nova cannot take it
(no fresh book, a baseline shorter than the window, one price) -- never 0; the
score is the weighted mean of the known readings (`null` with none); `quiet`
is too little tape at the bid or the ask to say, `blind` no print and no book.
Lit prints only (FINRA / TRF / ADF out), a `between` print counts for no side,
the drift reads only prints that set a price, and the baseline never counts
time before the feed could see the tape. Every number is a template parameter
(the catalogue's `flow` group on every setup with a scanner): `flow_window_sec`,
`flow_baseline_sec`, `flow_min_prints`, `flow_min_shares`, `flow_w_imbalance`,
`flow_w_pace`, `flow_w_drift`, `flow_w_book` (not all zero), `flow_pace_full`,
`flow_drift_full_pct`, `flow_book_levels`, `flow_burst_at`, `flow_flush_at`;
and the two choices below, whose defaults are the pre-registered rules.

**Entry** (`tape_entry: "gate" | "score" | "both"`, `flow_entry_min`): `gate` is
ADR 022's print counts; `score` keeps the vetoes and a seller that is not
thinning and replaces the print counts with the score at or over the minimum
(a quiet or blind flow waits); `both` needs both. Every tape read (a board row's
`tape`, `setups.db` `trigger_tape`) adds `flow` (the reading) and
`metrics.flow_score` / `metrics.entry_mode`; `near_tape` and the trigger event
the bot hears add `flow: {score, label}`.

**Exit** (`flush_exit: "off" | "tighten" | "exit"`, `flush_hold_sec`,
`flush_trail_r`, `flush_min_r` nullable): a `flush` at least `flush_hold_sec`
after the entry -- with `flush_min_r`, only while the trade is up that many R --
moves the stop up to `flush_trail_r` R under the price (never down) or gets out
at the bid (`tape_flow.flush_action`). Every lane reads each triggered setup's
flow every `TAPE_FLOW_EVAL_SEC` through its scoring window
(`setup_scanner/lane_flow.py`; the live engine keeps that symbol's tape); the
scoring exit applies the rule (`bar_exit_reason` adds `flush` / `flush_runner` /
`flush_stop` / `flush_stop_runner`; a backtest row adds `flush_action`,
`flush_at`, `stop_now`), and Nova's bot applies the same rule from its own fill
to its trade (`bot/first_pullback/flush.py`; the trade's `exit_reason` adds
`flush`, a tightened stop is a `bot_trade` `note`) from the scanner's newest
reading (`SetupEngine.flow_reading(setup_id)`, never older than
`TAPE_FLOW_READING_STALE_SEC`). The eyes' journal adds `flow` (a turn into or
out of a burst or a flush after a trigger: `label`, `was`, `score`, `readings`,
`price`, `since_trigger`) and `flush` (`action`, `score`, `price`, `bid`,
`stop`, `exit_px`, `mode`). The scoreboard summary's `by` adds
`flow_at_trigger`; a fill count of three covers `flush_runner` /
`flush_stop_runner`. `/sensors/flow` adds `score` (a flow reading with the
default numbers over the sensor rings; `SENSOR_TAPE_RING` 4,000 prints).

**Measuring it.** `eyes/flow_study.py` (`tools/flow_study.py`, read-only) reads
each recorded second through the score and measures the mid's move 10 s to 5 min
later -- never across a gap -- answering `{schema_version: 1, params, study,
recordings, seconds, seconds_by_label, onsets: {burst | flush: {HORIZON: {n,
mean_bp, median_bp, up_pct, t}}}, onset_spread_bp, onsets_by_context: {burst |
flush: {after_rise | after_fall | flat | unknown: ...}}, separation_bp,
by_label, by_bucket}`. `POST /api/eyes/backtests` adds `variants: [{name?,
base?, values}]` (at most `EYES_BACKTEST_MAX_VARIANTS`): templates made for the
run only (`var-NN`), never stored; a variant's manifest entry adds `variant:
true`, `base`, `overrides`, and every template's summary adds `exits`, `flush`
and `vs_base: {base, paired, avg_r_delta, better, worse, same} | null` -- the
same setups (day, symbol, leg) against the run's first template.
`tools/eyes_backtest.py sweep` builds the variants from a grid.

### Signal trials (ADR 041, operator decision 2026-09-30)

"how can we use all this data to determine if we should buy or sell or hold?" -- a study of every
Level 2, Time & Sales and setup signal on 6 recorded days found no buy edge, and a 30 s flush exit
and two don't-buy states that held in sample only (`F:\Nova\eyes\studies\buy-sell-hold-2026-09-29\`).
A tape or book reading becomes a call (or an automated action on a practice venue) only by passing a
trial registered before its data exists. The registry is `knowledge/signal-trials.json`:
`{schema_version: 1, registry: "signal-trials", adr, registered_at, data_from, frozen: true, note,
reading: {when, multiplicity, peeking, failed}, common: {recordings, prints, random_long: {every_sec,
entry, filters: {ask_min, ask_max, max_spread, quote_max_age_sec}, bracket: {target_cents,
stop_cents, time_stop_min}, fills}, lag_honest_exit, control, costs}, trials: [{id, name, role:
"sell" | "sell_bot_only" | "buy_veto" | "buy_warning", signal, rule, population, primary_metric,
test, sample: object, pass: string[], reported_not_deciding: string[], on_pass, on_fail, in_sample:
{study, evidence}}]}` -- T1 the 30 s flush exit on random longs, T2 sellers own the last 10 s, T3 a
red burst at bot speed, T4 a down-sweep, T5 a planned risk under 5c, T6 the 30 s flush on setup
trades. Only data dated `data_from` (2026-09-30) or later counts; each trial is read once, when its
sample is complete, Holm-adjusted across the trials read that night, and shows n of N until then.
The file is frozen: `backend/tests/test_signal_trials_registry.py` holds its canonical JSON (sorted
keys, no whitespace) to the SHA-256 it was registered with, so a change is a new trial on new days,
never an edit. Trials registered after it go in a new registry version, `knowledge/signal-trials-2.json`
(the same shape plus `version: 2` and `follows`; its own hash in `test_signal_trials_registry_2.py`): T7
Room under 2R to the first level of today's map, as a warning, on setups armed from 2026-10-01 ("The day's
levels" below). Then `knowledge/signal-trials-3.json` (`version: 3`, follows the second; its hash in
`test_signal_trials_registry_3.py`): T8 the 5-minute chart against a 1-minute setup at its trigger, as a
warning, on triggers recorded from 2026-10-01 ("The 5-minute chart on a 1-minute setup" above). No trial lets
Nova buy or sell on Live by itself. Recorded with it (built later):
a planned risk under 5c warns and never blocks until T5 passes; a "Flush exit 30 s" template plays
on Nova's Paper bot (put in play outside the bot's window, out again if T1 fails); Approve may hold
Nova's flush and 15-minute exits on Paper and on Sim at the live edge; the Trader's WAIT and SELL
NOW · FLUSH lines show as calls marked "in trial" (description only on Live) until read.

### The bot's read on one stock (ADR 036, operator ask 2026-09-24, #598)

"Show me the bot's decisions specifically for that stock ... if something is forming, can we start
highlighting it on the chart? ... all the tiny signals"; then "i want it to tell me my entry/exit
.. we typically want to aim for 2:1 ratio, like right on top of lvl2". Read-only everywhere: nothing
here places, stages or cancels an order.

**Every lane for one symbol.** `GET /api/setups/symbol/{symbol}` (owner `setup_scanner/`,
`symbol_view.py`) answers `{schema_version: 1, generated_at, session_date, symbol, followed:
boolean, followed_note: string | null, seeding: boolean, setups: SetupLane[]}` -- `followed` false
(with the note: the scanner follows the HOD Momo names) leaves `setups` empty. A **SetupLane** is
each setup's template in play: `{setup_type, template: {id, rev, name, params_hash}, level, chosen,
window: {start, end, state}, rules: {stop_cap, min_stop, target_r, target_mode, entry_offset,
risk_slippage}, state, reason, kind, nth, setup_id: string | null, leg, setup, forming, last_price,
distance, grade, pillars, tape: {verdict, reasons, line, metrics, flow} | null, proposal, outcome,
bar_r, mfe, mae, failed_at, series}` -- the board row's fields for that symbol whatever its state
(`watching` included), plus `forming` and `series`. `forming` is `{trigger, entry, stop, risk,
target1, bars, blocked: string | null, waiting: string | null}` or `null`: the levels the setup
would arm with, computed at the last bar close by the same rule that arms it -- a first pullback or
bull flag blocked by its risk, MACD or window, a bull flag with fewer flag candles than it needs
(`waiting` says how many more), a flat top's base blocked, red to green before its red closes or
with its risk out of the band. `series` is the lane's own indicators at its last closed bar:
`{bars_as_of, bars, close, ema, macd_line, macd_signal, macd_hist, hod}` (`null` before a bar) --
the values the gates read, on the scanner's own minutes. Nothing here changes what arms: the board,
`setups.db` rows and the journal keep their shapes.

**The read.** `GET /api/stock-read/{symbol}?entry=&stop=` (owner `backend/stock_read/`; cache reads
only, no network wait) answers `{schema_version: 1, symbol, generated_at, session_date, price,
prev_close, change_pct, followed, followed_note, setups: SetupLane[], no_scanner: [{setup_type,
label, reason}], plan: Plan | null, levels: Levels, groups: Group[], counts: {ok, warn, bad,
unknown, info}}`. A **Group** is `{id: "in_play" | "setups" | "front" | "tape" | "short" | "float" |
"halts", label, question, verdict, value, rows: Row[]}` and a **Row** `{id, label, value, detail:
string | null, state, source, as_of: number | null}`, where `state` is `ok` (for a long momentum
trade), `warn`, `bad`, `unknown` (Nova does not know -- the detail says why, never a pass) or `info`
(a fact that is neither). **Levels** `{hod: {price, ts} | null, pmh: number | null, open: number |
null, prev_close, vwap: number | null, round_above: number | null, round_below: number | null}`:
the high of day, the premarket high (today's bars 04:00-09:30 ET only), the 09:30 open (null before
it), the chart's session VWAP (from 04:00 ET, restarted at 16:00 for after hours), and the nearest
round number of the price's scale above and below (the stock's own round numbers, below). `price` (and the read's change) is `/api/why`'s `facts.price`.
A **Plan** is `{source: "setup" | "manual", setup_type, kind, state: "forming" | "armed" | "near" |
"triggered" | "manual", provisional: boolean, trigger, entry, stop, target, risk, reward, rr,
target_rule, entry_rule, stop_rule, grade, reason, tape: {verdict, reasons} | null, flow: {score,
label} | null, window: {start, end, state} | null, checks: [{id, state, text}], marks: [{price,
label, kind: "hod" | "vwap" | "pmh" | "round" | "wall" | "open"}]}`. The setup plan is the most
advanced lane (near, armed, triggered within 30 minutes, then forming; the bot's chosen setup
first on a tie): entry, stop and target are the lane's own (`setup`, else `forming`, then
`provisional`), the target the scanner's target 1 (entry + `target_r` x risk, or the leg high when
higher), `rr` = (target - entry) / risk. With `entry` given the plan is the operator's (`manual`):
the stop is `stop`, else the lowest low of the last `STOCK_READ_MANUAL_STOP_BARS` closed one-minute
bars under the entry; the target entry + `STOCK_READ_TARGET_R` x risk. `checks` name what stands in
the way; `marks` are the obstacles between entry and target (a seller of the tape gate's wait size
or more on Nova's book). Size is the desk's (the Trader's risk per trade, a desk setting).

**Not a trade (operator report, 2026-09-29).** The plan adds `pillars: {passed, known, total} |
null` (the lane's pillar checks: how many pass and how many are known, of five), `trade: {ok:
boolean, reasons: string[]} | null` and `result: {outcome: "target_first" | "stop_first", at, r,
text} | null`. `trade` is `null` for the operator's own plan; a setup plan is **not a trade**
(`ok: false`, each reason a sentence) when its grade is C (three pillars or fewer), the template's
stock filter keeps the name out, a triggered setup's tape at the trigger was not go, the setup
already played out (the scoring's first touch printed: `result`, with `r` the scoring's R), the
spread on Nova's book is at least the risk (`checks` adds `spread`: warn over half the risk, bad
at the risk or more), or the stock is too thin to trade ("Too thin to trade" above). A triggered plan's `tape` is the tape at the trigger (`trigger_tape`), else
the lane's last read; a `filtered` lane whose pattern triggered follows the 30-minute rule of a
triggered one. **It is one rule** (ADR 042, `setup_scanner/trade_verdict.py`, pure): the plan,
Nova's bot, Auto-entry, Approve and proposals all read it, so a plan that reads
NOT A TRADE is never bought by Nova either -- the bot and Auto-entry skip the
trigger with the reasons, and Approve refuses it (`STOCK_MODE_NOT_A_TRADE`). On the desk the plan's header carries the grade with its count in a chip that
never shrinks ("C 1/5"); a plan that is not a trade reads NOT A TRADE with its reasons, on the plan
and on the 1-minute chart's badge, drops its reward : risk from the header, locks Stage in ticket
and Approve with the reasons (`data-why`), and ENTER NOW is never called on it; a setup that played
out reads its result ("STOP FIRST 08:08 · -1.00R") instead of TRIGGERED.
The setup cards and Watchlist › Setups show every grade with its count ("C 1/5"), forming rows
too, and a filtered row greyed with its phase ("Filtered · near").

**Dilution on file** (the `float` group's last row; operator ask 2026-10-01: show the dilution filings on
file -- an S-3 / F-3 shelf, a 424B, an S-1 / F-1, an 8-K Item 3.02 -- on the stock read). Owners
`stock_read/dilution.py` (pure), `stock_read/dilution_reader.py` and `stock_read/dilution_store.py`;
constants `STOCK_READ_DILUTION_*`. Read-only: nothing places, stages or gates on it, and the Float tile's
verdict stays the float's. The row before it, `dilution` ("Dilution today"), reads today's catalyst items;
this one reads what the registrant has on file. It is `{id: "dilution_on_file", label: "Dilution on file",
value, detail, state: "warn" | "ok" | "unknown", source: "sec_edgar", as_of}`:
- **The facts** are SEC EDGAR's, from the registrant's submissions file
  (`data.sec.gov/submissions/CIK##########.json`: the columns `form`, `filingDate`, `items`). The CIK is
  looked up in SEC's `company_tickers.json`, a share class as SEC writes it (`BRK/B` is `BRK-B`). Four
  kinds, each by its filing date against today's Eastern date, the window's last day included:
  - **shelf**: an S-3, S-3/A, S-3ASR, F-3, F-3/A or F-3ASR within `STOCK_READ_DILUTION_SHELF_DAYS` (3 years);
  - **prospectus**: any 424B* within `STOCK_READ_DILUTION_PROSPECTUS_DAYS` (180);
  - **s1**: an S-1, S-1/A, F-1 or F-1/A within `STOCK_READ_DILUTION_S1_DAYS` (180);
  - **placement**: an 8-K whose Items include 3.02 within `STOCK_READ_DILUTION_PLACEMENT_DAYS` (180).
- **States.**
  - `warn` when any kind is on file. `value` names the newest filing of each kind with its month ("S-3
    shelf 2025-03, 424B5 2026-08, S-1/A 2026-07, 8-K 3.02 2026-09"); `detail` gives the dates and counts.
  - `ok` ("None on file") when the registrant is known, the list was read back to the start of every
    window, and none is on file.
  - `unknown` otherwise, the detail saying why -- never read as clean: the first read is under way
    ("Reading EDGAR…"); SEC's ticker list has no registrant for the symbol; EDGAR could not be read (the
    reason, and when Nova asks again); the reader is off; a kept read found none but is past its day; or
    EDGAR pages the list and a page that reaches into a window was not read.
  - `as_of` is when the submissions file was fetched, `null` without a kept read. A read past its day
    keeps a `warn` (what is on file stays on file) and says a new read is under way.
- **The read never waits on the network.** `gather` asks `dilution_reader.view(symbol, now)`, which
  answers from memory and queues the symbol when no fresh read is kept. One daemon thread reads EDGAR:
  - with the desk's SEC user agent (`SEC_USER_AGENT`, else the catalyst feed's default), at most one
    request every `STOCK_READ_DILUTION_SEC_MIN_GAP_SEC` (1 s; the catalyst feed paces its own);
  - a read is fresh until the next 04:00 ET, and never longer than `STOCK_READ_DILUTION_TTL_SEC` (a day);
  - a failed read is tried again after `STOCK_READ_DILUTION_RETRY_SEC` (30 s, 2 min, then every 10 min),
    the next time the symbol is asked about;
  - EDGAR's `recent` block holds a year or 1,000 filings, whichever is more. Older pages are read only
    when at most `STOCK_READ_DILUTION_MAX_PAGES` (2) reach into a window; else that kind is `unknown`.
- **Kept on disk:** `<cache_dir>/stock_read/dilution.sqlite3` (owner `stock_read/dilution_store.py`;
  `PRAGMA user_version = 1`; an unknown version refuses, and the reader then keeps its reads in memory).
  `reads (symbol, fetched_at, body)`, `body` the read as JSON: `{status: "read" | "no_cik", cik, name,
  filings: [{kind: "shelf" | "prospectus" | "s1" | "placement", form, date}], more: string[], unread_to:
  string | null}` (`no_cik` adds `listed_at`). `filings` holds at most `STOCK_READ_DILUTION_KEEP_PER_KIND`
  a kind, `more` names a kind cut there, and `unread_to` is the last filing date of the newest page not
  read. Rows older than `STOCK_READ_DILUTION_KEEP_DAYS` are deleted. `NOVA_DILUTION_READER=0` turns the
  reader off.
- **On the desk** the row shows with the Float tile's rows and in the Signals sheet like any other; its
  source reads "SEC EDGAR" (`stock_read/constants.ts` `sourceLabel`).

`GET /api/stock-read/{symbol}/decisions?date=YYYY-MM-DD` (default today: the trading day, which starts at
04:00 ET, never the calendar date) answers
`{schema_version: 1, symbol, date, generated_at, summary: {text, legs, armed, near, triggered,
trades, refusals: [{reason, count}]}, events: Event[], sources: {journal, hod_momo, borrow,
catalysts, bot: {ok, error}}}` -- one symbol's day, oldest first: the eyes' journal lines of that
symbol (live source, the template in play's lanes only -- `playing: true`; ADR 042: every template
was folded, so each event counted once per template; a run of the same state and reason on one
lane is one event with `count` and
`last_ts`; tape verdict flips fold the same way), the first HOD Momo alert of each strategy and the
day's count, the borrow changes, the day's catalyst and negative news items (the News panel's, so only
while the calendar date is the day's: none for a past day or from midnight to 04:00), the 09:30 open and the
high of day, and the bot's own `bot_trade` / `setup_proposal` lines for the symbol. An **Event** is
`{ts, lane: "first_pullback" | "bull_flag" | "flat_top_breakout" | "red_to_green" | "gap_and_go" |
"hod_momo" | "market" | "bot", event, title, detail: string | null, count, last_ts: number | null, levels:
object | null}`. A source that cannot be read is `ok: false` with its error; the others still
answer.

`GET /api/stock-read/{symbol}/history` answers `{schema_version: 1, symbol, generated_at, daily:
[{d, o, h, l, c, v}] (the last `STOCK_READ_HISTORY_CHART_DAYS` stored sessions), runs: [{date,
prior_close, high, close, run_pct, close_pct, today}] (sessions whose high was
`STOCK_READ_RUN_MIN_PCT` or more over the prior close, newest first), split: {factor: "a:b" | null,
ts, reverse: boolean | null, days_ago} | null (Yahoo's last split), holdings: Row[]}` -- the Level 2
Nova recorded, setups armed on the symbol on any day, the latest short interest, and what Nova does
not keep per symbol yet, said so.

**Fixed with it.** `/sensors/vwap` is the session VWAP from 04:00 ET (the chart's; since 2026-09-30
restarted at the 16:00 close for after hours as the chart does, `anchor: "16:00 ET"` then --
`sensors.math_indicators.vwap_session_bars`, the stock read's VWAP too) instead of the
newest 240 stored bars, and adds `anchor: "04:00 ET"`; `/sensors/halt` answers `halted: null` when
the state is unknown instead of `false`; `ibkr/shortability.cached(symbol)` returns the last
snapshot with its age (a read, never a wait), and `/ws/ticker/{symbol}` re-reads shortability every
`IBKR_SHORTABILITY_TTL_SEC` while the socket is open, every `IBKR_SHORTABILITY_RETRY_UNKNOWN_SEC`
while it is unknown (the Level 2 "SHORT Unknown" chip asked once per tab). The eyes' journal is read
by the desk only through the decisions route and, since 2026-09-29, the past-setups route (below).

**On the desk** (owner `frontend/src/stock_read/`). The Trader tab polls the read every
`STOCK_READ_POLL_MS` while it shows. The plan box and seven tiles sit between the quote and Level 2
(hover a tile for its rows, click it or "All" for the sheet over the charts: Signals, Decisions,
History). The plan opens whole while the quote card is at least `STOCK_READ_PLAN_OPEN_MIN_PX` tall
and is otherwise one line (the setup, entry / stop / target, the size, reward : risk, Stage), so
Level 2 keeps its room; the operator's own open or fold is kept. The size is whole shares of the
operator's risk per trade over the risk a share. The risk per trade is the desk venue's bot sleeve
`caps.risk_usd` (ADR 042: one number sizes every Nova buy and the operator's Stage, per venue),
read from `GET /api/bot/session` and edited with `PATCH /api/bot/session {caps: {venue, risk_usd}}`;
the old `localStorage` `nova.stockRead.riskUsd` is moved there once and deleted only after the
sleeve confirms it (a refusal keeps it and says so on the card). In a Nova mode the plan also
shows the size Nova would send (the stock-mode view's `size`). "Stage in ticket" fills this tab's ticket with a BUY
limit at the entry for that size through the ticket prefill channel. It never places, and the
plan's stop and target stay the operator's to set: the ticket takes no bracket from it. With no
setup forming, the operator's own plan starts from a typed entry or the ask. Its stop is typed, or
dragged on the 1-minute chart with the entry, and the target stays 2R. The 1-minute chart draws
each lane's shapes (the plan's lane in colour, the rest faded), the plan's zones and lines, the
day's levels, a legend and the plan's badge. It frames a forming setup once per setup, and again
when the badge is pressed. Nothing else moves the view: when the plan's zones appear, a view that
follows the live edge slides over to give them room, and a view the operator moved stays put (the
time scale's `rightOffset`, which is its scroll position, is never set). **A view the operator
zoomed or panned is theirs** (operator report 2026-10-06: "As I was zooming in and watching the
chart, all of a sudden it resized itself randomly"; owner `chart/operatorView.ts`, in memory per
chart): once they move a pane with the wheel, a drag or a pinch, no newly leading setup frames it and
no plan zones slide it, until a first paint (another symbol or timeframe, a Sim seek) or Reset chart
hands it back; the badge and "show on chart" still frame on request. A setup is framed at most once
per symbol, so a lead that goes back and forth between setups never reframes the pane. The 5-minute and 10-second charts mirror the plan's levels as thin lines,
and the daily chart marks every +40% run. `localStorage` `nova.stockRead.layers` = `{schema_version:
1, value: {setups, levels, past, labels: "compact" | "full", hidden: string[], plan: "auto" | "open" |
"folded"}}` keeps the switches (`past`, added 2026-09-29, reads true when a stored value lacks it;
`labels`, added 2026-09-30, reads `compact` when a stored value lacks it or holds anything else). A decision's "show
on chart" frames its moment on the 1-minute chart with the levels it armed at. Nothing is drawn or
read on a replay desk (the read is today's live stock) or on the sample desk.

### Setups that ended stay on the chart, and what price did next (ADR 036 amendment, operator ask 2026-09-29)

"after it fails to form ... it says 'pole' with a gray square. Eventually, it removes itself from the
chart ... we could probably go back and study them": the 1-minute chart drew each lane's current state
only, so a setup vanished at the first bar that did not continue it (NCPL 2026-09-29: a bull flag's
pole failed at 09:20 -- "flag candle 2 made a higher high than the candle before it" -- and left the
chart at 09:21, while the price went on through the pole's high). The eyes' journal kept every line,
but nothing read them back as setups, and nothing scored a setup that died before it armed.

**Episodes** (`eyes/episodes.py`, pure). One day's live journal lines of each setup's template in play
(`playing: true`) fold into episodes, one per setup's life on a symbol. An episode opens at the first
line that leaves `watching` and grows while its leg only extends (the same leg, or a later one with a
high at or over it). It ends when the lane goes back to `watching`, when a failed or triggered setup
is followed by a new attempt, when a lower or earlier leg replaces it, or at a `session` line (Nova
restarted). An episode is `{id, symbol, setup_type, template, rev, started_at, ended_at, end: "failed"
| "faded" | "triggered" | "cut" | null, died_at, died_bar_t, reason, reason_key, ended_by, reached:
"leg" | "pullback" | "armed" | "near" | "triggered", leg: {t, high, low, pct, bars?}, setup: object |
null, setup_id, filtered, triggered_at, trigger_price, score: {outcome, bar_r, exit_reason, mfe, mae}
| null, after: After | null}`:
- `ended_at` / `end` / `ended_by` are `null` while the lane still shows it; `ended_by` is the reason on
  the line that ended it ("no pole", or "a new attempt began: ..."). A restart ends a setup that had
  failed or triggered as that, and any other as `cut` (how it would have ended is unknown).
- `died_at` / `died_bar_t` are set the moment it failed (its first `failed` state), while its lane may
  still show it failed for a while; a faded one's are the moment it ended. `reason` is the rule it
  broke -- the first, never a later one -- else what it was waiting on or blocked by when it ended;
  `reason_key` is `reason` with every number replaced by `#`, so a report counts "the flag gave back
  61.9% ..." with "... 83.3% ...".
- `died_bar_t` is the start of the candle the scanner had just read: a line written within
  `EYES_EPISODE_BAR_CLOSE_SEC` (3 s) of a minute is about the candle that closed (bar-close lines land
  about 0.3 s in), else about the one forming.
- `setup` is the levels it last armed with (`null` when it never armed); `score` is a triggered
  setup's own score, from its `scored` lines (they may come after the episode ended).

**After** (`eyes/aftermath.py`, pure): what price did in the `EYES_EPISODE_AFTER_MIN` (15) minutes
after a setup failed or faded, on the chart's one-minute bars (`bars_store`, less IBKR's no-trade
minutes). `{from_ts, price, level, entry, floor, window_min, complete, bars, high, low, first: "high" |
"low" | "neither" | "pending" | "unknown", crossed_at, trade}`:
- `level` is the high it was building under: its trigger when it armed, else its leg's high (for a
  pullback or a flag, above the trigger it would have had -- the test is conservative; red to green's
  is the open). `entry` is one cent over it, or the setup's own entry when it armed.
- `floor` is the low it would have stopped under: its stop when it armed; else red to green's lowest
  low since the open, and any other's lowest low from the candle after the leg's high through the
  candle it died on (`null` without those bars). `price` is that candle's close.
- `first` says which it crossed first, from the candle after the one it died on (the one it died
  inside, when it died between closes): over the level (`high`) or under the floor (`low`). A candle
  that did both reads `low`: the order inside a minute is unknown, and the study never credits a run
  it cannot prove. `neither` once the window passed, `pending` while it has not, `unknown` with no
  candle after it died. `crossed_at` is that candle's start.
- After `high`, `trade` is the trade the rule refused, scored the way an armed setup is: entry one cent
  over the level (the candle's open when it gapped over; the setup's own entry when it armed), stop the
  floor, target entry + `SETUPS_TARGET_R` x risk (the setup's own target 1 when it armed and over the
  entry) -- `{entry, stop, risk, target, outcome: "target_first" | "stop_first" | "open", outcome_at,
  bar_r, exit_reason, mfe_r, mae_r}`. The crossing candle counts its stop only on a close under it (the
  scoreboard's entry-bar rule), a later candle touching both counts the stop, `mfe_r` / `mae_r` read
  `SETUPS_SCORE_WINDOW_MIN` from the cross, and `bar_r` / `exit_reason` are `ScoreTracker`'s exit rules
  on the bars (a 9 EMA over the day's bars). `null` when the floor is unknown or not under the entry.
  Scores, never fills: no tape, no slippage.

**The route.** `GET /api/stock-read/{symbol}/past-setups?date=YYYY-MM-DD` (owner
`stock_read/past_setups.py`; default today: the trading day, from 04:00 ET; a sync route, off the loop) answers `{schema_version: 1,
symbol, date, generated_at, episodes: Episode[] (oldest first, open ones included), counts: {failed,
faded, triggered, cut, open}, journal: {ok, error, lines}, bars: {ok, error, count}}` -- `after` for
every failed or faded one, the failed ones the lane still shows included; `lines` the day's journal
lines read. The day's file is found by listing the journal folder (`eyes.journal.day_path`, which
`GET /api/eyes/at` and the Sim eyes use too): a date from a request is only compared with file names,
never made into a path. Today's file is read as it grows (`eyes.journal_day.JournalTail`: appended
bytes only, never a line the writer has not finished) and folded once for every symbol, in memory;
another day is folded on each ask. A source that cannot be read is `ok: false` with its error (a day
with no journal file: "no eyes' journal on file for DATE") and the rest still answers (`after: null`
without bars).

**On the desk** (`frontend/src/stock_read/`: `pastSetups.ts` the wire and the words, `pastShapes.ts`
the drawing, `ShapeTip.tsx` the hover):
- The 1-minute pane draws each failed, faded and triggered episode of a lane the operator has not
  hidden, where it happened and fainter than the live lanes, dashed, under them: its leg / pole /
  impulse / open, and the pullback / flag / base from the leg's high to the candle it died (or
  triggered) on, between the floor and the level. Its label says how it ended -- `✕` and the rule it
  broke, `○` what a faded one was waiting on, `✓` a trigger and its score -- and what came next ("↗
  then broke out", "↘ then broke down", "→ then went nowhere"). A rule is named in a few words (the
  scanners' rules are listed in `pastSetups.ts`; any other reason is cut to its first clause, 40
  characters).
- A setup that failed is drawn as past from the moment it failed: while its lane still shows it
  failed, the lane's own box gives way to it. Before the past setups are read (or with the layer off)
  the lane's failed box says `FAILED` and the rule, on the pole's box when a bull flag failed before
  its flag.
- A faded episode that never got past its leg (a leg, a pole or a new high with no pullback, flag or
  base) is not drawn: it is the chart's own candles (59 of the 173 setups that had ended by 10:00 ET
  on 2026-09-29).
- Hovering a setup's box -- live or past -- shows its whole story (`SetupShapesPrimitive.hitTest`
  names the box): the state or end with the full reason, the times, the level, the floor, what price
  did next and the refused trade's outcome.
- The legend's "Past" chip switches the layer (`nova.stockRead.layers` `value.past`), counts what it
  draws, and says why when the backend has no such route. The read is fetched every
  `STOCK_READ_PAST_POLL_MS` while the Trader tab shows with the layer on, and at once when a lane's
  drawn state changes, so a setup that fails or ends is drawn as past within one read. Nothing is drawn
  on a replay desk or the sample desk.
- **Labels make room** (operator report, 2026-09-30: "i do really like seeing the details, but perhaps
  it is extremely too crowded"; LGHL that morning drew 15 past setups, their labels piled on each
  other; then "maybe the compact form should just show (x) and when we hover, it shows the full failed
  setup"). The legend's labels chip beside "Past" (`value.labels`) sets how much a past setup's label
  says: `compact` (the default) its mark alone -- `✕` failed, `○` faded, `✓` triggered -- and no leg
  or pole label; `full` the whole label. Pointing at a label shows the story its box's hover tells
  (`SetupShapesPrimitive.hitTest` names the labels the last draw placed, then the boxes). Either way
  the labels are placed (`stock_read/sceneLabels.ts`, pure): the live lanes' labels, the levels'
  words, the edge tags and the moment's pin stay where they are; the past labels take the room left, a
  trigger's result first, then how the newest ended, then the legs. Each takes the longest form its
  setting allows -- in `full` whole, then a few words ("✕ topping tail ↘", "✓ +1.4R"), then its mark --
  that touches no label already placed, and none when even its mark would; its dashed box and its
  hover stay. A label whose box starts past the pane's left or right edge is kept inside the pane.

**The study.** `py -3 tools/setup_failures.py [--date D | --days N] [--setup S] [--symbol X] [--all]
[--list] [--json]` (read-only; owner `eyes/failure_study.py`) folds the journals and the stored bars
into the same episodes and totals the failed and faded ones by setup, end and reason, faded legs left
out unless `--all`: `{schema_version: 1, generated_at, dates, filters: {setup, symbol, include_legs},
ended, left_out_legs, missing_bars: string[], groups: [{setup_type, end, reason_key, example, count,
first: {high, low, neither, pending, unknown}, trade: {n, target_first, stop_first, open,
avg_bar_r}}], triggered: {count, target_first, stop_first, open, avg_bar_r}, episodes?}` (`episodes`
with `--list`; `triggered` totals the triggered setups' own scores, for comparison). A symbol-day
without stored bars counts its episodes `unknown` and is named in `missing_bars`.

### The day's levels: support and resistance on the charts and in the plan (ADR 036 amendment, operator ask 2026-09-30)

"say our target is 1:2 ratio for trades is too generic, sometimes we have to look at the very obvious
resistance/support levels"; then "the material teach us that there are stops at half dollar or full dollar
which are great psychological triggers", and, on the mockup, "we are overloading the 1min chart". Measured
first (`F:\Nova\eyes\studies\levels-2026-09-30`, in sample): half and whole dollars turn price back before
they break (76% of fresh approaches printed through within 10 minutes, against 84% at a random price) and
are a trigger once through (+1.5% before -1.5% in 77% of breaks, against 70%; a break under 68% against
63%); the high of day and tested tops slow price a little; old daily highs do not; capping the target at
a level costs. So the target stays 2R, and the levels describe. Nothing here places, stages or blocks.

**The level map** (owner `stock_read/level_map.py`, pure). `GET /api/stock-read/{symbol}` adds
`level_map: {schema_version: 1, price, rounds: {minor, major, measured, words} | null, intraday: Zone[],
five_minute: Zone[], daily: Zone[], daily_sessions, daily_error: string | null, study: {source, round_turn,
round_through, round_lost, hod_past, top_past, daily_past}}` -- each
study pair `[at the level, at a random price]` in percent (`STOCK_READ_LEVEL_STUDY`); `rounds` is the
price's scale of round numbers (below), `null` without a price. A **Zone** is
`{id: "<home>:<lo>", lo, hi, price (its edge nearest the price), side: "above" | "below" | "at" |
"unknown", strength, label ("$7.50 · top ×8 · VWAP"), tag ("$7.50"), home: "intraday" | "five_minute" |
"daily",
members: Member[]}`, highest first; a **Member** `{kind, price, label, touches: integer | null, times:
number[] (an intraday level's tests, epoch seconds), dates: string[] (a daily level's sessions), note:
string | null}`. `kind` is one of `hod | lod | pmh | open | vwap | top | bottom | whole | half |
yday_high | yday_low | prior_close` (today's map; `whole` is the scale's major round, `half` its minor one,
and `note` names it: "whole dollar", "$5 round number") and `daily_highs | daily_lows | daily_high | gap |
sma200 | yday_high | yday_low` (the daily map).
- Today's map reads the session's closed one-minute bars from 04:00 ET: the high and low of day; the
  premarket high once the regular session has a bar; the 09:30 open; the session VWAP; tops and bottoms
  -- swing highs (lows) over (under) the two candles before them and even with the two after, within 0.3%
  (at least a cent), tested twice or more; the round numbers within 25% of the price; yesterday's
  high and low (the stored daily bar, extended hours included) and the regular session's prior close.
  The plan reads it (Room, `between`; trial T7 is registered on it).
- The 5-minute map (`five_minute`, operator report 2026-09-30: "why does it say it's a double top when,
  on the graph, we only see one top?") reads the same day from 5-minute candles made of those minutes on
  the clock (`level_map.five_minute_bars`; a candle counts once its five minutes are over): the high and
  low of day, the premarket high, the open, and tops and bottoms by the same swing rule on the 5-minute
  candles -- so two 1-minute tops inside one 5-minute candle are one top here. A round number is
  kept only in a zone with another reason. No VWAP (the chart draws its own line) and nothing from
  yesterday (the Full Day pane's). A backend older than it sends no `five_minute`; the desk then draws no
  5-minute levels and says so.
- The daily map reads the stored daily bars before today: highs and lows within 2% touched twice or more
  in the last 60 sessions; up to three older daily highs above the price, reading right to left, each
  higher than every high after it ("look left and up"); unfilled gaps (the part no later session traded);
  the 200-day average (`history.summary` adds `sma200`: the last 200 stored daily closes before today,
  which close after hours; `null` with fewer); yesterday's high and low. `daily_error` says why the
  daily map is empty when the history could not be read.
- Levels within 0.6% (today) or 1.5% (daily), and always within 2 cents, are one zone, at most twice that
  wide; a zone lists every member, and its label counts one kind once ("top ×8", not "top ×5 · triple
  top"). `side` is `at` within 0.2% (at least a cent) of the price.

**The stock's own round numbers** (owner `stock_read/rounds.py`, pure; operator report 2026-10-01 on ACN at
$223: "I'm pretty sure you could see the problem here. How do we address this without losing important
visibility on important resistance and support levels?"). Every half dollar had been a level at any price:
ACN's plan listed 26 of them between a 217.53 stop and a 236.61 target, one check each, its ruler printed
27 prices on top of each other, and today's map was zones of six half dollars that buried its real levels
("$216.00 · top ×14 · $217.00 · $218.00 · $215.50 · open ..."). Round numbers now scale with the price
(`STOCK_READ_ROUND_LADDER`, a minor round always 2% of the price or more): half and whole dollars up to $25,
$1 and $5 to $50, $2.50 and $10 to $125, $5 and $10 to $250, $10 and $50 to $500, $25 and $100 to $1,250,
$50 and $100 to $2,500, then $100 and $500. One scale per read, from the map's price, for the map, the
plan's notes, marks and checks and the read's next-round row. `rounds` on the wire is `{minor, major,
measured, words}`: `measured` only for half and whole dollars on a $1-$20 stock, where the level study
looked; anywhere else a note's `detail` and the level's card say the rounds are not measured instead of
quoting the study, and Room is not trial T7's (`trial: null`, its detail says why: T7 counts half and whole
dollars). A target or stop is on a round within a tenth of its step (`STOCK_READ_ROUND_NEAR_SHARE`: 5c at a
half dollar, 50c at $5). The plan's checks list the rounds between the entry and the target on one line
("$225.00, $230.00 and $235.00 before the target"; past three, "4 round numbers ($15.50 to $17.00)"), and
the desk's ruler leaves off a label that would touch a stronger one (a seller on the book, then the high of
day and the day's levels, then a round; `planMath.placeRulerLabels`) and keeps its tick. On ACN's bars that
morning: checks 32 to 7, ruler marks 27 to 4, and the map names "217.99 · triple top", "$215.00 · top ×15 ·
bottom ×5 · VWAP · open" and "$220.00 · double top · PMH".

**What the plan says** (owner `stock_read/level_notes.py`, pure). The Plan adds `levels: {room, target,
stop, next, recent, between} | null` (null without a map). Each note is `{state, text, detail}` (`detail`
quotes the study):
- `room` adds `{r, price, label, trial: "T7" | null}`: the first zone of today's map over the entry, in R
  (`trial` null on a stock whose rounds are not half and whole dollars: T7's map counts those);
  `warn` under `STOCK_READ_ROOM_MIN_R` (2R), `ok` at or over it or with none, `unknown` without a stop. The
  daily zones between the entry and the target are named in its detail and never counted. It blocks
  nothing: trial T7 (`knowledge/signal-trials-2.json`) decides whether it ever becomes a NOT A TRADE reason.
- `target` / `stop`: a round number within a tenth of its step (5c at a half dollar) of the target or the stop
  -- a target under the round sells before it (`ok`), one on or over it needs the break (`warn`); a stop
  under a round the entry is over survives its test (`ok`), one on or just over it does not (`warn`).
  `null` when no round is near.
- `next`: the next round number over the entry (else the price) -- `warn` within a tenth of a step ("turns
  back about 1 in 4 before it breaks" where the study looked), else `info`, "resistance until it prints
  through, a trigger after".
- `recent`: a round the price broke (`ok`) or lost (`bad`) within `STOCK_READ_ROUND_CROSS_SEC` (10 min)
  while it still stands on that side; a cross is fresh when the 15 candles before it stayed on the other
  side. `null` otherwise.
- `between`: today's zones strictly between the stop and the target, `{price, lo, hi, tag, label, round,
  hod}`.

**On the desk** (owner `frontend/src/stock_read/`: `levelPicks.ts` which zones a chart draws and each
card, `levelRender.ts` the drawing, `levelTypes.ts` and `levelMapNormalize.ts` the wire, `PlanLevels.tsx` the
rows, `paneKeyRows.ts` / `ChartKey.tsx` each pane's Key). Each chart draws only the levels its own candles
show, and no level twice (operator, 2026-09-30: "Every chart has special needs and special powers ...
There's no reason to have duplicate information"). Every level is a line (a band when the zone is wide)
with a short label at the right edge (the pane's one column, below) -- its price, what it is and what
the candles made of it ("$17.50 · double top", "23.52 · HOD · double top", "16.38 · PMH") -- and a card
under the pointer: what it is and how far from the price, why it is there in plain words (each top or
bottom with the candles it was counted on and when), and what usually happens there, from the study. The
**5-minute** pane draws the 5-minute map: per side the nearest zone and the strongest others within 12% of
the price (three in all), the zone the price is on, the high and low of day; every other zone is a short
tick on the price axis. The **Full Day** pane draws the daily map the same way within 40%, with
yesterday's levels. The **1-minute** pane draws from today's 1-minute map the high of day, the zone the
price is on, the nearest zone over and under it that its candles made (a top or a bottom tested twice or
more), the nearest round dollar each side and the plan's `between` levels, with no ticks; the premarket
high and the open are the 5-minute pane's. (Until 2026-09-30 these were price lines without an axis
label, and lightweight-charts 5.1 shows a price line's title only beside its axis label: the 1-minute
pane's level lines never showed their names.) The **10-second** pane draws the plan's lines only. Every
pane's corner carries a **Key** chip: pointed at, focused or pressed, it lists what each colour on that
pane means -- the time-of-day background on the intraday panes, the levels, and on the 1-minute the
setup boxes and the plan's lines. The plan
card lists Room (with "in trial T7" while amber), Target, Stop, "$ next" and "$ now", each one line with
its detail on hover, and the ruler marks the `between` levels. The toolbar's Levels switch
(`nova.stockRead.layers` `value.levels`) turns every chart's levels on or off. Nothing is drawn on a replay
desk or the sample desk.

**One column at a pane's right edge** (operator report 2026-09-30: "everything is getting on top of each
other in the charts!"). The right edge had three owners -- the levels' labels stacked among themselves,
lightweight-charts drew the EMAs', VWAP's and the plan lines' titles on its own, and the tags for prices out
of view sat at a fixed spot the 1-minute pane's corner chips covered -- so they landed on each other. The
stock read now claims each pane's edge (`chart/edgeWords.ts`, in memory per chart):
- the overlays (`components/TickerChartOverlays.tsx`) blank their series titles and publish their names;
  the plan's price lines keep their prices on the axis and give their names to the column; the position tag
  reserves its spot;
- one column (`stock_read/edgeColumn.ts`) places every word: on its line where there is room, else the
  crowd centred on its lines in their order, with a hairline back to each line. A crowd that cannot sit
  within three rows of its lines drops its least important word first -- the plan's lines, VWAP, the high
  of day, the levels, the 9 / 20 / 200 EMA, then the tags -- and a level that loses its label keeps an axis
  tick that opens its card;
- the tags for prices out of view (an EMA's with its value: "↑ 200 EMA 1048.99") stack under the corner
  chips and at the bottom, at most three at each end; the 1-minute legend ends where the price axis begins.

A pane without the stock read (a replay desk, the sample desk) keeps the series' own titles. The EMAs no
longer stretch the price scale on any chart: the candles decide what prices a pane shows (LGHL's 200 EMA,
a year of reverse splits behind it, squeezed the Full Day candles into a flat line). The Full Day pane's
+40% runs are drawn by the scene: every run keeps its arrow, and where labels crowd today's and then the
biggest runs keep theirs.

**The close countdown keeps clear of the pane's words** (operator report, 2026-10-05: on a 5-minute pane the
countdown chip sat on the setup's "5m ... +83.3%" label). The chip over the forming candle
(`chart/BarCountdownPrimitive.ts`, on every minute pane) knew only the candle, and a live lane's label starts at
its box's left edge a few candles back, so it ran under the chip; a sell's price over the forming candle did too.
Each primitive that writes words on a pane now publishes the rectangles it drew (`chart/paneWords.ts`, in memory
per chart, nothing persisted): the stock read's labels, pins, fixed labels and edge column, and the fill arrows
with their prices. When the chip's usual spot (centred over the wick) touches one, it takes the first clear
spot: beside the candle on its right at the wick's middle, then over it, under the candle, beside it on the
left, and then a row at a time higher and lower. It never sits on the forming candle, and with no clear spot it
is not drawn for that paint: a covered label is information lost, a missing digit for a moment is not. Draw
order between primitives is not relied on: a change in the words after the chip's own paint is announced once,
after the paint (a microtask), and costs one more paint; a chip that painted after the words costs none. The
setups' labels still place as they did (a live lane's whole where it is); only the chip yields. No wire or
stored shape changed.

### Who trades the stock (ADR 037, operator ask 2026-09-24, #604, #606)

"When may Nova buy for you? I want a clear option next to level 2 ... if I selected the exit is on
me, then I'm going to be the one who exits, not the bot." Owner `backend/stock_mode/`: the routes,
the in-memory store and the runner. Nova places for a stock only on Paper, or on Sim at the live
edge. On Live every Nova side is locked, and the lock says why: a Nova buy is `auto_live`, NO-GO,
and Approve on Live waits on #604.

**The view.** `GET /api/stock-mode/{symbol}` answers `{schema_version: 1, symbol, generated_at,
venue: "live" | "paper" | "sim" | null, mode: "signal" | "approve" | "auto_entry" | "bot", buy:
"you" | "nova", sell: "you" | "nova", risk_usd: number | null, set_at: number | null, locks:
{buy: string | null, sell: string | null}, notes: [{id, tone: "info" | "warn", text}], approval:
Approval | null, trade: Trade | null, entries_today: {count, cap}, nova_entries_today: integer (one
release), size: {qty, by_risk, capped_by, text} | null, last_event: {ts, tone: "info" | "ok" | "warn" |
"bad", text} | null, bot: {on_list, playing, reason, setup_at_strategy, active} | null}` (ADR 042:
`risk_usd` is the venue sleeve's, read-only here; `size` is what Nova would send for the stock's plan;
`setup_at_strategy` is the plan's setup; the bot's skips on the stock become its `last_event`).
- `locks.buy` / `locks.sell` say why Nova cannot take that side now (`null` means it can): Live, a
  replay desk, or a venue Nova cannot read.
- `notes` name **every** thing that will keep Nova from acting although the switch is set (ADR
  042, not only the first): the venue, the padlock, the kill switch, the day lock, the bot trip, the
  bot not active, the plan's setup not at Strategy, its window, extended hours, no depth line, NOT A
  TRADE, a stock the scanner does not follow, the day's Nova entries used, and what could not be
  read (`bot_unreadable`, `trades_unreadable`, `scanner_unreadable`).
- An **Approval** is `{setup_id, setup_type, entry, stop, target, qty, approved_at, state:
  "waiting" | "sent" | "withdrawn", reason}`.
- A **Trade** is `{kind: "auto_entry" | "approve" | "bot", state: "entering" | "holding" | "closed"
  | "missed" | "handed", venue, venue_day, setup_id, setup_type, qty, entry, stop, target,
  entry_order_id, target_order_id, stop_order_id, fill_price, filled_at, exit_price, exit_reason:
  "target" | "stop" | "time" | "flush" | "outside" | "handed" | null, exits: "nova" | "you", sent_at, closed_at:
  number | null, note, exiting: boolean}` -- `closed_at` when it closed, missed or was handed;
  `exiting` true while the bot is selling it. The bot's own trade is mapped from `bot-session.json`
  (`entry_sent_ts` is its `sent_at`, `closed_ts` its `closed_at`; `open` and `exiting` read `holding`).

`GET /api/stock-mode` answers `{schema_version, generated_at, venue, stocks: [view]}` for every
stock that is not at Signal only.

**Changing it.** Writes need the desk's API key even on loopback (they place orders), like the bot
routes.
- `PUT /api/stock-mode/{symbol}` takes `{buy, sell}` and answers the view (a `risk_usd` it is
  sent is ignored: Nova sizes by the venue sleeve, ADR 042).
  - **One owner** (ADR 042): Nova / Nova puts the stock on this venue's bot list
    (`symbol_allowlist`), and the list is written only through these rules -- `POST
    /api/bot/allowlist {symbol, op}` and `PATCH /api/bot/session {symbol_allowlist}` (which answers
    `refused: [{symbol, reason, error}]` and applies the rest) go through them too, with the Live lock,
    "you hold it" and the 50-stock cap (`BOT_ALLOWLIST_FULL`) refused before anything changes. A
    stock has one mode: Bot clears an Auto-entry or Approve switch, and the reverse; `op: remove`
    sets Signal only.
  - Moving Sell from Nova to You takes over the exit (below). Moving Buy from Nova to You cancels a
    Nova entry that is still working.
- `POST /api/stock-mode/{symbol}/approve` takes `{setup_id, entry, stop, target, qty, now?}` and
  answers the view. The stock must be in Approve, and the plan must be the lane's own: the setup id,
  with its levels within a cent. `now: true` on a triggered setup sends the bracket at once.
- `DELETE /api/stock-mode/{symbol}/approve` withdraws a waiting approval, or cancels a sent entry
  that has not filled; its exits go with it.
- `POST /api/stock-mode/{symbol}/take-over` cancels the exits Nova holds on the stock:
  - Approve's two bracket legs;
  - or the bot's trade. The bot cancels its target and stop legs, stops watching, and ends the
    trade `handed`, releasing its shares from the sleeve.
  - Buy always stays on You after a take-over (ADR 042: it could turn into Auto-entry and buy the
    next trigger at the old risk), and a cancel that is refused keeps the trade and says the order
    still rests.

A refusal is `{detail: {reason, error, field}}`:
- 400: `STOCK_MODE_INVALID`, `STOCK_MODE_RISK`.
- 409 `STOCK_MODE_LIVE`: a Nova side on Live, or on a venue Nova cannot read.
- 409 `STOCK_MODE_REPLAY`: Sim off the live edge.
- 409 `STOCK_MODE_HELD`: Sell to Nova while the stock is held.
- 409 `STOCK_MODE_NOT_APPROVE`.
- 409 `STOCK_MODE_FILTERED` / `STOCK_MODE_NOT_A_TRADE`: Approve on a setup the template's filter keeps
  out, or a plan that is not a trade.
- 409 `STOCK_MODE_PLAN_CHANGED`: the setup is no longer armed at those levels.
- 409 `STOCK_MODE_NOTHING_HELD`: Nova holds nothing of this stock to take over.
- 409 `STOCK_MODE_BOT_EXITING`: the bot is already selling.
- 409 `STOCK_MODE_SEND`: the execution door refused the send; `error` is the door's own reason.

**What Nova does.** The runner (`stock_mode/runner.py`) hears the setup scanner's triggers
(`SetupEngine.add_trigger_listener`, live feed only).
- **Auto-entry is the bot's rules with the exit handed to you** (ADR 042, `admit.for_auto_entry`):
  the first go trigger of a setup at effective Strategy (never one at Off or Eyes), the first of the
  day, inside that setup's bot window, with extended hours as the sleeve says, within the shared
  daily cap, never NOT A TRADE, at most `BOT_FP_TRIGGER_MAX_AGE_SEC` old, and only while the bot is
  Active, sends one BUY limit at that setup's entry.
  - Size: the sleeve's (one size for every Nova buy).
  - Source: `bot`. A stock on the bot list never auto-enters (the bot trades it).
  - The gates as the bot's, plus no Nova order already working on the stock.
  - Unfilled after the sleeve's `working_ttl_sec`, it is cancelled and the trade ends `missed`.
  - After the fill the trade is `holding` with `exits: "you"`: Nova places no exit.
- **Approve.** The approved setup's go trigger (fresh) sends one bracket: `operation: "bracket"`,
  `source: "manual"`, an entry limit, a target limit and a stop.
  - It is cancelled unfilled after the sleeve's `working_ttl_sec`. Its size is the operator's
    approved quantity (no sleeve caps); it is counted, never capped, by the daily count.
  - A re-arm at other levels, or a failed or disarmed setup, withdraws the approval with the reason.
- **Every act and every skip** is a `stock_mode` line on the bot audit stream. `outcome` is one of
  `set`, `approved`, `withdrawn`, `sent`, `skipped`, `filled`, `missed`, `closed`, `handed` and
  `refused`, and `inputs` carry the symbol and the setup id.

The switches and approvals are in memory only (`stock_mode/store.py`) and stamped with the venue: a
restart or a venue change returns every stock to Signal only. **Nova's trades are persisted**
(ADR 042): `stock-mode-trades.json` in the operator cache, `{schema_version: 1, ...}` (an unknown
version refuses loudly and is never overwritten; kept `STOCK_MODE_TRADES_KEEP_DAYS`), so a restart
resumes managing them (TTL cancels, fill notices). The bot's list belongs to the venue's dial and
lasts; with Activate cleared on every start, nothing buys after a restart until the operator presses
Activate. **Leaving a venue cancels Nova's working entries there first** (`stock_mode/leave.py`):
before the desk moves, every Nova entry still working on the venue it leaves -- the bot's,
Auto-entry's, an approved bracket's -- is cancelled there (a `missed`); no new entry starts while it
runs (`BOT_VENUE_CHANGING`); `POST /api/desk/venue` answers `left: [{venue, symbol, order_id, by,
text, ok}]` and the desk toasts each. Open positions keep their resting exits.
Sell: You means Nova never sells the trade; the loss breakers and KILL still flatten every position.

**On the desk** (owner `frontend/src/stock_read/`, with the stock read):
- The "Who trades" row sits directly above Level 2. The same switch is a chip under the plan's badge
  on the 1-minute chart.
- The badge carries the moment track (Forming, Trigger, Holding, the exit), computed from the lane's
  state, the position and the orders (`stock_read/momentModel.ts`, pure). The chip opens the four
  modes; a mode Nova cannot take now is locked with the reason.
- ENTER NOW, SELL NOW and what Nova just did appear in the badge's corner, with one ping per event,
  and as a tag on the chart at the event's price and candle. ENTER NOW stays up 30 s after the
  trigger while the price is within half a risk of the entry; SELL NOW is kept once the target or the
  stop printed while the operator held the stock (this tab's memory of the position, never
  persisted); what Nova did stays up 30 s. `localStorage` `nova.stockRead.sound` = `{schema_version:
  1, value: boolean}` mutes the ping.
- The plan's stop and target are dashed while they are only a plan, and solid while an order stands
  behind them.
- Level 2 draws ENTRY, STOP and TARGET as separator rows where they sit in the book (the
  `MontageSide` `markers`).
- The plan card's buttons follow the mode:
  - Signal only: Stage in ticket; Stage sell (at the target, or at the bid once an exit is due)
    while shares are held.
  - Approve: Approve (an armed plan), Approve: buy N now (after its trigger), Approved · cancel,
    Cancel stop and target (take over the exit).
  - Auto-entry: Auto-entry on · turn off; Stage sell once Nova bought.
  - Bot: Bot on SYMBOL · stop it; Take over the exit while the bot holds it.
- The badge promises a Nova buy ("THE BOT TRADES THIS", "NOVA BUYS AT ...") only when nothing
  blocks it (ADR 042); otherwise it says why, every reason on hover. The plan card shows the size
  Nova would send in a Nova mode. The Bots page lists every stock not at Signal only (`GET
  /api/stock-mode`), so an Auto-entry stock is never invisible once its tab closes.
  - A trade Nova closed on the plan's setup reads "Closed · +$X" (gross, from the fill to the exit).
- The Trader reads the view every `STOCK_MODE_POLL_MS` while the tab shows. Nothing is read on a
  replay desk or on the sample desk.

### Managing a trade you hold (ADR 036 / 037 amendment, operator ask 2026-10-01)

"If I enter a trade, can it tell me on the chart when I should sell ... if we pass that level, okay, this is
the next level ... I can instruct Nova to sell it for me"; on mockup v4b: keep the plan box as it is and add
the THEN / NEXT / NOW / BROKE ladder, then "lets move these targets ... to the 10 seconds chart". Owners
`stock_read/held.py` (pure), `stock_mode/exit_trade.py`; on the desk `frontend/src/stock_read/`.

**The read while you hold.** `GET /api/stock-read/{symbol}` takes `held_qty`, `held_avg` (both > 0: the read
adds `held`), `held_stop` (your stop; absent, the read proposes one), `held_risk` (the risk a share your R is
measured in; absent, the average less the stop while the stop is under it, else R is unknown) and
`held_since` (epoch seconds you have held since). `held` is `null` without them.
`held: {schema_version: 1, qty, avg, price, open_usd, r: number | null, risk: number | null,
stop: {price, source: "yours" | "proposed" | "nova", rule, printed: boolean} | null,
raise: {to, round, at, text} | null, target: {price, rule, traded_at: number | null} | null,
ladder: [{role: "then" | "next" | "now" | "through" | "broke" | "support" | "stop" | "cost", price, text,
r: number | null, usd: number | null}], broke: [{round, at, close}], through: [{round, at, high}],
levels: {room, target, stop, next, recent}, checks: Check[]}`:
- **The stop**: Nova's when Nova holds the exit (`nova`, "Nova takes the exit" below), else `held_stop`
  (`yours`), else proposed: the lowest low of the last `STOCK_READ_MANUAL_STOP_BARS` closed 1-minute
  candles when it is under the price, else 1c under the nearest zone of today's map under the price
  (`proposed`; `null` when neither exists). `printed`: a price at or under it since `held_since`.
- **Broke and through** (the stock's own round scale, `rounds.of`): a round is **broke** when a closed
  1-minute candle since `held_since` closed 1c or more over it after the
  `STOCK_READ_ROUND_FRESH_BARS` closes before it stayed under it (`at`: when that candle closed), and
  **through** when the price stands over it, a candle's high since `held_since` crossed it and no close has.
  A one-second sweep is at most through: only a close moves a stop.
- **Raise**: the highest broke round whose `round - near` (the stock's own `rounds.near`: 5c under a half
  dollar) is over the stop and under the price -- `to` is that price ("raise the stop to 5.95, 5c under
  $6.00"); `null` otherwise. Up only.
- **The target**: the average plus `STOCK_READ_TARGET_R` x the risk (your 2:1); `traded_at` when a candle
  since `held_since` reached it.
- **The ladder**, highest price first: the first two zones of today's map over the price (`next`, `then`),
  the price (`now`), the through and broke rounds under it, the nearest zone under the price over the stop
  (`support`, when no broke round is there), the stop and the average (`cost`). `r` is in the held risk.
- **The rows** (`levels`, the plan's note shape) are measured from the price, never the entry: Room to the
  first zone over the price in R (`info`; trial T7 reads entries, not positions), the target behind or
  ahead, the stop's round (`level_notes.stop_note`), the next round over the price and a round just
  broken or lost. `checks` are the plan's checks that hold for a position: the spread against what the stop
  gives back, the 1-minute MACD, the 9 EMA, VWAP, the tape's flow, bids pulled and a halt.

`GET /api/stock-read/{symbol}/flush` (cheap: the sensor rings only) answers `{schema_version: 1, symbol,
at, score: number | null, label: "burst" | "flush" | "neutral" | "quiet" | "blind", window_sec}` -- trial
T1's reading (`tape_flow` with a 30 s window, every other number the default); the Trader reads it every
`STOCK_READ_FLUSH_POLL_MS` while you hold. It is a call in trial, never an order.

**On the desk.** While the tab's account holds shares (the venue's position):
- The plan box stays the box it is (#675): its header names the trade (THIS TRADE, shares @ average, the
  badge, open P&L and R); its five numbers become Average, Stop, Next, At the stop and Holding; its ruler runs
  from the average (●) past the stop to the level after next (dim green: locked in by a stop over the
  average; red: what the stop gives back from here; green to the next level; dotted to the one after); the
  ladder sits under the ruler; the rows and checks are `held`'s. The stop is yours to set: "Use stop",
  "Raise stop to X" and typing it set it for the tab (never an order); Stage sell fills the ticket.
- The 10-second chart draws the trade's levels -- THEN, NEXT, SUPPORT, STOP, the average (COST) and the
  broke rounds -- each a line with its name in the edge column. The 1-minute chart keeps its setups, levels,
  the badge and one call: SELL NOW · STOP (the stop printed), SELL NOW · FLUSH "in trial T1" (a flush 10 s or
  more after you held; description only on Live), BROKE $X · NEXT Y with the raise offered, TARGET HIT.
- Level 2 marks NEXT on the ask side and STOP on the bid side.

**Nova takes the exit** (Paper, and Sim at the live edge). `POST /api/stock-mode/{symbol}/take-exit` takes
`{stop, trail: boolean}`: Nova places a SELL stop for every share the venue holds at `stop` through the
execution door (source `manual`, origin `nova_exit`) and keeps a trade `{kind: "exit", state: "holding",
exits: "nova", qty, entry (the average), fill_price, stop, target: null, trail, stop_order_id,
raised: [{at, from, to, round}], ...}` (`stock-mode-trades.json`; the trade shape adds `trail` and
`raised`, and `kind` adds `exit`). No target rests beside it: the door lets one order sell the same shares,
and a one-cancels-other exit pair is built only as a bracket's legs, with an entry -- a target for a held
position waits on an exit-only pair in the door (#681). The runner (`exit_trade.manage`, every
`STOCK_MODE_POLL_SEC`): the stop that fills closes the trade; a position gone closes it `outside`; a stop
cancelled outside Nova hands the exit back (`handed`); with `trail`, at each closed minute a broke round
since the trade began raises the stop by a replace of the stop order (the rule above, up only), an audit
line `raised` and the stock's last event. Refusals: `STOCK_MODE_LIVE` / `STOCK_MODE_REPLAY` (Live, a venue
Nova cannot read, Sim off the edge), `STOCK_MODE_NOTHING_HELD` (no shares, or the position cannot be
read), `STOCK_MODE_INVALID` (a stop at or over the last price), `STOCK_MODE_HELD` (Nova already holds an
exit or an entry on it), `STOCK_MODE_SEND` (the door refused). "Take it back" is `POST .../take-over`
(the stop cancelled, the trade `handed`); Sell: You on the switch does the same. While it holds, the view's `sell` is `nova`. The Sell switch to Nova on a
held stock opens the sheet instead of `PUT` (which still answers `STOCK_MODE_HELD`). On Live the sheet is
locked and says why: Nova never moves a Live order by itself, and a Live stop does not trigger before
09:30 (#604).

### Catalysts (ADR 024)

One pure classifier, `backend/catalysts/classify.py` (rules and `CATALYST_RULES_VERSION` in
`constants_catalysts.py`), for the backfilled history and the live desk. An item is
`catalyst` (`strength: "strong" | "weak"`), `negative` (dilution, delisting), `routine` or
`noise` (movers lists, "why is it moving", law-firm adverts, opinion, stock screens, roundups of
more than three tickers). Rules v6: a one-ticker "why is it moving" rewrite is labelled by the
cause its summary names ("... after the company priced a $5 million offering") when that cause
is a placed catalyst or dilution, and stays noise otherwise (no cause, "no news", a peer's news,
a denial, a list of stocks, an analyst piece). Rules v7 (#517): an EDGAR item of form `4` is a
Form 4 open-market purchase (transaction code `P`) by an officer or a director, its dollar total
stamped in `sec_items` as `P:<whole dollars>` (`catalysts/form4.py`); at or above
`CATALYST_INSIDER_BUY_MIN_USD` (25,000) it is `catalyst` / `listing_financing` / `weak`, below it
(or unstamped) `routine` / `corporate_routine`. Rules v8 (2026-10-02, AMOD): a raise (an offering, a
private placement, a `PIPE`) whose money or consideration is a digital-asset treasury ("bitcoin-funded",
"consisting of 3,170 bitcoin", never bitcoin mining) is `catalyst` / `crypto_treasury` / `weak` with
`dilution: true`, judged after the strong classes and before plain dilution (an EDGAR filing is searched
across its whole stored item text); `PIPE` (case-sensitive) is a raise word, except a headline about a PIPE's
investors or shares; an item's `n_tickers` counts names, not symbols (`classify.ticker_count`: `IONQ.WS`
names IONQ again, and one crypto pair on a company's story names the coin it is about -- AMOD + BTCUSD is
one -- while several pairs each count). A **verdict** for a symbol-day reads only
items published after the prior
session's 16:00 ET close and at or before its cutoff: `{verdict: "catalyst" | "negative" |
"routine_only" | "noise_only" | "none_found" | "not_checked", category, strength, title,
source, published_ts, url, negative_too, rules_version}` (plus `sources_answered`, `n_items`).
`none_found` only when a source looked; `not_checked` when none did. The live verdict adds
`news_pending: boolean` (a Nasdaq T1 / T12 halt inside the window with no resumption yet),
`halt_code: string | null` and `prior_session: {kind: "catalyst" | "negative", category, strength,
dilution, title, source, published_ts, url} | null` -- the best-ranked catalyst or negative item the
live catalyst feed recorded from the prior session's 04:00 ET open to its 16:00 close (ADR 024
amendment 2026-10-02). It is shown, never counted: `verdict`, `category`, `negative_too`,
`sources_answered` and the News pillar read only the window. `null` is none on file, never a claim the
company said nothing, and always `null` in Sim playback. The feed keeps its items in memory back to that
04:00 open (`CATALYST_FEED_MEMORY_HOURS` at least).

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
**Form 4** (#517) is its own feed source, `edgar_form4` (owner `catalysts/feed_form4.py`): EDGAR's
latest Form 4s (`owner=only`), the issuer's entry only (its CIK names the ticker), each listed
issuer's filing read once as its full submission text; only an officer's or a director's
open-market purchase is recorded -- an `items` row with `source: "edgar"`, `form: "4"`, the stamp in
`sec_items` and a title like `Form 4: open-market purchase by <owner> (<role>), <shares> shares
($<value>)`. Its span is separate from `edgar`'s, so a Form 4 burst never breaks the 8-K / 6-K
span; a filing that cannot be read (after `CATALYST_FEED_FORM4_MAX_ATTEMPTS`, or unparseable) breaks
it there. It is not in `CATALYST_FEED_COVERAGE_SOURCES`: it reads one filing type, so its silence
never supports `none_found`.
`/api/diagnostics` adds the `catalyst_feed` row (group `recorder`) with
`evidence.sources: {name: {last_ok, last_error, items, gaps, covering_since}}` and
`evidence.finnhub: {enabled, pending, symbols, last_ok, last_error, reads}` (the Finnhub reader).

The research store `F:\Nova\catalysts\catalysts.sqlite3` (`NOVA_CATALYST_DIR`; `PRAGMA
user_version = 1`, unknown versions refuse; owner `research/catalysts/`, never read by the
backend) holds `targets (ticker, session_date, window_start, cutoff, window_end, origin)`,
`items (item_id "<source>:<id>", source edgar | alpaca | finnhub | massive, published_ts,
title, summary, url, publisher, n_tickers, form, sec_items, fetched_ts)`, `item_tickers`,
`checks (ticker, session_date, source, status ok | error | unavailable | out_of_range,
n_items, detail, checked_ts)` and `verdicts` per rules version. An `edgar` item's
`published_ts` is its EDGAR acceptance time with each bulk-JSON row read on its own clock: SEC
writes a `Z` on every `acceptanceDateTime`, but some filers' JSON holds Eastern wall time behind
it (`research/catalysts/edgar_clock.py`; ADR 024 amendment 2026-09-30). SEC's bulk
`submissions.zip` and `companyfacts.zip` are kept beside it under `edgar/`, Nasdaq's halt
pages under `halts/raw/`. Nasdaq's halt history (2021-10 on) is loaded into the leaderboard's
`halt_events` (source `nasdaq_trade_halt_rss`) by `research/catalysts/backfill_halts.py`, and
its checks and labelled items into the leaderboard's `catalyst_checks` / `catalyst_items` by
`research/catalysts/export_leaderboard.py` (#498), so Sim playback of a past day shows each
mover's verdict at the playhead ("Catalysts in playback" under Scanner leaderboard).

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
line with `schema_version` and `kind: "sample" | "client" | "stall" | "heap"` -- a
`sample` line aggregates `PERF_PERSIST_EVERY_SEC` (5) seconds (ops and gc
summed, `cpu_pct` averaged, `delay_max_ms` maxed, gauges last) -- and
`stalls/<id>.json`; both removed after `PERF_RETENTION_DAYS`. A reader skips
and counts a line of unknown `schema_version`, never guesses. `/api/diagnostics`
adds group `performance` (rows `perf_process_cpu`, `perf_ib_loop`,
`perf_http_loop`, `perf_stalls`, `perf_queues`, `perf_windows`,
`perf_handlers`; one `unknown` row while the recorder has no samples).

**The longest stalls keep their stacks (#619).** The hourly full-report cap keeps
the longest `PERF_STALL_FILES_PER_HOUR` stalls, rather than the first ones. A
strictly longer report replaces the shortest kept report; ties keep the earlier
report. Replaced files are removed by the writer, and live summaries' `file`
fields follow the retained set (null after eviction). Ordinary day summaries
remain. The cap is per report's start hour, with bounded current/previous-hour
bookkeeping; a late report outside that window is counted and declined. GC
thresholds, startup freezing and trading behavior are unchanged.

**L1 timestamp evidence (#667).** With the existing performance recorder on,
`perf/l1_timestamps.py` queues the L1 updates delivered to quote listeners and
price-setting AllLast facts; a bounded off-loop drain writes
`<perf>/l1_timestamps/YYYY-MM-DD.jsonl`. Each line is `{schema_version: 1,
kind: "l1_timestamp", symbol, instance, price, price_ts, arrival_ts,
last_timestamp, rt_time, seed, quote_quality, native_price_received,
timestamp_receipt: {tick_type: 45 | 88, stamp, received_at, with_price} | null,
tape_candidates: [{price, exchange_ts, arrival_ts, delta_sec}],
candidates_truncated}`. Native wrapper callbacks establish receipt: cached
`ticker.ticks` cannot say whether a string tick arrived. `with_price` means a
native last tick and timestamp receipt were in the same dispatch, never a seed.
Nearby same-price prints are candidates, not proof they are the same trade.
Correlation requires the same IB instance and recent arrival times; bounded
rings, queue, rate and per-day file size count omissions in perf gauges. Files
follow `PERF_RETENTION_DAYS` retention and unknown schema versions are refused
by readers. Missing receipt/correlation stays null/empty. Evidence never
changes trigger age, minute bucketing, warm-up protection or the sampled-L1
source; #667 still needs recorded-market diagnosis before those decisions.

**Heap census (#619).** A full (gen-2) garbage collection stops every thread
while it walks every tracked object. On 2026-09-29 the backend ran about one a
minute all day, and the median one took ~430 ms; only ~60 ms of that was
imported code. The census says what the rest is (owner `perf/heap.py`):

`GET /api/perf/heap` -> `{schema_version: 1, generated_at, elapsed_ms, tracked,
allocated_blocks, gc: {thresholds, counts, frozen, stats}, process:
{private_bytes, working_set_bytes, peak_working_set_bytes, page_faults},
types: [{type, count}], holders: [{name, kind, items, nested_items}], cached}`.

- **`tracked`** counts the objects the collector walks. `types` are the most
  common, at most `PERF_HEAP_TOP`. `allocated_blocks` is
  `sys.getallocatedblocks()`. After the freeze below, the frozen objects are
  not walked and not counted here; `gc.frozen` counts them.
- **`process`** is the OS's figures. A field is null where the platform does
  not report it: on Linux only the peak and the page faults.
- **`holders`** are the backend's biggest containers, each counted once:
  - its modules' globals;
  - the containers on module-level objects (a state singleton's dicts) and on
    its classes, named `module.name.attr`;
  - its `lru_cache`s (`kind: "lru_cache"`, `items` the cache's size).

  `nested_items` sums the containers one level down, and the containers on the
  objects there, reading at most `PERF_HEAP_SCAN_CAP` values.

Taking a census walks the heap too, so it pauses the process about as long as
one full collection. Two things limit it:
- The route answers the last census (`cached: true`) while it is younger than
  `PERF_HEAP_MIN_GAP_SEC`.
- The recorder takes one `PERF_HEAP_FIRST_AFTER_SEC` after it starts, then every
  `PERF_HEAP_EVERY_SEC`, never in `PERF_HEAP_QUIET_ET` (09:25-09:45) on a
  weekday.

Every census taken, scheduled or asked for, is written to the day file as `kind: "heap"`.

**GC policy (#619, owner `gc_policy/`).** The first census on the live backend (2026-09-29,
minutes after a start) found 732,138 tracked objects in 7,037 modules; the objects were mostly
code, classes and module state. 1,434 of those modules were torch and transformers, imported by
the FinBERT warm-up, which failed on every start on the desk.
- **FinBERT is off** unless `NOVA_NEWS_SENTIMENT=1`; its label reads `unavailable`, as it
  already did.
- **The heap is frozen once.** `GC_FREEZE_AFTER_SEC` after start, the backend collects what is
  garbage and freezes everything still alive (`gc.freeze()`), so full collections walk only what
  was created since. A frozen object is still freed when nothing refers to it; one that later
  dies in a reference cycle is never reclaimed. That leak is bounded, since the freeze runs once
  per process. `NOVA_GC_FREEZE=0` turns it off.

### The operator's focus and the book watcher (ADR 033, operator ask 2026-09-24)

Sensors for agents and bots: ask the endpoint, never guess. Both are in the
sensor catalogue (`GET /sensors`: 19 `focus`, 20 `book-pulls`) and answer the
sensor envelope `{sensor, status: "live", as_of, data, symbol?, error?}`.

**Focus.** Every desk window posts `POST /sensors/focus` (owner
`sensors/focus_routes.py`; at most `FOCUS_REPORT_MAX_BODY_BYTES`, 413 over,
422 invalid) on each change and every `FOCUS_HEARTBEAT_MS`: `{schema_version:
1, role: "main" | "popout" | "browser", window_id, instance_id, focused,
visible, page: "trader" | "desk" | "scanner" | "account" | "bots" | "records" |
"cryptos" | null, tab: string | null, symbol: string | null, symbol_source: "trader_tab" |
"desk_board" | "scanner_row" | null, trader_tabs: string[], last_input_ts:
number | null, reason: "start" | "focus" | "blur" | "visibility" | "page" |
"symbol" | "input" | "heartbeat", ui_tag}` -- `window_id` is the perf
recorder's (`main`, `trader:SYM`), `instance_id` one per page load,
`focused` `document.hasFocus()`, `tab` the scanner tab on the Scanner page,
`last_input_ts` the last click / keypress / wheel there (epoch seconds). The
Electron main process posts `{schema_version: 1, role: "electron", window_id:
"electron-main", app_focused, focused_window_id: string | null, windows:
[{window_id, focused, visible, minimized, display: {id, label, index, count,
primary, scale_factor} | null}], reason}` (monitors numbered left to right
from 1; reason also `display`). The sample desk sends nothing. `GET
/sensors/focus` -> `data: {schema_version: 1, nova_in_front: boolean | null,
focus_source: "electron" | "window" | null, symbol, page, tab, symbol_source,
window_id, role, display, since, last_input_ts, last_input_age_sec, windows:
[{window_id, instance_id, role, focused, visible, minimized, page, tab, symbol,
symbol_source, trader_tabs, display, last_input_ts, ui_tag, reported_ts,
age_sec}], recent: [{ts, window_id, page, tab, symbol, focused, reason}]
(newest first, at most `FOCUS_RECENT_KEEP`), venue, live_edge, note}` -- the
window Windows has in front (Electron's word first, else the window's own),
else, with Nova behind another app (`nova_in_front: false`), the window last in
front; `since` is when that window last changed page or symbol. A report older
than `FOCUS_STALE_SEC` is ignored; with none, the answer is null with `error`.
In memory only (`sensors/focus_store.py`), never persisted. Where the
operator's eyes are cannot be known; the last input is the stated stand-in.

**The book watcher** (`backend/book_watch/`). The live IBKR depth handler and
AllLast handler only enqueue (ADR 010); one thread follows every held depth
line with its tape. Each book is summed per price across venues; only prices
wholly in view in two consecutive books are compared (with every row in use the
worst visible price may be cut off, and a price that scrolled out of view is
unknown, never pulled; a side that collapses at once, an L1-only book and IBKR's
book reset are not judged). A drop in size is judged `BOOK_WATCH_SETTLE_SEC`
later: lit prints at exactly that price inside `BOOK_WATCH_MATCH_SLACK_SEC` of
the two books are **filled** (each print claimed once; FINRA and midpoint
prints never fill; the window is `book_watch/matching.py`'s, measured below; a
level a print traded through first takes that print's own, #636 below), the
rest **pulled**. A pull is **large** at `BOOK_WATCH_LARGE_MIN_SHARES` and
`BOOK_WATCH_LARGE_MEDIAN_MULT` x the side's median level. A large pull event is
`{event: "pull", symbol, ts, side: "bid" | "ask", price, pulled, filled,
level_before, level_after, median_level, distance_ticks,
distance_at_post_ticks, lifetime_sec, approached, opposite_volume}` (unknowns
`null`: a level there before the watcher's first book has no post time). A flag
is `{event: "flag", id: "<ts_ms>-<SYMBOL>-<kind>", kind: "pulled_on_approach" |
"repeated_pulls", symbol, ts, side, price | null, shares, why, evidence}` --
`pulled_on_approach`: a large pull after the side's best came toward it
(posted `distance_at_post_ticks` >= 1 away, pulled closer); `repeated_pulls`:
`BOOK_WATCH_REPEAT_COUNT` large pulls on one side inside
`BOOK_WATCH_REPEAT_WINDOW_SEC` (evidence `{count, window_sec, pulls: [{ts,
price, pulled}]}`, once per side per window). Hints consistent with spoofing,
never a detection: on a busy premarket name they are frequent (PFSA
2026-09-24: 299 in 93 minutes), so read them as a description of the book, not
an alarm. `GET /sensors/book-pulls?symbol=` -> `data: {schema_version: 1,
source: "ibkr_depth", watching, since, feed: {books, prints, books_per_sec,
median_gap_ms, last_book_age_ms, window_sec}, window_sec, pulled_shares,
filled_shares, pulls, fills, large_pulls, sides: {bid | ask: {pulled_shares,
filled_shares, large_pulls}}, flags[], pulls_recent[] (newest first, at most
`BOOK_WATCH_READ_LIMIT`), caveats[], note}` over the last
`BOOK_WATCH_STATS_WINDOW_SEC`; a symbol without a depth line answers
`watching: false` with the reason. `GET
/sensors/book-pulls/events?since=<epoch>&symbol=` -> `{schema_version, now,
since, flags[] (oldest first), watcher: {enabled, symbols, queue_depth, queued,
dropped, processed, errors, journal}, note}` -- a poller's feed. The L2
sensor's `spoof_hints` are the watcher's newest large pulls `{side, price,
from_size, pulled, filled, ts}`, and its replenish / cancel counts sum venue
rows per price. The journal (`book_watch/journal.py`):
`<dir>/YYYY-MM-DD.jsonl` (`NOVA_BOOK_WATCH_DIR`, else `F:\Nova\book_watch`
when F: is mounted, else `<cache>/book_watch`), one line per flag, large pull,
large drop and symbol-minute `{schema_version: 1, wall_ts, event: "minute", symbol,
minute_ts, books, prints, pulled_shares, filled_shares, pulls, fills,
large_pulls, flags}`; nothing prunes it. `NOVA_BOOK_WATCH=0` stops the
watcher, `NOVA_BOOK_WATCH_JOURNAL=0` its journal. `py -3
tools/book_watch_replay.py <recording dir>` runs the same detector over a
Session Record.

**What left the book, on the ladder** (ADR 033 amendment, operator ask
2026-09-29: "I see massive orders in level 2, and I just think they're
disappearing. I don't see them on time and sales"). The detector also judges
every **large drop** -- the size that left a price, traded or not, by the same
size rule applied to the drop -- as `{event: "drop", symbol, ts, side, price,
dropped, pulled, filled, outcome: "pulled" | "traded" (pulled over filled),
level_before, level_after, median_level, distance_ticks,
distance_at_post_ticks, lifetime_sec, approached, large_pull, on_approach}`
(`on_approach`: the `pulled_on_approach` flag's own rule); the journal keeps
them. `/ws/ibkr/depth/{symbol}` carries, beside its books, `{"type":
"book_watch", symbol, data: {schema_version: 1, now, reset, seq, watching,
reason: string | null, window_sec, sides | null, drops[] (each with its `seq`),
note}}` (owner `book_watch/ladder.py`), asked at most every
`BOOK_WATCH_PUSH_SEC`: a socket's first frame (`reset: true`) holds the large
drops of the last `BOOK_WATCH_LADDER_MEMORY_SEC`, later frames only those
judged since, and `sides` rides on each (refreshed on its own at most every
`BOOK_WATCH_SIDES_PUSH_SEC`). While the ladder shows no live line (a replay
desk) or the watcher is off, one `watching: false` frame gives the `reason`,
then nothing; the desk ignores an unknown `schema_version`. The ladder
(`ibkr/bookWatch.ts`, pure, and `ibkr/BookWatchParts.tsx`) marks each large drop
of the last `L2_PULL_MARK_SHOW_MS` (6 s, fading over the last 2) where its price
sits between the rows -- "✕ 2,000 pulled" in amber (solid when it was pulled as
the price came closer), "✓ 8,200 traded" in slate; drops between the same two
rows share one mark per verdict, and a price above the book is marked over the
column head. It hatches every row at a price with a large pull in the last
minute (the count and times on hover), and puts each side's `✕ pulled ✓ traded`
for the watcher's minute above its column, amber when pulled is over 3x traded
and at least 1,000 shares. Nothing is drawn over a size or a price, no row is
added, and Time & Sales still shows prints only. Every mark's hover ends "a hint
consistent with spoofing, never a detection". The reading's `pulls` count read
`null` until then (the recent-pulls list overwrote it; the Tape tile showed
"None pulls").

**Hidden sellers and buyers** (ADR 033 amendment, operator ask 2026-09-30: "do we have a way to detect
hidden sellers? like we have spoofing!?", then mockup v1 and "1 go"). The mirror of a pull: size that
traded at a price that held beyond the most the book ever showed there (owner `book_watch/hidden.py`,
pure). Per side the watcher follows one **stretch**, the price that side's counted prints keep landing
at -- lit prints at or through its best price, odd lots included, and prints at that price after the
size shown there is gone -- while a book younger than `BOOK_WATCH_IDLE_SEC` stands (a Session Record can
keep the tape after its depth line is gone); a cross print (`BOOK_WATCH_AUCTION_CONDITIONS`), a
volume-only print, a FINRA report and a midpoint print never count. The stretch weighs what printed
there against the most the book showed there from `BOOK_WATCH_HIDDEN_SHOWN_BEFORE_SEC` before its
first print. It is a **hidden seller** (the ask) or **hidden buyer** (the bid) once its price has held
`BOOK_WATCH_HIDDEN_MIN_HOLD_SEC` (10) since its first print, at least `BOOK_WATCH_HIDDEN_MIN_SHARES`
(2,000) printed there and at least `BOOK_WATCH_HIDDEN_SHOWN_MULT` (3) x the most shown; a stretch the
book could not follow (a collapsed side, its price cut off, a reset) never is. It speaks as a detector
event `{event: "hidden", id: "<started_ms>-<SYMBOL>-<side>-<price>", kind: "hidden_seller" |
"hidden_buyer", symbol, ts, side: "ask" | "bid", price, state: "holding" | "broke" | "faded" | "moved" |
"auction" | "reset", hidden (printed beyond shown_max), printed, shown_max, shown_now: number | null,
prints, refills, started_ts, last_print_ts, flagged_ts, ended_ts: number | null}` when flagged, as it
grows (at most every `BOOK_WATCH_HIDDEN_UPDATE_SEC`) and once when it ends (`broke`: a print went
through it; `faded`: no print there for `BOOK_WATCH_HIDDEN_GAP_SEC`; `moved`: the offer came down or
the bid went up); the journal keeps each. The readings' `sides.{bid,ask}` add `hidden_shares` (the
hidden size at the side's flagged prices, holding or ended in the stats window) and the reading a total
`hidden_shares`. `GET /sensors/book-pulls` adds `hidden_recent[]` (the newest word on each stretch,
newest first, at most `BOOK_WATCH_READ_LIMIT`) and `hidden_note`; `/sensors/book-pulls/events` adds
`hidden[]` (the newest word on each stretch sent after `since`, oldest first). The depth socket's
`book_watch` frames add `hidden[]` (each word with its `seq`; a `reset` frame carries each stretch's
last word while it holds or was heard in `BOOK_WATCH_LADDER_MEMORY_SEC`) and `hidden_seq`.
`/sensors/flow`'s `iceberg_hint` is the watcher's word: `true` when it flagged one in the last minute,
`false` when it follows the line and flagged none, `null` without a depth line, and `hidden: {stretches,
window_sec, note} | null` beside it -- it used to be true whenever any level grew while anything
printed. The stock read's tape group adds the row `hidden` ("Hidden size": `warn` while a hidden seller
holds at the offer, `info` otherwise) and the Tape tile reads "Hidden seller" then. On the ladder
(`ibkr/bookWatchHidden.ts`, pure) the row a hidden seller or buyer holds at is outlined in violet and
its mark sits under it ("◆ 12.4K hidden"; after it ends, "· broke" / "· held" and so on, fading like a
pull mark); each side's minute line adds "◆"; a word the watcher has not refreshed for
`L2_HIDDEN_STALE_MS` is not drawn. Every hover gives what traded against what showed, how it stands and
what `tools/hidden_study.py` found, and ends "never a detection". One reserve (iceberg) order and several
orders refilling a price look the same here. The setup scanner's tape gate keeps its own hidden-seller
veto; nothing here gates, stages or places.

`tools/hidden_study.py` (read-only; owner `book_watch/hidden_study.py`) runs the same tracker over every
Session Record and answers `{schema_version: 1, rule: {min_shares, shown_mult, min_hold_sec},
horizons_sec: [10, 30, 60, 300], recordings: [{date, symbol, books, prints, depth_hours, stretches}],
depth_hours, groups: {flagged_ask | busy_ask | flagged_bid | busy_bid: {n, per_hour, horizons: {H:
{measured, broke_pct, beyond_pct, toward_bp: {n, mean, median, t}}}}}, by_day: {DATE: groups}, events[],
grid?}` -- `flagged`: the moment the rule held; `busy`: a stretch where as much printed at a price that
held while the book showed enough to explain it; `broke_pct`: a counted print went through the price by
then; `beyond_pct`: the mid past the price then; `toward_bp`: the mid's move toward the break (up for
an offer, down for a bid). A horizon past its recorded stretch is not measured. On the Session Records
of 2026-09-21..29 (26 hours with a book), a minute after a hidden seller the mid was past the offer 37%
of the time against 46% after a busy offer (104 against 66); a hidden buyer made no such difference.

**The matching window, measured** (ADR 033 amendment 2026-09-30; asked after the hidden-seller study:
the lit size at the quote that no drop claimed often had a pulled drop at its price nearby, so does the
window call fills "pulled"? "Change it only if the evidence is clear"). The detector takes the window
as a parameter, `MatchParams(before_sec, after_sec, settle_sec, sweep_hold_sec)` (owner
`book_watch/matching.py`; `settle_sec` must exceed `after_sec`, and a swept level's prints must still be
kept when its drop is judged), and an optional `judged` list that collects every judged drop with the
prints it claimed; the live watcher runs the defaults and collects nothing. A lit print fills only a
level at exactly its price (price keys, `matching.PRICE_EPS`): the old half-tick test let
floating-point error match a midpoint print to the level below it. `tools/book_watch_window_study.py`
(read-only; owners `book_watch/window_study.py` and `book_watch/sweep_study.py`) runs the detector over
every Session Record up to yesterday (`--until`; today's may still be recording), cross prints and
prints with no book within `BOOK_WATCH_IDLE_SEC` left out, and answers `{schema_version: 1,
windows_sec: [0.5, 1, 2, 3], extensions_sec: [1, 2, 3], shift_sec: [30, 60], seeds: [1, 2],
sweep_hold_sec, recordings: [{date, symbol, books, books_per_sec, prints, left_out: {cross, tape_only},
sweep, extension, evidence, depth_late, sweep_rule}], by_day: {DATE: {sweep, extension, evidence,
depth_late, sweep_rule}}, total}`:
- `sweep: {"0.5" | "1" | "2" | "3": {dropped, filled, pulled, large_pulls, flags: {pulled_on_approach,
  repeated_pulls}, large_drops, large_traded}}` -- the detector with that window either side of a
  drop's two books, judged 0.25 s after it closes (shares and counts), with the sweep rule on.
- `extension: {pulled, before | after: {"1" | "2" | "3": {real, moved_real, moved, tick_out}}}` --
  shares a window reaching that far before the earlier book (the print early: the book trailing the
  tape) or after the later one (the print late) would fill beyond the 0.5 s window, of the `pulled`
  shares: `real` from the prints no drop claimed; `moved_real` / `moved` from those a move of 30-60 s
  could place with their price in the same place against the quote, at their own time / moved (mean
  of the seeds); `tick_out` from all of them one tick away from the inside. A moved print first meets
  the drop's own 0.5 s window, as an unclaimed print had. Real less moved is what the window misses.
- `evidence: {real | moved: {volume, print_late_0.5_3, print_early_0.5_1, print_early_1_3}}` -- the
  unclaimed lit size at the best bid or ask, and how much of it had a pulled drop at its price shown
  0.5-3 s before it or 0.5-1 s / 1-3 s after it; real and moved are the same prints.
- `depth_late: {through, "<=0.5", "0.5-1", "1-3", "3-10", never, grew_first}` -- lit prints through the
  displayed best price (that level at least 100 shares), by when a book showed that level smaller or
  gone; `grew_first` counts those not shown smaller within 0.5 s whose level the book showed larger
  first (new size posted there: a refill, not the book trailing its tape).
- `sweep_rule: {sweeps, levels, pulled_off, off, on, covered: {drops, dropped, filled_off, filled_on},
  reach: {real, matched_real, moved, beyond}}` -- the sweep rule below: the sweeps and the levels they
  took; the detector at 0.5 s without the rule (`off`; its drops left `pulled_off` shares pulled) and
  with it (`on`), each shaped like a `sweep` entry; the drops the rule let take a sweep's prints
  (`covered`: their size, and what read filled without and with the rule); and the size the rule adds
  to what the detector fills (`reach`), always the detector itself: `real` with the sweeps it finds;
  `matched_real` / `moved` with its own sweeps off and given the sweeps that a move of 30-60 s could
  place at a moment their best price stood as the best again, at their own moments / moved (mean of
  the seeds); `beyond` given the level one tick past where each sweep stopped, at its own moments. Real
  less moved (or beyond) is what the rule recovers; moved and beyond are chance.

On the 27 recordings of 2026-09-21..29 the window stays 0.5 s: moved prints had a pulled drop 0.5-3 s
before them as often as the real ones (45.3% against 44.9%); 87.9% of 339,550 through-prints saw the
book show their level gone within 0.5 s and 10.2% took 0.5-3 s; and reaching 1 s before the earlier
book would fill 2.3% of the 82.0M shares called pulled, only 0.5-0.6 points beyond chance (3 s: 7.8%,
1.3-2.2 beyond; 1 s after the later book: 2.0%, 0.2-0.3 beyond).

**A level a print traded through reads traded** (ADR 033 amendment 2026-09-30, #636; the operator: "1
go"). A lit, price-setting print above the book's best ask (below its best bid) proves the size the book
showed at the round-lot levels from the best to its own price traded: a protected quote cannot be
traded through. `matching.Sweeps` keeps that size owed per level. For `BOOK_WATCH_SWEEP_HOLD_SEC` (3 s)
after the sweep, a drop at one of those levels first takes the sweep's own prints -- lit prints at its
exact price within 0.5 s of the sweep -- at most the size still owed, and then its own window; each
drop the book shows there pays the owed size down. New size posted at the level, or the level leaving
the view, ends it: a later drop there may be the new order, pulled, and the sweep's leftover prints (a
hidden order, a refill that traded) are not its own. A level pulled before the sweep reached it has no
print there and still reads pulled. An odd lot, a cross, a volume-only or an off-exchange print proves
nothing (`BOOK_WATCH_SWEEP_SKIP_CONDITIONS`), nor does a print through an odd-lot best
(`BOOK_WATCH_SWEEP_MIN_LEVEL`) or a book older than `BOOK_WATCH_IDLE_SEC`; a book reset forgets every
sweep. On the same 27 recordings: 9,695 sweeps; the drops the rule covers read 86.2% traded without
it and 88.7% with it; it adds 0.37% of the size called pulled (299,598 shares), 98% of it beyond chance
against the level a tick past each sweep and 76% against the same sweeps moved 30-60 s -- on the
recordings that kept every book IBKR sent (2026-09-25 and -29), 0.14%, 91% and 49%; large pulls 11,121 ->
11,071, flags 3,190 -> 3,176. A first build without the owed size or the end on new size added 1.6%, and
84% of what it relabeled on six busy recordings sat at levels refilled after the sweep: its chance tests
passed, because the prints were real and next to a real sweep and only the drop they filled was wrong.
Of the 12.1% of through-prints not shown smaller within 0.5 s, 4.2 points had new size posted at the
level first (`grew_first`); 7.8% sat in the book untouched until it showed them smaller. The window
stays 0.5 s: with the rule on, reaching 1 s before the earlier book still adds 2.0%, 0.3-0.4 points
beyond chance.

### LULD bands on Level 2 (ADR 047, operator ask 2026-10-06)

"do we have LULD levels?", then, beside DAS screenshots of red `LULD` rows at each band: "1 go.. make it obvious".
IBKR passes on the halt but no band, so Nova computes each stock's limit up / limit down from the published LULD
Plan rules (owner `backend/luld/`). Read-only: nothing places, stages, gates or cancels an order on it.

- **The rules** (`luld/rules.py`, `luld/tracker.py`, pure):
  - The percentage comes from the previous close (IBKR's tick 9), fixed for the day. Over $3.00 it is 5% (Tier 1)
    or 10% (Tier 2); from $0.75 to $3.00, 20%; under $0.75, the lesser of $0.15 or 75%. It doubles 15:35-16:00 for
    Tier 1 and for Tier 2 at or under $3.00.
  - Bands round to the penny, half up. There are none outside 09:30-16:00 ET.
  - The first reference is the listing exchange's opening print (condition `O`, from any venue but a trade-report
    facility). For five minutes the mean of the trades since it follows; after that, the arithmetic mean of the
    eligible (price-setting) trades of the preceding five minutes. A new mean replaces the reference only when it is
    1% or more away and the old one has stood 30 s. Five minutes without a trade keep it.
  - A limit state (the NBO on the lower band, or the NBB on the upper, not crossed) holds the reference; 15 s in it
    is a pause due. A halt shows no band; the reopening print (`5`) is the next reference.
  - Measured against the SIP's own band flags (the Massive NBBO indicators), a limit state's end makes no reference
    of its own. The Plan's text says it does; keeping the reference matched 81% exactly, against 64%.
- **Exact or approximate.** `exact` when Nova saw the stock open or reopen with its tape unbroken since.
  - Otherwise a band appears after five minutes of tape, seeded from the mean: `exact: false`, with `spread` (how
    far it may sit from the exchanges', in dollars). An approximate band never claims a limit state.
  - A lost tape line or an IBKR feed gap makes an exact band approximate until the next reopen.
  - The tier: a company of at least $15B is Tier 1 and one of at most $2B Tier 2 (sure). Between them, the side of
    $4.5B; with no size known, Tier 2. Both read `tier_sure: false` and show `≈`.
- **The live worker** (`luld/live.py`). The AllLast and Level 1 handlers only enqueue (ADR 010). One thread keeps a
  tracker for every stock whose tape line Nova holds, from its first live print until 30 minutes without one. Every
  0.25 s it reads the halt state (`halt_status.halted_now`), the line (`tape_stream.is_subscribed`) and feed gaps
  (`feed_pulse`). In memory only; `NOVA_LULD=0` turns it off.
- **The replay** (`luld/replay.py`). On a Sim desk off the live edge with a Session Record loaded: the bands at the
  playhead, from the recording's prints, book tops and the day's halt log, never ahead of the playhead. It runs on
  its own thread, with a checkpoint every 5 minutes of replay.
- **The view** (`luld/views.py`) is one shape for `GET /api/luld/{symbol}` and the depth socket's `{"type": "luld",
  "symbol", "data": view}` frames (sent on change, and at least every 5 s): `{schema_version: 1, symbol, source:
  "live" | "replay", state: "off" | "unknown" | "warming" | "bands" | "limit" | "pause_due" | "paused", exact, lower,
  upper, reference, reference_since, reference_source: "open" | "reopen" | "mean" | "open_mean" | "seeded" |
  "first_trade_after_halt" | "limit_exit" | null, reference_words, percent, prev_close, tier: 1 | 2 | null,
  tier_text, tier_sure, spread, limit: {side: "down" | "up", since, band, pause_at, overdue} | null, straddle: "down"
  | "up" | null, anchor: {kind, ts, price} | null, halted_since, watching_since, warm_until, gap: {ts, reason} |
  null, last, distance: {down_pct, up_pct} | null, near: "down" | "up" | null, reason, history: [{ts, reference,
  source}], note, rules, track, as_of, text, watching?}`.
  - `lower` / `upper` are null unless `state` is `bands`, `limit` or `pause_due`. `near` means within 2% of the
    price or 5 cents. `track` is the measured record (`luld/track_record.py`).
  - `GET /api/luld` lists the stocks the live worker follows. The stock read's halts row `luld` reads the view.
- **On the desk** (`frontend/src/ibkr/luld.ts`, `LuldStrip.tsx`, `luld.css`):
  - The Level 2 ladder draws the lower band in the bid column and the upper in the ask column: a bold rose line and
    a `LULD 4.40` tag where the price sits among the rows, or under the last row (`↓`) when deeper. It pulses while
    the price is near or on it.
  - A 15 px strip above the book reads `LULD ▼ 4.40 −18.6% | ▲ 6.60 +22.0%`, the side amber when near. In a limit
    state it reads `LIMIT DOWN 4.40 · PAUSE IN 9s` in red, the 15 s counting down. Outside 09:30-16:00 it is gone.
  - `≈` marks an approximate band or an assumed tier. Every piece's hover says it is Nova's calculation, how it
    knows, and the measured record.
- **Measured** (`tools/luld_check.py`): `massive` replays the Massive flat files' trades and NBBO and compares with
  the SIP's own flagged bands; `records` checks Nova's Session Records against the price the quote sat at for the
  15 s before each logged pause.

### The trading screen is always recorded (ADR 035, operator decision 2026-09-24)

"I always, always, always want the screen that I'm trading to be recorded.
Everything ... That's definitely not negotiable." The desktop app's main
process records every monitor from launch to quit (owner
`frontend/electron/screenRecorder.mjs`; plan `screenRecordPlan.mjs`, files
`screenRecordFiles.mjs`, a hidden recorder page `screenRecorder.html`). There
is no off switch: no button, setting or variable stops it;
`NOVA_SCREEN_RECORD_DIR` only moves the folder. The browser desk cannot record
the screen and says so.

**Files.** `<dir>/<YYYY-MM-DD>/<HHMMSS>-screen<N>.mkv` -- the Eastern date and
start time, monitors numbered left to right from 1 (`.webm` when Chromium has
no H.264 encoder) -- a new file per monitor on every quarter hour, started
before the old one stops. `<dir>` is `NOVA_SCREEN_RECORD_DIR`, else
`F:\Nova\screen` while F: is mounted, else `<userData>\screen` (the view says
`dir_source: "fallback"` and why). Beside them `segments.jsonl`, one JSON
object per line: `{schema_version: 1, event: "start", segment_id, file,
display: {id, index, count, label, primary, scale_factor, bounds}, width,
height, fps, bps, mime, started_ts}` and `{schema_version: 1, event: "end",
segment_id, file, ended_ts, bytes, reason: "rotation" | "quit" |
"display_change" | "stall" | "error" | "suspend" | "recorder_gone", error}`
(epoch seconds). A start with no end is a file cut short by a crash or power
loss; it plays up to its last write. Nothing deletes a recording (operator
decision 2026-09-24: "Keep every screen recording until I say otherwise; just
warn me when F: gets low" -- the drive guard below is that warning).

**The view** (one shape for every reader: the desk over IPC
`nova:screen-record:view` / `nova:screen-record:subscribe`, read-only, and
`POST /api/screen-record` every `SCREEN_RECORD_REPORT_SEC` and on each state
change): `{schema_version: 1, state: "starting" | "recording" | "partial" |
"failed" | "suspended" | "stopped", recording: boolean (every monitor), since:
number | null, error: string | null, dir, dir_source: "env" | "data_drive" |
"fallback", dir_note, dir_error, mime, fps, segment_min, displays: [{index,
count, id, label, primary, scale_factor, width, height, recording, since, file,
bytes, last_data_ts, error, retry_at}], unmatched: [{index, id, label}],
disk: {free_bytes, state: "ok" | "warn" | "fail" | "unknown", error,
checked_ts}, problems: [{at, display_index, reason, detail, resumed_at}]
(newest first, at most 10), restarts, generated_at}`. A monitor that fails,
stalls (no data for 12 s) or ends by itself is started again after 2, 5, 10,
30 s, then every 60 s, forever; a crashed recorder page is replaced; each loss
is a `problems` row until it is back.

`GET /api/screen-record` (owner `backend/screen_record/`, in memory, never
persisted) answers `{schema_version: 1, reported, fresh, age_sec, received_ts,
report: view | null}`; `fresh` is a report younger than
`SCREEN_RECORD_STALE_SEC` (35). `POST` refuses an unknown `schema_version`,
`state` or `dir_source` (422) and a body over 64 KB (413). `/api/diagnostics`
adds the `screen_recorder` row (group `recorder`): `fail` with no desktop app
reporting, a stale report, or any monitor not recording; `warn` while starting
or recording to the system drive; `off` while the PC sleeps; and the
leaderboard's drive guard (warn under 50 GB free, fail under 10 GB, only ever
worse). The header chip (`frontend/src/screen_record/`) is a monitor icon with a
red dot while every monitor records and a red "Screen not recording" the moment
one does not.

### The desk draws with the graphics card (operator decision 2026-10-05, #707)

"Especially when I move the chart left and right with my mouse and hold ... it really feels laggy." The desktop
app drew in software on Windows from the 2026-09-17 black-window fix, which changed three things at once and
never tested the graphics card alone. Dragging the 1-minute chart in Electron 41 on the demo desk (4K at 150%):
about 22 fps in software (frames 40-55 ms at the median, 38-56 ms of main-thread work), and frames of 5 ms at the
median with about 5 ms of work with the graphics card. It draws with the graphics card by default now, with a
safety net (owner `frontend/electron/graphics*.mjs`, wired by `gpuPolicy.mjs` and `graphics.mjs`):

- **The choice** is `graphics.json` in the app's userData: `{schema_version: 1, gpu: "on" | "off", reason:
  "operator" | "gpu_crashed" | "blank_window", at: number | null, detail: string | null, told: boolean}` (`at`
  epoch seconds; `told` once the operator was told why it is off). No file: the graphics card. A file of
  another version, or one Nova cannot read: software, said in the log. `NOVA_ELECTRON_GPU` (1 / 0) wins over
  the file. Occlusion tracking stays off on Windows either way.
- **View > Draw with the graphics card** (native menu, so it works over a blank page) shows the mode and
  switches it after a confirm, which restarts Nova; a note under it says why the safety net turned it off.
- **The graphics process ends abnormally** (`child-process-gone`, type `GPU`, not a clean exit or a kill):
  Chromium starts it again and Nova keeps running; the next start draws in software, and the operator is
  told at once.
- **The window goes blank**: every 5 s, while a desk window is focused, loaded 20 s, not minimised and the
  operator gave input within 15 s, the screen under it is read from the trading screen recording's own
  capture of that monitor (a `sample` command to the recorder page: a 96x54 picture, 75-290 ms; asking
  Windows for a screen picture took 0.9-1.6 s a call). A picture is blank when 97% of it sits within 6 levels
  of its median colour (healthy Trader pages measured 8-18%, a Scanner page 55%, whole monitors 53-81%). Only
  then is the page itself read (`capturePage`); a page as flat as that (over 90%, loading) decides nothing.
  The first blank look asks the window to draw again; three in a row store `blank_window` and restart Nova
  in software, which tells the operator once after it starts. Any look that decides nothing starts over.

### Share clips (ADR 039, operator ask 2026-09-29)

"I want to be able to record videos. Can I have maybe a small red button ... to share with the world?"
Owners: `frontend/electron/clip*.mjs` (the main process: marks, High quality, exports),
`frontend/src/clips/` (the desk), `backend/clips/` (the view for agents and the checklist). Nothing
here places, stages or cancels an order, and nothing deletes a screen recording (ADR 035).

**A clip is marks** on the always-on screen recording: the red ● on every Trader tab strip (and the
symbol menu, and two Nova Actions) opens and closes it; while it is open the main process marks where
its Trader tab is and whether it shows. It has no cap and no time limit, costs nothing while it runs,
and survives a restart: the next start marks the gap (`restart`) and goes on. **Save the last 5 min**
makes a closed clip from the tab's last `CLIP_LAST_N_SEC` (the main process keeps
`CLIP_TAB_HISTORY_SEC` of where each tab was, in memory); a tab that was not on screen then is
refused. A clip opened by hand starts with the same memory written as marks before its start, so the
export can begin up to `CLIP_TAB_HISTORY_SEC` earlier. Nova knows only what it marked: before a
clip's first mark and after it stopped, where the tab was is **not known** (never taken to be shown).
**High quality** adds a 30 fps capture of the tab's window (`desktopCapturer` window source)
in its own hidden page (`clipRecorder.html`), apart from ADR 035's: at most `CLIP_HQ_MAX_CONCURRENT`
(2) at once, each stopped at `CLIP_HQ_MAX_SEC` (30 min; the chip counts down the last minute), after
which the clip goes on as a cut. A capture that fails, stalls or ends by itself is started again with
back-off; after a restart it does not start again by itself. When the screen recording is not seeing
the tab's monitor a new clip records in high quality (else it is refused `CLIP_NO_PICTURE`).

**Files.** `<dir>` = `NOVA_CLIPS_DIR`, else `F:\Nova\clips` while F: is mounted, else
`<userData>\clips` (the view says `dir_source: "fallback"`). `<dir>/clips.jsonl`, one JSON object
per line, `schema_version: 1`, `ts` (epoch seconds) and `event`:
- `open` `{clip_id, started_ts, symbol, origin: "button" | "symbol_menu" | "hotkey" | "last_n",
  picture: "trader_tab", hq: boolean}`; `close` `{clip_id, ended_ts, reason: "operator"}` (a quit
  never closes one); `beat` `{clip_ids}` once a minute while any is open.
- `set` `{clip_id, hq: boolean, reason: "operator" | "limit" | "restart" | "clip_closed"}`.
- `mark` `{clip_id, kind, detail}`: `shown` `{window_id}`; `hidden` `{reason: "symbol" |
  "minimized" | "page" | "document" | "closed" | "not_open", showing: string | null}`; `geometry`
  `{window_id, display_id, content: {x, y, width, height}, inner: {w, h}, pane: {x, y, w, h},
  panels: {charts | level2 | tape | quote | plan | ticket | orders: {x, y, w, h}}}` -- `content` is
  the window's page on the screen in DIP, the rest the page's CSS pixels; `restart` `{down_since}`.
- `hq` `{clip_id, state: "start" | "end", file, window_id, reason: "operator" | "limit" | "error" |
  "window" | "restart" | "quit" | "clip_closed", error}` -- `file` relative to `<dir>`
  (`hq/<date>/<HHMMSS>-<SYMBOL>-hq.mkv`); the frame size is read from each decoded frame, never
  written here.
- `export` `{clip_id, export_id, state: "queued" | "running" | "done" | "failed" | "cancelled",
  file (`<date>/<SYMBOL>-<HHMMSS>.mp4`, relative), bytes, error, settings: {start_ts, end_ts,
  picture: "trader_tab" | "panels" | "window" | "monitor", panels, blur, cut_hidden, counts, out}}`.
- `delete` `{clip_id, files}` -- the clip's own exports and high-quality files only.

A row of another version, an unknown event or an unknown clip is counted and left out, never guessed.
Dates and times in names are Eastern.

**The view** (one shape for every reader: the desk over IPC `nova:clips:view` / `nova:clips:subscribe`,
and `POST /api/clips` every `CLIP_REPORT_MS` and on each change): `{schema_version: 1, generated_at,
dir, dir_source: "env" | "data_drive" | "fallback", dir_note, dir_error, skipped, hq_max, hq_in_use,
hq_max_sec, hq_warn_sec, last_n_sec, open: [{clip_id, symbol, started_ts, state: "ok" | "hidden" |
"hq_lost" | "no_picture", reason, showing, window_id, screen_recording: boolean | null, hq: {since,
ends_at, recording, lost, error, retry_at} | null}], clips: [{clip_id, symbol, origin, picture,
started_ts, ended_ts, length_sec, status: "recording" | "not_exported" | "queued" | "exporting" |
"ready" | "failed" | "cancelled", hq_sec, hidden_sec, gap_sec, export: {export_id, state, file,
bytes, error, note, progress, picture, blur} | null}] (newest first, at most `CLIP_VIEW_MAX`; the
backend keeps 50), exporting: {export_id, clip_id, done_sec, duration} | null, queued, tabs:
[{window_id, symbol, visible, display_id, screen_recording}], disk: {free_bytes, state, error}}`.

**The tab report** (every desk window, `nova:clips:tab`, on each change and every
`CLIP_TAB_REPORT_MS`; `frontend/src/clips/clipTabReport.ts`): `{schema_version: 1, window_id,
visible, reason: "page" | "document" | "draft" | null, symbol, pane: {x, y, w, h} | null, panels,
inner: {w, h}}` -- the active Trader tab's pane (`sv-tab-pane-<SYMBOL>`) and its panels by
data-testid, in CSS pixels (a panel of several parts, such as the rail's quote head and stats, is the
box around them); the main process adds the window's place and whether it is minimized.

**Requests** (`nova:clips:act`, from desk windows only; an answer is `{ok: true, ...}` or `{ok:
false, reason, error}`): `start {symbol, hq, origin}`, `stop {clip_id | symbol}`, `save_last {symbol,
seconds}`, `set_hq {clip_id, on}`, `detail {clip_id, from_ts, to_ts}` (the export dialog's tracks),
`plan {clip_id, settings}` (the export without making it), `export {clip_id, settings}`,
`cancel_export {export_id}`, `preview {clip_id, ts, picture, panels, blur}` (a JPEG data URL),
`delete`, `show`, `play`. Refusals: `CLIP_INVALID`, `CLIP_NO_TAB`, `CLIP_HQ_FULL`,
`CLIP_NO_PICTURE`, `CLIP_NOT_OPEN`, `CLIP_NOT_ON_SCREEN`, `CLIP_UNKNOWN`, `CLIP_OPEN` (stop it
first), `CLIP_EXPORTING`, `CLIP_NOTHING_TO_EXPORT`, `CLIP_NO_FRAME`, `CLIP_EXPORT_UNKNOWN`,
`CLIP_DELETE_FAILED`, `CLIP_NO_FILE`, `CLIP_OPEN_FAILED`, `CLIP_FORBIDDEN`, `CLIP_ERROR`.

**The export** (`clipExportPlan.mjs`, pure; `clipExporter.mjs`; the page `clip-export.html`,
`frontend/src/clips/export_page/`, WebCodecs + mediabunny): the stretch is cut wherever something
changes; each slice takes its picture from a high-quality file that ran in the tab's window, else from
the screen segment of the tab's monitor (ADR 035's `segments.jsonl`), so a lost capture leaves no
hole. Hidden stretches are cut when `cut_hidden` (the default); restart gaps, stretches Nova was not
following the tab (`unknown_sec`, whatever `cut_hidden` says) and stretches with no picture are left
out and counted -- `counts: {hq_sec, screen_sec, hidden_sec, gap_sec, unknown_sec, no_picture_sec}`;
the dialog's tracks add `unknown`. A cut is the monitor's picture: a window over the tab is in it (the
dialog says so; High quality records the tab itself). The blurred panels are the rail's trade card
(`stock-view-open-card`), the plan and the orders dock with its position line; the charts' own
position line is not blurred, and the dialog says that too. A screen crop maps the page's rectangle through `content` onto the
segment's display bounds and size; a window capture's is worked out from each decoded frame (the frame
is the window's visible rectangle, the page at its bottom-left under the title bar; measured on the
desk's monitors at 100% and 150%). The MP4 (H.264) is at a constant rate -- 30 fps with any high
quality, else 15 -- each output frame the source frame showing at that moment, fitted without
stretching, with the chosen panels blurred; at most `CLIP_OUT_MAX_WIDTH` x `CLIP_OUT_MAX_HEIGHT`. The
sandboxed page reads sources and writes the MP4 only through the main process, by the tokens a job
names; the MP4 is written to `.mp4.part` and renamed when done. Frames are walked with the sample
iterator, never looked up one timestamp at a time (mediabunny 1.61's key-packet lookup missed a
keyframe in a real segment on 2026-09-29). Nova never posts a clip.

**The desk.** The red ● (`RecordButton`) opens the Record menu: Market data (the Session Record,
unchanged, stopping is a hold) and Video clip (Start / Stop, Save the last 5 min, High quality), every
lock with its reason. The header's CLIP chips count up beside REC (amber for High quality's last
minute or a lost capture, dimmed for a hidden tab, red only with no picture); pointing at one shows its
card and has the tab draw its red frame; a click stops the clip and a toast offers the export. The
export dialog: the preview, the picture, the panels to blur (the plan, the order ticket and positions
& orders on by default), the trim timeline over the day (moments from the eyes' journal, the screen
recording, high quality, when the tab showed the symbol), the output line and X's 2:20 hint. Records
› Video clips lists every clip by Eastern day with the actions of its state. The Nova Actions
`clip_toggle` and `clip_save_last` ship unbound; `runNovaAction` hands them to the clips feature before
any gate. A browser desk has no clips and says so.

**The backend.** `GET /api/clips` answers `{schema_version: 1, reported, fresh, age_sec,
received_ts, view}` (`fresh`: younger than `CLIPS_STALE_SEC`); `POST` refuses an unknown
`schema_version`, `dir_source` or open-clip `state` (422) and a body over 256 KB (413). The checklist
row `clips` (group `recorder`) is `off` with no desktop app reporting, `unknown` on a stale report,
`ok` in the ordinary run, `warn` on a lost high-quality capture, an unwritable clip list or the system
drive, and `fail` only when an open clip has no picture. The perf recorder (ADR 026) names the two
hidden pages' processes `clip-recorder` (High quality) and `clip-export` in the Electron report's
`processes`, beside `screen-recorder`, and the focus sensor (ADR 033) leaves all three out: they are
never a window the operator sees. Their `cpu_pct` is Electron's, divided by the logical CPUs (24 on
the desk PC), so 3.5 there is about 0.84 of a core.

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
file is `schema_version: 5` (ADR 042); a v1-4 file migrates on load (v1-3:
`active_pack`, `pack_settings` and `llm` stripped; v4: below) and an unknown
version refuses loudly. **One owner for Nova's buys (ADR 042, operator decision
2026-09-30: "why is it a radio button? We are already choosing if it's off,
eyes only, or strategy independently in each strategy").** There is no chosen
setup: the session's `level` (per venue, "The level belongs to a venue" below)
is the **master ceiling** -- the most any setup may do on this venue, and the
level the localhost bot API reads -- and `setup_levels: {SETUP: 0 | 1 | 2}`
holds every setup with a scanner's own level; a setup's **effective** level is
the lower of the two. Off (0) watches and scores in silence, Eyes (1) proposes,
Strategy (2) lets Nova's bot and Auto-entry trade its go triggers while the bot
is Active (until then it proposes like Eyes). `GET /api/bot/session` adds
`setups: [{id, scanner, level, effective}]` (`level` / `effective` null without
a scanner) and `setup_levels`; `PATCH /api/bot/session {setup_levels: {SETUP:
0 | 1 | 2}}` sets any of them (each change a `setup_level` audit line `inputs:
{setup, from, to}`), and raising the master `level` needs no Activate token
(configuration is not "go"). `PATCH {setup}` is refused `400
BOT_SETUP_RETIRED`. The v4 -> v5 migration gives the old chosen setup the old
`level`, keeps the others' 0 / 1, drops `setup`, `strategy` and the `advise`
budget (and `/api/bot/advise*`, which nothing called), and moves the sleeve, the
bot list and the day lock into each venue's dial (below).

`readout` (owner `setup_scanner/readout.py`, cached 30 s) is `{state:
"collecting" | "passed" | "not_passed" | "failed" | "unavailable", passed,
reason, go: {triggered, scored, win_pct, avg_net_r}, control: {...}, rules:
{kind, min_go, fail_go, min_net_r}}` over every `setups.db` row of the setup's
first-of-the-day kind (`rules.kind`: `first_pullback`, `bull_flag`,
`flat_top_breakout` or `red_to_green`, ADR 031) that triggered: `go` are those whose tape was go at the
trigger, `control` those blind or wait (pooled). It passes when at least 50 go
setups triggered and their average net R is above +0.2 and above the
control's; it is judged on the first 100 go setups, and 100 without a pass is
`failed`. A closed store is `unavailable`. **Read-outs are evidence, and
gate nothing** (ADR 042, amending ADR 027 / 030): Nova's bot trades Paper and
Sim only, and Live trading by a bot is not built -- it waits on its own operator
decision -- so passing a read-out unlocks nothing yet. Each setup's card shows
its own read-out (`GET /api/setups/templates`), which says it scores the
backtest's exit (half at target 1, break-even, a 9 EMA trail) while the bot
sells everything at target 1 with a 15-minute time stop. The session's
`readout`, `readout_required` and the `readout` gate are gone. **The localhost
bot API refuses Live**: every `POST /api/bot/action` on Live or on a replay desk
is refused `409 BOT_LIVE_NOT_BUILT`, exits and cancels included (a bot never
touches Live). At Strategy a `buy_*` kind is also refused outside its setup's
bot window on the venue's clock (each setup's template in play: `409
BOT_OUTSIDE_WINDOW`), outside 09:30-16:00 ET while the venue's sleeve turns
extended hours off, and past the venue's daily cap (`409 BOT_DAY_TRADE_CAP`):
the sleeve's `entries_per_day` (1-3, default 1) counts Nova's automatic entries
-- the bot's and Auto-entry's together -- per venue day, from the persisted audit
stream (entry audit rows carry `inputs.venue_day`; an entry cancelled unfilled
-- a `missed` -- gives the day back; Approve is counted, `entries_today.approved`,
never capped); exits and cancels are never held by either. **Commissions unknown
hold new entries** (operator decision on #564, 2026-09-24): while the session's
commission read fails, every bot entry on Live -- a `buy_*` kind on `POST
/api/bot/action` and the bot's own entry (both pass
`entry_rules.assert_entry_allowed`) -- is refused `409
BOT_COMMISSIONS_UNKNOWN` until a read succeeds again (the unreadable file is the
execution ledger every order is written to). Exits, cancels, flatten and kill
are never held, and Paper and Sim never are; a venue that cannot be read counts
as Live. The failure is logged (at once, then at most every
`BOT_COMMISSIONS_WARN_EVERY_SEC`), never read as $0. **The breakers compare
IBKR's own figure** (ADR 042 / #664): on Live, the finite `dailyPnL` from
`reqPnL` for the current READY IB instance, generation and account. IBKR owns
that figure's reset (the TWS configuration, not Nova's 04:00 ET lock boundary);
the API supplies no reset timestamp, so the meter never invents one. Pending,
failed, disconnected or superseded subscriptions cannot supply cached daily
P&L. While it is unavailable, the stated fallback is `RealizedPnL + UnrealizedPnL`,
which can include an overnight position's lifetime move. Both broker figures
already include commissions (TWS Users' Guide, Profit and Loss) -- until
2026-09-30 the breakers subtracted the session's commissions again and tripped
that many dollars early; on Paper and Sim at the live edge, the practice
ledger's `DayPnL`; on a replay desk nothing (a replay's P&L is not today's).
`GET /api/bot/pnl`'s meter says which: `{compares, source, venue, compared,
note, error, day_pnl, commissions, commissions_in_figure, commissions_unknown,
commissions_error, fallback, fallback_reason, reset_semantics, reset_time,
daily_pnl_updated_at, ...}`. The fallback and its limitation are visible; no
session commission is subtracted again. A commission read failure still holds
new Live bot entries without invalidating the known P&L. Practice day boundaries,
breaker thresholds, existing latches and trading authorization are unchanged.
Proposals are accepted at Eyes and Strategy. **Every gate is drawn with its
reason** (owner `bot/gates.py`): `gates: [{id, ok, stage: "activate" | "fire",
detail: {..., text}}]` are `venue` (Paper, or Sim at its live edge), `level`
(the master at Strategy), `setups` (`at_strategy`), `padlock`, `allowlist`
(stocks set to Bot or to Auto-entry on this venue; stage `fire`, so it never
locks Activate -- Auto-entry needs the bot Active), `depth_lines` (ok while at
least one Bot stock holds a depth line, `held`, `missing`, `max_lines`; each
trigger still needs its own), `bot_trip`, `day_lock`, `kill_switch`, `window`
(per Strategy setup: `setups: [{setup, start, end, open, clipped, error}]`),
`daily_cap` (`count`, `cap`, `venue_day`), `extended_hours` and `commissions`;
the session adds `ready` / `ready_reason` (the bot would trade a go trigger now)
with `live_fire_ready` as a one-release alias.

**Activate: one control, one meaning, never carried** (ADR 042, owner
`bot/activation.py`). `POST /api/bot/session/arm {reenable?}` refuses, `409`
with a plain reason: `BOT_LIVE_NOT_BUILT` (Live), `BOT_REPLAY_DESK` (Sim off the
live edge), `BOT_VENUE_UNKNOWN`, `BOT_LEVEL_NOT_STRATEGY`,
`BOT_NO_SETUP_AT_STRATEGY`, `BOT_PADLOCK_LOCKED` and `BOT_TRIP_LATCHED` (the
bot trip fired on this venue today; the desk confirms in words, then sends
`reenable: true`). Choosing Strategy never activates. The backend clears
Activate -- a `deactivate` audit line and `deactivated: {at, reason, text}`,
`reason` one of `restart | padlock | venue | level | no_setup | bot_trip |
all_stop | operator` -- on every process start (like spend arming, ADR 018),
when anyone locks the padlock (`ibkr.safety.set_armed` calls
`activation.on_disarm`; it used to be only a page effect), on a venue change,
with the master below Strategy or no setup left at Strategy, and on a trip. The
session's `active` is the truth (`armed` a one-release alias; `has_desk_arm`,
the token's presence, stays).

**One sleeve per venue** (ADR 042, owner `bot/sleeve.py`, #658 item 2). Each
venue's dial carries its own `caps: {venue, risk_usd, max_shares,
bp_budget_usd, working_ttl_sec, extended_hours, entries_per_day, api_kinds}`
(`allowlist`, the localhost API's order kinds, a one-release alias of
`api_kinds`); bounds `caps_bounds` (risk 1-10,000, shares 1-10, budget up to
$50, TTL 1-10 s, entries 1-3); a value out of bounds is refused `400
BOT_CAPS_INVALID`, never clamped in silence. `PATCH {caps: {venue?, ...}}`
edits the named venue's (else the desk's); `caps_by_venue` lists all three. The
migration copied the one sleeve to every venue. **One size**
(`bot/sizing.py`, pure) for every Nova automatic buy: floor(`risk_usd` / the
setup's risk a share), capped by `max_shares` and by what the budget still buys
(`{qty, by_risk, capped_by: "max_shares" | "budget" | null, text}`; under one
share is a stated skip). `risk_usd` is also the Trader's risk per trade. **One
entry timeout**: `working_ttl_sec` for the bot, Auto-entry and Approve.
`extended_hours` (default on: the default bot windows open at 07:00 ET) binds
the bot and Auto-entry. `entries_today: {count, cap, venue_day, entries:
[{symbol, setup_type, by, ts, outcome}], approved, error?}`.

**Loss breakers per venue** (ADR 032, operator ask 2026-09-24). The bot trip
(soft: flatten, the bot to L0) and the all-stop (hard: flatten, bot and manual
buys on that venue locked until the next 04:00 ET -- ADR 042: the practice
day's own boundary; at midnight they had lifted while the practice day's P&L
still read yesterday's loss, and tripped again) compare the whole account's day P&L with
the desk venue's own thresholds (owner `bot/breaker_limits.py`): the session
keeps `breakers: {VENUE: {soft_usd, hard_usd}}` for `live` / `paper` / `sim`
(an optional key of schema 4; a venue with none reads -50 / -200; a venue Nova
cannot read reads Live's). `GET /api/bot/session` adds `breakers: {venue,
soft_usd, hard_usd, custom, defaults: {soft_usd, hard_usd}, by_venue: {VENUE:
{soft_usd, hard_usd}}, bounds: {soft_usd: [loosest, tightest], hard_usd:
[loosest, tightest], step_usd}}`; `PATCH /api/bot/session {breakers: {venue?,
soft_usd?, hard_usd?}}` changes the named venue (else the desk's) within -5 to
-1,000 (bot trip) and -10 to -5,000 (all-stop), the bot trip above the
all-stop, snapped to $5 -- `400 BOT_BREAKER_INVALID` otherwise -- and records a
`breakers` audit line; a venue moved back onto -50 / -200 keeps no pair of its
own (`custom: false`). Moving a threshold never clears a fired bot trip or a
day lock. A trip writes its record on the dial of the venue whose P&L tripped:
`hard_lock_until_date` (an ISO datetime of the next 04:00 ET; a legacy
`YYYY-MM-DD` still lifts at that date's 00:00 ET), `hard_lock_at`,
`hard_lock_pnl`, `hard_lock_usd`, and the bot trip's `soft_breaker_at`,
`soft_breaker_pnl`, `soft_breaker_usd`; `bot.buy_lock.lock_for(row, venue)` reads
any venue's, `execution.service` asks with the door's own venue, and the session
adds `day_lock: {active, until, tripped_at, pnl, venue, threshold, text}`,
`day_locks` and `soft_breaker: {fired, at, pnl, until}` (`hard_lock_until_date`
/ `day_lock_active` stay one release, the desk venue's). On a replay desk the
breakers compare nothing and `breakers.note` says so. The Bots page drags the two markers on the desk venue's bar (it asks
before loosening Live), and the Account page's Risk block reads the same pair. A trip's flatten carries
its origin (`bot_trip` / `all_stop`, "Who sent it" under the execution command), and its audit line
(`breaker_soft` / `breaker_hard`) adds `inputs.closes: [{symbol, side, qty, ok, order_id, error}]` (what
the flatten sold, one line per position) and `inputs.flatten_error`. **Every desk window says so**
(operator report 2026-10-01: the trip had been visible only on the Bots and Account pages): the bot's
notices (`frontend/src/bot/breakerNotices.ts`) read the polled audit stream and raise one notice per trip
younger than 10 minutes -- "Bot trip sold your positions", the venue, the day P&L against the limit, the
time, each position sold with its order id (or why it was not), and what follows -- which stays until it
is dismissed; a failed sell reads "the sell failed -- close your positions yourself". `bot-session.json` and `bot-proposals.json` are written through a
temp file and a rename.

**The level belongs to a venue** (operator report 2026-09-30: "When I switch
between L0 and L2 in the paper, it stays persistent when I switch to live, and
I feel like that shouldn't happen"; owner `bot/venue_levels.py`). Each venue
keeps its own dial -- `level`, `setup_levels`, the bot trip's latch and record,
the all-stop's day lock (ADR 042, #658 option b: Live's lock follows Live and
switching away and back does not escape it), the sleeve (`caps`), the bot list
(`symbol_allowlist`; Live's starts empty: Nova never buys on Live) and the bot's
`working` orders and `bot_qty` -- the session's fields being the dial of
the venue in `level_venue` and the others waiting in `venue_levels: {VENUE:
dial}` (optional keys of schema 4; a venue with none starts Off, its bot trip
clear). `sim.mode.set_venue` puts the old venue's dial away, takes the new
one's and deactivates the bot (a `venue` audit line): Activate never carries
into another venue, like spend arming. A session loaded on another venue than
its `level_venue` takes that venue's dial; one without the stamp belongs to the
venue the desk showed. `GET /api/bot/session` adds `level_venue` and
`levels_by_venue: {live, paper, sim}`. The bot trip's latch adds
`soft_breaker_until` and lapses at the next 04:00 ET like the day lock
(`bot.clock.soft_latched`; a latch without it has lapsed), and the all-stop
trips again once an earlier day's lock has lifted -- it read the stale date as
"locked" and never tripped a second time. Leaving a venue first cancels Nova's
working entries there ("Who trades the stock" below). Every bot audit line
carries `venue`, and the daily entry cap counts this
venue's entries (a line without it counts on every venue). A TTL cancel and a
take-over of the exit never send another venue's order id.

**Nova's own bot** (ADR 030, owner `bot/first_pullback/`; #514; ADR 042).
Active at Strategy, on Paper or on Sim at the live edge -- never on Live -- it
hears the setup scanner's triggers (each setup's template in play's lane, live
feed only: `SetupEngine.add_trigger_listener`; the event carries `setup_type`,
`grade`, `pillars`, `filtered` and `spread`) and plays **every setup at
effective Strategy** on this venue's Bot stocks: the first go trigger wins, one
trade at a time, then the shared daily cap. It takes the first of a setup on a
symbol that day (its kind without `second_`) with the tape at go and the plan a
trade (NOT A TRADE is one rule, below), after every gate (`admit.for_bot`): the
venue, Activate, the setup's level and window, extended hours, a held depth
line, the padlock, the kill switch, this venue's day lock and bot trip, the
working block, the sleeve's size and the daily cap; a trigger it does not take
is a `bot_trade` `skipped` line with every reason (`inputs.codes` /
`reasons`) and the stock's last event on its Trader tab. Its entry is a
**practice bracket** (`operation: "bracket"`, source `bot`: a BUY limit at the
scanner's entry, a SELL limit at target 1 and a SELL stop, the exits held until
the entry fills, then one-cancels-other), so its stop and target rest at the
broker and Paper's fill while the desk shows another venue (Sim's matcher runs
only at its live edge: a Sim trade waits while the desk is elsewhere, and says
so). Unfilled after the sleeve's `working_ttl_sec` the entry is cancelled with
its exits (a miss). The time stop (`BOT_FP_TIME_STOP_MIN`, 15 minutes), the
flush exit (a tightened stop is a replace of the stop leg) and a stop leg that is
gone (the bot then watches the stop on IBKR's Last) cancel both legs and sell at
the bid, then the protective flatten. Every order carries its real setup
(`setup=<setup_type>`). It claims the L2 session as brain `nova-first-pullback`
(the id kept from ADR 030) and heartbeats while it plays. `GET
/api/bot/session` adds `runner: {brain_id, playing, reason}` and `trade` -- the
current or last trade, `{setup_id, setup_type, symbol, venue, venue_day,
template_id, template_rev, state: "entering" | "open" | "exiting" | "closed" |
"missed" | "handed", qty, trigger, entry_planned, stop, target1, risk,
entry_order_id, entry_fill_price, entry_filled_ts, target_order_id,
stop_order_id, stop_leg_at, exit_order_id, exit_price, exit_reason: "target" |
"stop" | "time" | "flush" | "outside" | "handed" | null, closed_ts, slippage, r,
size_text, waiting, note}` (`r` gross in the setup's risk), kept in
`bot-session.json` so a restart resumes it; a take-over whose cancel is refused
keeps the trade and says the order still rests. Every step is on the bot audit stream as `bot_trade` (`skipped` |
`missed` | `filled` | `closing` | `closed` | `note` | `error`, `inputs` with
the `setup_id`). A bot working order the bot cancels itself carries
`expire_ts: null` in `working`.

### One Bots page (ADR 044, operator decisions 2026-10-01)

"I definitely don't like it if we have redundancies ... put everything on one page", after AISP's three
triggers went unbought for five reasons no screen showed together. ADR 044 amends ADR 042, 037, 041,
036, 032 and 023 as below.

**The Bot switch.** One per venue, on the desk in place of the master dial and Activate. `POST
/api/bot/session/switch {on: boolean, reenable?: boolean}` (API key) answers the session view.
- **ON** puts the venue's master `level` at Strategy (2) and activates. It is refused like Activate:
  409 `BOT_LIVE_NOT_BUILT`, `BOT_REPLAY_DESK`, `BOT_VENUE_UNKNOWN`, `BOT_PADLOCK_LOCKED`,
  `BOT_NO_SETUP_AT_STRATEGY` (no strategy is On), and `BOT_TRIP_LATCHED` unless `reenable`. A
  successful ON returns `desk_arm_token`, as `/arm` does.
- **OFF** deactivates (`deactivated.reason: "operator"`) and puts the master at Eyes (1), so setups
  at Eyes or On still propose.
- **The bot trip** (`bot/autonomy.drop_to_eyes`, `drop_to_l0` kept as its alias) also leaves the master at
  Eyes (1), not Off; its `breaker_soft` line's outcome reads `eyes`.
- Each change is a `bot_switch` audit line, outcome `on` | `off`, `inputs: {on, from_level, to_level}`.
- The session view adds `bot_on: boolean` (active with the master at Strategy) and `switch: {on, venue,
  why_off: string | null, latched: {at, pnl, until} | null}`.
- The localhost bot API's `level` stays readable, and `PATCH {level}` stays for it.

**Strategies: Off · Eyes · On** are `setup_levels` 0 / 1 / 2 under new names on the desk.
- Two template parameters join the bot group, which never restarts a read-out:
  - `bot_grades`: `"AB"` (default) or `"A"`. C stays NOT A TRADE.
  - `bot_setups_a_day`: 1 (default) or 2.
- `bot/first_pullback/admit.blockers` reads both from each setup's template in play:
  - a grade the template does not buy is `BOT_SKIP_GRADE` ("grade B: this strategy buys grade A only");
  - a setup whose `nth` is over `bot_setups_a_day` keeps its code `BOT_NOT_FIRST_OF_DAY` ("a 2nd first
    pullback: this strategy buys the 1st of the day only").
- The built-in template takes them too: `PATCH /api/setups/templates/{setup}/default` accepts bot-group
  values only (a name, a note or any scanner value is still `TEMPLATE_BUILTIN`). They are stored as
  `setups.{SETUP}.default_bot` in `setup-templates.json`, only the values that differ from the defaults,
  and the answer is `rules_changed: false` with the revision unchanged.
- A strategy at Off draws nothing on the charts.

**Today's hot list** (owner `backend/hot_list/`): the stocks Nova watches all day. Watching only (amended
2026-10-06, operator: "a starred ticker ... shouldn't be buying and selling if it's signal only"): a star never
decides who trades a stock, and taking one off never changes it -- that is the stock's Buy / Sell alone.
- **The file** is `hot-list.json` in the operator cache: `{schema_version: 1, date: "YYYY-MM-DD", auto_n: 0 | 3
  | 5 | 10, entries: [{symbol, how: "auto" | "star", at, board: "gainers" | null, rank: integer | null,
  change_pct: number | null}], yesterday: string[], reset_error?: string}`. A file written before
  2026-10-06 may carry `default: {buy, sell}` (the side a new name started on); it is read and dropped.
  `reset_error` is present only while today's 04:00 reset of the bot's buys failed (below).
  - `date` is the trading day, which starts at 04:00 ET; `at` is epoch seconds; `change_pct` is a fraction
    (0.6 = +60%), as on leaderboard rows. `yesterday` is the last day that had names, so Monday's
    bring-back finds Friday's.
  - Written through a temp file and a rename. An unknown version or an unreadable file reads as an
    empty list with the error stated, and writes are refused 409 `HOT_LIST_UNREADABLE` (also when the
    file cannot be written).
  - `HOT_LIST_CAP` is 20. Each day is also kept read-only as `hot-list/YYYY-MM-DD.json` for the
    triggers audit.
- **Auto** (`hot_list/auto.py`), every `HOT_LIST_AUTO_TICK_SEC` from `HOT_LIST_AUTO_START_ET` (07:00) to
  `HOT_LIST_AUTO_END_ET` (16:00): the live Gainers board through `scanner_surface.surface_rows` and
  `leaderboard.ranking.rank_rows` with `LEADERS_RULES`, its top `auto_n`. A name is added once a day and
  stays: one the operator takes off is not added again that day (remembered in memory, and re-read from
  the audit stream after a restart).
- **At 04:00 ET** (the day's reset of the bot's buys, run by the rollover):
  - `entries` move to `yesterday`;
  - every venue's bot list (`symbol_allowlist`) and every Auto-entry / Approve switch are cleared,
    with a `hot_list` audit line `{event: "rollover", cleared}`, so yesterday's choices never buy today;
  - trades Nova holds keep their exits.
  - The bot and Auto-entry buy nothing until today's file is written: `BOT_SKIP_DAY_NOT_RESET`
    (`hot_list.day_reset_block`; the auto feed's loop rolls over within `HOT_LIST_AUTO_TICK_SEC` of 04:00
    and at every start). When clearing the bot lists fails, today's file carries `reset_error`, the bot
    still buys nothing, and every later pass retries the lists (not the switches: one set since is today's);
    the retry that works writes a `rollover` line with `inputs.retry: true`.
- **Followed by the scanners.** The stocks the bot buys (Buy set to Bot on the desk's venue: its bot list,
  then each Auto-entry switch; `hot_list.following.bot_buy_symbols`), then listed names, share HOD Momo's 20
  reserved slots (`HOD_MOMO_FORMER_MOMO_MAX_SLOTS`) with Former Momo (`hod_momo_active.build_active_set`,
  `bot_symbols` then `hot_symbols`), then Former Momo fills what is left, so live movers keep at least 20 of
  the 40. A name on two lists counts once, as the first's. Past the 20 a name's admission reason is
  `bot_buy_over_reserved` / `hot_list_over_reserved` (it can still win a mover's slot on its own move); one
  IBKR cannot stream is `bot_buy_l1_blocked` / `hot_list_l1_blocked` and frees its slot. `GET
  /api/setups/symbol/{symbol}`'s `followed_note` says why a bot-buy or listed name is not followed.
- **Who trades the stock.** The stock's Buy / Sell switch (ADR 037) is the only "who", and the list is no
  part of it: starring, an auto star, bring-back and taking a stock off never change Buy / Sell, setting Buy
  to Bot never stars a stock, and the bot buys a stock whose Buy is Bot whether it is listed or not.
- **The mark.** On the desk a listed ticker carries a filled ★ (your star) or an outlined ☆ (an auto star)
  beside its symbol: scanner and Desk board rows, the Trader tab, the Focus rail, the HOD Momo strip, the
  quote card and the Who trades row (`watch_list/WatchMark.tsx`, `watchHow`).
- **Audited.** Every change is a `hot_list` line on the bot's audit stream, outcome and `inputs.event` one
  of `rollover` | `auto` | `star` | `remove` | `settings`, with the symbol where there is one (lines before
  2026-10-06 may also read `default`).
- **Routes** (writes need the API key):
  - `GET /api/hot-list` -> `{schema_version: 1, date, cap, auto: {n, start, end, rule, error},
    entries: [{symbol, how, at, board, rank, change_pct, followed: boolean | null, why_not_followed:
    string | null}], yesterday, error}` -- `why_not_followed` is null while `followed` is true: "HOD Momo's
    20 reserved slots are full", IBKR could not open the name's line, the scanner has not picked it up
    yet, or the active set has not been rebuilt since it was listed; `followed` is null when the scanner
    could not be read;
  - `POST /api/hot-list/star {symbol}`;
  - `DELETE /api/hot-list/{symbol}` (who trades it is unchanged; `HOT_LIST_NOVA_TRADE` is retired);
  - `PATCH /api/hot-list {auto_n?}`;
  - `POST /api/hot-list/bring-back` (yesterday's names as stars, up to the cap).

  Every write answers the view.

**The squares, by ticker.** `GET /api/bot/triggers?date=YYYY-MM-DD` (default today: the hot list's
trading day, which starts at 04:00 ET, never the calendar date; owner `bot/trigger_audit.py`, read-only)
answers:

```
{schema_version: 1, date, generated_at,
 gates: [{id, label}],
 tickers: [{symbol, listed: {how, at} | null,
            now: {cells, answer: "yes" | "no", reasons} | null,
            triggers: [{ts, setup_id, setup_type, kind, nth, grade, tape, outcome, r, cells, reasons}]}],
 impact: [{gate, blocked, target_first, stop_first, r}],
 judged_now: string[],
 sources: {journal, audit, hot_list: {ok, error}}}
```

- **The gates**, in Nova's order: `bot_on`, `strategy_on`, `grade`, `setups_a_day`, `bot_window`,
  `nova_buys` ("Bot buys"), `level2_line`, `tape_go`, `trades_today`. The `hot_list` gate is retired
  (2026-10-06): being listed decides nothing, so no square asks it.
- **`cells`** maps each gate to `{ok: true | false | null, why}`; `null` means the gate did not apply.
  A trigger reads the bot's state, tape, grade (its `armed` line), `nth`, liquidity and outcome as the
  journal recorded them. It reads the stock's mode and the strategy's level from the audit stream at its
  moment. `judged_now` names the gates judged with today's
  settings because nothing recorded them.
- **`grade`** also carries NOT A TRADE's own checks (grade C, the spread, too thin), so every block has
  its red square.
- **A setting at a trigger** is the nearest audit record before it; one that a restart, a venue change or
  the rollover hides reads `null`.
- **The tickers**: the day's hot list (`listed`), then today's bot-buy stocks not on it, then every other
  ticker that triggered (`listed: null`).
- **BLIND** is the Level 2 line's red, never the tape's.
- **`now`** (today only, the trading day: the rows stay from midnight to the 04:00 rollover) is each
  listed or bot-buy ticker this minute; its `nova_buys` square is red while today's reset has not run.

**A hidden Trader tab lends its Level 2 and Time & Sales lines** (owner `backend/line_lending/`). IBKR
caps tick-by-tick lines too (ADR 044 took it for the depth lines' 3; on 2026-10-02 it carried 4 at once and
refused a 6th while Nova held 5, #698), so a loan moves both: a borrower
with a book and no prints would read WAIT, never GO.
- **When.** A setup of a strategy at On, on a stock whose Buy is Nova (Bot or Auto-entry), with the Bot on,
  is armed, near or in a trade; no line is free; and `line_lending` is on (`bot-session.json`, desk-wide,
  default true). Then the lines of a Trader tab that no visible window shows (the focus sensor) are lent to
  it. Checked every few seconds, so a setup has its lines before its trigger.
- **Never lent:** the tab in front, or one in front in the last 30 s; a line a Session Record, auto-record
  or the L2 recorder holds; a line a Level 2 outside a Trader tab watches; a stock Nova needs a line on
  itself; anything while the focus sensor cannot say which tab is in front.
- **On the lender's sockets.** A Trader tab opens `/ws/ibkr/depth/{symbol}` and `/ws/ibkr/tape/{symbol}` with
  `?tab=1&front=0|1`. Both send `{"type": "lent", symbol, to: {symbol, setup_type, setup_id}, why, tier,
  since, text}` (`why` in words, `tier` its code) and close. A socket opened with `front=1` -- the tab came
  to the front -- recalls the loan: both lines come back together, and the borrower's loss is said in the
  audit stream.
- **When it ends.** `setup_ended` (the setup failed or disarmed), `trade_ended` (the scoring window and
  Nova's trade are both over), `recalled`, `lending_off`.
- **Routes.**
  - `GET /api/ibkr/depth/lines` -> `{schema_version: 1, generated_at, cap, lines: [{symbol, held_by: "tab" |
    "record" | "auto_record" | "loan" | "replay", front: boolean | null, viewers}], lending: {on, error,
    loans: [{lender, borrower, setup_type, setup_id, since, why, tier, state, text, tape_lent, tape: boolean
    (a print arrived on the borrower's line), tape_state: "receiving" | "waiting" | "refused",
    tape_last_print, tape_error}], recent: [{lender, borrower, setup_type, setup_id, since, ended, end,
    tape_lent, text}]}}`. A borrower's tape line IBKR refuses or ends (10190) is `tape_state: "refused"`
    with `tape_error`, and is asked for again.
  - `PATCH /api/ibkr/depth/lending {on}` (API key) answers the same view; a `line_lending` audit line.
  - Every loan is a `line_loan` audit line: `lent` (with `tape_lent`, and the tape's error when the
    borrower got none), `ended`, `tape_refused` (once per refusal) and `tape_opened`.
- **On the desk** the lender's Level 2 and Time & Sales read "Level 2 lent to AISP's first pullback (near
  its trigger) -- back when it ends or when you bring this tab to the front". They reconnect when the loan
  ends or the tab comes to the front, never by their own backoff. A tab brought to the front within IBKR's
  15 s same-instrument rule shows its Time & Sales resubscribing for those seconds; the 10-second chart,
  built from those prints, has a gap for the length of the loan.

**On the desk.** The Bots page reads, top to bottom:
1. one answer line ("Can Nova buy right now?" for every ticker at once, each red with its fix, the
   desk's checks as chips);
2. the Bot card (the switch, Freeze all orders, the venue's risk);
3. the strategies, each Off · Eyes · On with its bot rules;
4. Level 2 lines;
5. Tickers today (the hot list and the squares);
6. Today, Proposals and Activity.

Elsewhere:
- **Freeze all orders** is the kill switch's name on the desk (`/api/kill-switch` unchanged). The
  header's red KILL is the one that flattens.
- **The Trader's chart toolbar has one Eyes switch** for every pane of the tab. `nova.stockRead.layers`
  `value` adds `eyes: boolean` (true when a stored value lacks it); off hides every Nova drawing, while
  `setups` / `levels` keep their own values for when it is on.
- **The Who trades row adds the ★** (on today's hot list; ☆ outlined for an auto star) and the stock's own
  answer ("Bot may buy AISP: no -- the bot is off").
- **Bot buy, bot sell** (operator, 2026-10-06: "Let's not have Nova buy and sell terminology"): every Buy /
  Sell switch reads You | Bot, the modes "bot buys · you sell", "you approve · bot sells", "bot buys · bot
  sells", and the chart's calls BOT BUYS AT / BOT BOUGHT / BOT IS SELLING / BOT HOLDS THE EXIT. The wire
  keeps `"you" | "nova"`.

### Release notes and the update notice (operator ask, 2026-09-23)

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

### Filing an issue from the desk (operator ask, 2026-09-24)

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

### Setup templates, the eyes' journal and replayed eyes (ADR 029, operator ask 2026-09-23)

`GET /api/setups/templates` (owner `backend/setup_templates/`) answers
`{schema_version: 1, error: string | null, max_per_setup, setups: [{id,
scanner: boolean, catalogue: {setup, scanner, source, groups: [{id, label,
blurb, params: [{key, group, label, kind: "number" | "int" | "bool" | "time" |
"choice", default, unit, min, max, step, choices: [{value, label}], nullable,
help, live}]}]}, in_play, templates: [{id, setup, name, note, rev, values:
{KEY: value}, builtin, in_play, fingerprint, error: string | null, created_at,
updated_at, readout?: {state, passed, reason, go_triggered, min_go,
go_avg_net_r}}]}]}` -- values in the unit the operator types (percent as 5, a
float in millions of shares); a nullable parameter is off when `null`;
`readout` only on a setup with a scanner. Writes need the desk's API key even
on loopback, like bot routes (a template sets the bot's entry rules):
`POST /api/setups/templates/{setup}` `{name, from?, values?, note?}` -> 201;
`PATCH .../{id}` `{name?, values?, note?}` -> `{template, rules_changed,
setup}` (a change to `values` bumps `rev`; a rename does not); `DELETE
.../{id}`; `POST .../{id}/play`. Every write answers `setup`, that setup's
view. A refusal is `{detail: {reason, error, field}}`: `TEMPLATE_INVALID` 400,
`SETUP_UNKNOWN` / `TEMPLATE_UNKNOWN` 404, `TEMPLATE_BUILTIN` /
`TEMPLATE_LIMIT` / `TEMPLATE_NAME_TAKEN` / `TEMPLATES_UNREADABLE` /
`TEMPLATE_NO_PARAMS` 409. The built-in `default` (the pre-registered rules at
`SETUP_TEMPLATE_DEFAULT_REV`) is never stored and never edited. The store is
`setup-templates.json` in the operator cache: `{schema_version: 1, setups:
{SETUP: {in_play, templates: [{id, name, note, rev, values, created_at,
updated_at}]}}}`; an unknown version or an unreadable file leaves every setup
on its default and refuses writes.

The setup scanner runs one lane per template of every setup with a scanner
(ADR 031): every template is watched; each setup's template in play proposes
(at Eyes or above) and draws that setup's rows. `setups.db` was `PRAGMA
user_version = 2` here -- rows add `template_id`, `template_rev` (integer) and
`params_hash`; a version-1 file migrates in place and its rows become the
default's (ids stay `SYMBOL-DATE-LEG_T`; another template's rows end
`~TEMPLATE_ID`) -- and is 3 since ADR 031 (`setup_type`, `detail`). The board payload adds `source: "live" | "sim"`, `template:
{id, rev, name, params_hash} | null`, `templates_watched` and `replay: {kind:
"capture" | "journal", date, symbol, playhead, at, loading, error, note,
recording, loaded?, gap?, journal?} | null` (`journal`: "Recorded eyes in Sim"
below; its `setups[]` add `recorded: boolean`); a row's `state` may be `filtered` (the template's stock
filter kept the name out, and the reason says which rule); a proposal adds
`template_id`, `template_name` and `source`. The read-out's `rules` adds
`template: {id, rev, name}` and counts only that template revision's rows.
`bot/entry_rules` reads each setup's bot window from its template in play
(`bot_window_start` / `bot_window_end`); the daily cap is the venue sleeve's
`entries_per_day` (ADR 042), and `bot_entries_per_day` left the catalogue: a
stored template that carries it loads without it (listed on the wire as
`retired: [{key, value, text}]`), and a write that sends it is refused
`TEMPLATE_INVALID`. **The bot's rules never restart a read-out** (ADR 042):
the parameters in the `bot` group are left out of a template's `rev`, its
fingerprint and `params_hash` (every catalogue param carries `affects_readout:
boolean`; a save touching only bot parameters answers `rules_changed: false`
and keeps the revision). **The bot window sits inside the arming window**: a
write whose bot window reaches outside the setup's arming window is refused
`TEMPLATE_INVALID` naming the field and both windows; a stored window outside it
is clipped when read, and a window wholly outside is empty (the bot never
enters on that template). A template adds `bot_window: {start, end, clipped,
empty, arming: {start, end}, stored: {start, end} | null, note} | null`; red to
green's built-in is 09:30-10:00. The read-out adds `bot_window: {start, end,
clipped, triggered, triggered_inside, go_triggered, go_triggered_inside} |
null` (its pre-registered rules unchanged). A setup without a scanner takes no
template writes: create, update and play are refused 409 `TEMPLATE_NO_SCANNER`. `GET /api/setups/scoreboard` and
`GET /api/setups/rows` answer for the template in play (its id and current
revision) unless `template=` names another template id (every revision) or
`all` (every template: a variation re-scores the same legs, so counts
overlap); both add `template: {id, rev, name} | null`.

**The eyes' journal** (`backend/eyes/journal.py`):
`<eyes dir>/journal/YYYY-MM-DD.jsonl` (`NOVA_EYES_DIR`, else `F:\Nova\eyes`
when F: is mounted, else `<cache>/eyes`; the file is the wall clock's Eastern
date), one line per observation: `{schema_version: 1, wall_ts, ts, date,
source: "live" | "sim" | "backtest", event, symbol, template, rev, playing,
bot: {level, active, venue} | null, replay?: {date, symbol}, ...}`, where
`event` is `session | lanes | watch | beat | leg | state | armed | filtered |
rearmed | near | tape | price | triggered | failed | disarmed | proposal |
scored` and carries its own fields (`setup` levels, `grade`, `pillars`,
`reason`, `tape` / `verdict` / `reasons` / `metrics` / `line`, `status`,
`outcome`, `bar_r`, `mfe`, `mae`, `added` / `removed`, `lanes`, `count`). `ts`
/ `date` are the moment and session the eyes looked at (a replay's own). A line
from a lane adds `setup_type` (ADR 031). Since 2026-09-24 every line about a
symbol carries the detector's `last` price and `leg` (`null` when none), a
`triggered` line its `reason`, a `state` line `kind` and `nth`; the lane writes
a `state` line whenever the detector's state or reason differs from what its
last line implied (`setup_scanner/lane_view.JOURNAL_EVENT_STATES`; writer
`setup_scanner/lane_journal.py`), the playing
lane a `price` line for a name armed or near at most every
`EYES_JOURNAL_PRICE_EVERY_SEC` (5 s), and the live engine a `beat` line (`count`:
names followed) every `EYES_JOURNAL_BEAT_SEC` (60 s). `NOVA_EYES_JOURNAL=0` turns
it off. Read by `tools/eyes_journal.py` (`days | summary | setups | events |
board`) and `eyes/reader.py`; the desk reads one symbol's day through `GET
/api/stock-read/{symbol}/decisions` (ADR 036), and the Sim desk off the live
edge every card at the playhead ("Recorded eyes in Sim" below).

**Replayed eyes** (`backend/eyes/replay.py`, `sim_eyes.py`, `backtest.py`): a
Session Record's prints (per second, the high then the last of the prints that
set a price), its recorded books (sampled every 0.5 s) and the day's archive
minute bars (else the recording's `bars_1m`) through the same lanes; outside a
recorded stretch nothing is near and nothing triggers. `GET /api/eyes/journal`
-> `{writer: {enabled, dir, written, dropped, queued, last_error,
last_write_ts}, days: [{date, bytes, path}]}`; `GET /api/eyes/sim` -> `{target,
loading, error, template, lanes, recording, now}`; `GET /api/eyes/backtests`
-> `{dir, runs: [{run_id, created_at, finished_at, status, error, templates,
sessions, setups}]}`; `POST /api/eyes/backtests` `{setup?: SETUP, templates?: [id],
sessions?: [{date, symbol}]}` -> 202 `{run_id, status: "running"}` (400
`BACKTEST_INVALID`, 404 `TEMPLATE_UNKNOWN`; `setup` defaults to
`first_pullback`, and `templates` are that setup's; ADR 031); `GET /api/eyes/backtests/{run_id}`
-> `{manifest, summary}`. A run is `<eyes dir>/backtests/<run_id>/`:
`manifest.json`, `setups.jsonl`, `events.jsonl` and `summary.json`, shaped in
`eyes/backtest.py`'s docstring; never `setups.db`, never the live read-out.

**Recorded eyes in Sim** (`backend/eyes/playback.py`, operator ask 2026-09-24:
"i want this stuff to be recorded when they show up ... viewable in the sim ...
when something pops up ... so we can fine tune them when things dont match").
On the Sim desk off the live edge without a Session Record loaded -- nothing
loaded, a past day, a historical download -- the Setups board and every setup
card on the Bots page are the live eyes' journal of the playhead's Eastern date
folded up to the playhead: `source: "sim"`, `replay.kind: "journal"`, the rows,
each setup's funnel and the proposals open then, in the live board's shape.
Only `source: "live"` lines of that session count; no line after the playhead
is read; nothing is recomputed with today's rules (a loaded Session Record still
re-reads the recording with today's templates, `replay.kind: "capture"`). A
recorded proposal is pushed on `/ws/setups` as an alert when the playhead plays
across its moment (a step of at most `EYES_PLAYBACK_ALERT_STEP_SEC`, 120 s),
never on a jump or a rewind; nothing proposes (`proposing: false`). `replay`
adds `loaded: "historical" | "capture" | null`, `gap: {reason: "no_record" |
"before_record" | "not_running", since, until} | null` and `journal: {path,
exists, lines, folded, first_ts, last_ts, line_ts, skipped}`; `note` states the
absence. A silence longer than `EYES_PLAYBACK_GAP_SEC` (180 s) after a `beat`
of the same session is `not_running` (Nova closed or its eyes off), and a gap
draws no rows, no proposals and zero counts -- never the board carried across
it; a day written before beats existed has no gap check. A `session` line (Nova
started) begins the fold again from nothing, as the live eyes did. Each
`setups[]` summary adds `recorded: false` for a setup whose scanner was not
running at the moment; its level, template and window stay today's controls
(the window of the template that played then). `GET /api/eyes/at?date=YYYY-MM-DD&at=<epoch>`
-> `{schema_version, date, at, gap, note, journal, proposing, setups, rows,
proposals, universe, universe_symbols}` (the names the eyes followed then; 400
`EYES_DATE_INVALID`); `py -3 tools/eyes_journal.py
board --date D --at HH:MM[:SS]` prints the same. A backward scrub refolds the
day at most every `EYES_PLAYBACK_REBUILD_MIN_SEC`; the file is read off the
scanner's loop, as it grows.

**Every locked control says why** (frontend, `ux/whyTip.ts`): a control that
cannot act carries its reason in `data-why` beside `disabled` (or
`aria-disabled="true"`); one tip per window shows it on hover and at once on a
refused press. `ux/whyCoverage.test.ts` fails the build on a JSX element that
can be disabled without its reason.

**Every chip explains itself** (frontend, `ux/hoverTip.ts`, ADR 031): an enabled
element that carries `data-tip` (and optionally `data-tip-title`) shows it in one
tip per window on hover and on keyboard focus -- plain text, line breaks kept,
never HTML. A locked control keeps `data-why` (the two never stack). The setup
cards, the Setups board and the Symbols card explain every state, tape verdict,
grade, price, count, level and read-out this way; `title` stays for short labels.

**Ctrl+F finds on the page** (frontend, `ux/findBar.ts` + `ux/findText.ts`,
operator ask 2026-09-24: "can we also do like CTRL+F so maybe we can search on
anything in that screen instead of looking everywhere?"). Electron has no find
bar, so every window installs one from `main.tsx`: Ctrl+F opens it, typing
marks every shown match (CSS highlights; case ignored, spacing flexible, never
across two blocks, never hidden panels, tooltips or text fields), Enter /
Shift+Enter move, Esc closes and gives focus back. While it is open a changed
page is searched again at most every `FIND_REFRESH_MS`, keeping the current
match, never scrolling on its own. It yields Ctrl+F to a Nova Action bound to
it (the hotkey dispatcher marks the key handled first), and every key typed in
its box stays in the box. It reads only what is drawn as text: a chart's canvas
and a list's undrawn rows are not found. The Ctrl+Alt shortcuts menu lists it.

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
bid/ask/sizes and the replay's own previous close (null when nothing records
one, #542); depth is empty without recorded books; daily OHLC
is null unless a replay source provides it. Loading, failed, and pre-first-event
capture selections have no market data to fall back to -- there is no synthetic
instrument (ADR 019), and `replay_source` is `none` when nothing is loaded.

### Practice venues and fills (ADR 019, ADR 020)

The desk venue is `live | paper | sim` (`desk-venue.json` `schema_version: 2`,
`{"venue": ...}`; owner `sim/mode.py`). **Paper is Nova's practice account on
the live feed** (ADR 020): orders enter `execution.service.execute` unchanged
and are filled by the practice broker against the live reference (the L1
last only when it traded inside `PRACTICE_LIVE_FRESH_SEC` by IBKR's Last
Timestamp -- never the prior close a line carries before its first trade --,
live top of book, live tape prints that set a price for resting orders); the account is
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
`ts_source` naming what their `ts` is, so an arrival time is never read as the
exchange's own: every live print since #563 says `receive` and carries IBKR's
own second in `exchange_ts`; rows recorded before #563 say `exchange` but hold
arrival times too (print times, under "Prints that set a price"). Practice
order rows stamp `submitted_at` / `updated_at` / `filled_at` with the venue's
time -- the replay playhead on Sim,
the clock a rewind unwinds by -- and a paused Sim playhead scrubbed forward
still fills resting orders on the prints it crossed. Rules and biases: `architecture/practice-fills.md`;
fees and margin: `architecture/practice-account.md`.

**A practice send answers when the venue answers** (operator report,
2026-09-24: "Why are things not getting sent fast enough?"). The practice
broker's answer to a place or a replace is the order's acknowledgment
(`broker_ack_ns`, `practice/watch.note_answer`): `Submitted` for a resting
order, `Filled` for a fill at placement, so the reply -- and the ticket's
unlock -- leaves as soon as the venue decides, never after a wait for a
callback the practice broker does not send and never after an invented delay.
The broker's place / replace reply adds `filled_qty`, `remaining_qty`,
`avg_fill_price`, `status_reason` and `status_code`
(`practice/watch.answer_facts`). An order the venue cancels at the fill is
refused with the venue's own reason and code (`PRACTICE_NO_SHORTS`,
`PRACTICE_BUYING_POWER`), `broker_status: "Cancelled"` and its `order_id`.
Before this, 21 of 23 Paper orders that day answered in 5.1 s
(`EXECUTION_ACK_WAIT_SEC`) while they filled in under 150 ms. Live is
unchanged: its reply waits for IBKR's first status.

**Paper and Sim fill brackets in Live's shape** (ADR 037, #606 step 1; owner
`practice/bracket.py`, pure; contract `architecture/practice-fills.md`). A
`bracket` command is no longer refused `SIM_NO_BRACKET`: the practice broker's
`place_bracket` takes Live's order -- a LMT entry, a LMT take-profit and a plain
STP stop-loss on the reverse side, one quantity, TIF and outside-RTH flag on all
three, three consecutive order ids, entry first -- and answers `{ok, order_id
(the entry), parent_order_id, target_order_id, stop_order_id, error, mode,
nova_placed_at, broker_status, filled_qty, remaining_qty, avg_fill_price,
status_reason, status_code}` (a refusal: `ok: false`, `reason_code`, every id
`null`). The receipt and the execution row carry the three ids, and the three
watches are Live's (only the entry's counts toward the execution's fills). Every
practice row adds `parent_id` (the entry's id on each exit), `oca_group`
(`"oca-<entry id>"` on both exits) and `leg_role: "parent" | "target" | "stop"`,
all `null` on a plain order (a row written before brackets reads the same).
**The exits wait** `PreSubmitted` until the entry fills: a waiting exit holds
nothing, never fills and counts nothing toward a Flatten; applying the entry's
`filled` event wakes both (`Submitted`, placed at the fill's moment), so the
print that filled the entry never fills an exit and a Sim rewind before the
fill puts them back to waiting. **One cancels the other**: an exit's fill
cancels its sibling (`PRACTICE_OCO_CANCELLED`, "One-cancels-other: the target
filled" / "... the stop filled"), and an entry that closes unfilled -- cancelled,
refused at the fill, or expired -- cancels its waiting exits
(`PRACTICE_PARENT_CANCELLED`); each is an ordinary `cancelled` event stamped
source `venue`, so no event type and no ledger schema changed. Cancelling one
exit leaves the other; cancelling a leg the bracket already closed answers
`{ok: true, verified_gone: true, closed_by: <code>}`. A bracket's shape is
checked again at the broker (`BRACKET_GEOMETRY`, `QTY_INVALID`, then the TIF,
admission, `PRACTICE_NO_SHORTS` -- a bracket that opens with a SELL is refused
-- and buying power at the entry's limit). The ticket's Flatten counts a
bracket's two exits once, at the larger open quantity. **Stated difference
before 09:30 ET:** a practice stop triggers on any price-setting print, while
IBKR holds a plain stop until the open; it stands until #604's question 2 is
answered.

**Order timing readout** (`tools/order_timing.py`, read-only; asks the
backend that answers): per order, `{execution_id, created_et, venue,
operation, source, symbol, side, qty, order_type, price, order_id, status,
answer, error, steps: [{stage, at_ms, step_ms}], slowest, missing: string[],
venue_leg_ms, venue_is_local, browser_click_to_request_ms, fill_price,
exchange_ts_utc, exchange_to_callback_ms}` under `{schema_version: 1, api,
orders[]}` with `--json`. Stages are the backend's own `perf_counter_ns`
stamps from the moment Nova received the order (recorded in the ledger,
checks passed, sent to the venue, venue answered, filled, reply ready), in
time order; `venue_leg_ms` is sent to answered -- IBKR's round trip on Live,
the practice broker on Paper / Sim. A browser stamp is never subtracted from a
backend one, and a stage with no stamp is listed in `missing`, never guessed.
`answer` is the order's broker status now, shown on its first line ("cancelled
(broker now: Cancelled)"). The ledger records when the venue first answered,
not what it said, so the status is never printed beside that stage.

**A practice order's rows close when its venue closes it** (TNMG, 2026-10-02:
Nova's bot cancelled its unfilled Paper bracket entry 77 at 09:47:22, and the
bracket's row and the cancel's row read `acked` until the 10:36 restart's sweep
called them `failed`). An execution row's `status` is open while it is
`reserved | validated | sent | acked`, and closed once it is `filled |
cancelled | rejected | failed | abandoned | duplicate_replay`. `cancelled` is
new: the order reached its venue and closed unfilled -- a cancel, a DAY expiry or
a bracket's own closure -- so it is not an error (`error` stays null). One pure
rule classifies a venue's close (`execution.order_outcome.ledger_close`):

- `Filled` closes the row `filled`;
- `Cancelled` / `ApiCancelled` / `Expired` with no code, or with
  `PRACTICE_TIF_EXPIRED`, `PRACTICE_OCO_CANCELLED` or `PRACTICE_PARENT_CANCELLED`,
  closes it `cancelled` with that code;
- any other close is `failed`, in the venue's own words. That covers a refusal at
  a later fill, such as `PRACTICE_BUYING_POWER`, and `Inactive`.

On Paper and Sim no callback follows the venue's first answer. So every close
after it -- a resting fill, an expiry, a bracket's exits, Nova's own cancel --
closes that order's place, bracket and replace rows at that moment, with
`filled_ns` on a fill (`practice.watch.close_rows`). The rows are matched by the
order id, the venue (`mode`) and this process (practice ids restart per venue).
Nova's cancel also closes its own row `cancelled`, and the ticket's
acknowledgment wait never reopens a closed row.

Before this, a resting Paper order that filled read `acked` until a restart:
AIFF, NXL and CNTB were marked `filled` hours or days later. A bracket's row now
keeps its entry's `perm_id`; each exit leg had written its own over it, so TNMG's
row read 79.

The startup sweep reads a broker's cancel or expiry as `cancelled`, not
`failed`. Live still closes these rows only at that sweep (#712), and the sweep
reads the desk venue's book rather than each row's own (#713).

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
was armed on. The PIN is never in the repository or the frontend. Locking the
padlock -- by anyone -- also clears the bot's Activate, in the backend (ADR 042).

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

The owner is `backend/sale_conditions.py`; the codes live in `constants_tape.py`. Time & Sales shows every print, and dims one that does not set a price with the reason in its tooltip (#543). A Sim capture replay's prints on `/ws/ibkr/tape/{symbol}` -- the seed a socket gets on open or a scrub, and the stream as the playhead moves -- carry the same two fields, from the recorded row (`sale_conditions.tape_flags`). Every candle Nova builds from prints uses only the prints that set a price, volume included, because IBKR's own TRADES bars count the same prints. That covers the Trader's client 10Sec bar, `ibkr/tape_10sec`, the archive 1m builder, the recorder's bar buckets and a capture replay's print-built candles. A row without the fields (an older recording) is judged by its conditions. A Session Record replay draws every candle from its prints and never from the bar buckets stored beside them (#535, operator decision 2026-09-23): recordings made before this rule stored buckets built from every print, and `replay_load.counts` no longer lists `bars_10s` / `bars_1m` / `bars_5m`.

Practice fills follow the same rule (#511): on Paper, and on Sim at the live edge, the practice broker's newest-print last and its resting-order matcher read only the prints that set a price, and so do a capture replay's last and matcher. The live tape archive (`l2.db` `tape_trades`) adds a nullable `unreported` column (IBKR's flag) beside `conditions` for this; a row stored before it is judged by its conditions. A historical download already excludes IBKR's `unreported` prints.

**Print times (#563).** ib_async 2.1.0 stamps each AllLast tick with the moment its message reached Nova (`Wrapper.lastTime`) and throws IBKR's own `time` argument away. A live print's `time` / `ts` is that arrival time, and it says so: `ts_source: "receive"`. IBKR's whole epoch second for the print rides beside it as `exchange_ts: integer | null`, on each live print on `/ws/ibkr/tape/{symbol}` and on each Session Record print row; `ibkr/tape_exchange_time.py` keeps the `time` argument with a thin override of `Wrapper.tickByTickAllLast`, installed on the IB that opens the tape line. `exchange_ts` is `null` when the override did not see the tick. Prints stay ordered by arrival, because the books they are classified against are arrival-timed too. Rows recorded before #563 say `ts_source: "exchange"` but hold arrival times as well, and carry no `exchange_ts`; they load as they are and are never rewritten. `l2.db` `tape_trades` and the archive keep no `exchange_ts`.

**A 10-second candle has one clock and one writer (#721; operator report 2026-10-05: "two candles drawing
together ... the previous candle should never move").** Built from prints -- the Trader's client bar
(`chart/barsStore.upsertTapePrint10SecBar`) and the backend's `ibkr/tape_10sec` -- a candle is keyed by
IBKR's own second for each print (`exchange_ts`, arrival time only when it is missing), the clock IBKR's own
10-second history uses, so a history fill moves no candle the tape drew. Arrival time had built 51-97% of the
day's candles differently from IBKR's, and trails IBKR's second by 0.6 s at the median, up to 9 s. IBKR
delivers prints in the order of that second: 1,219,396 October prints, none out of order. So a candle never
takes a print after the next one opened. The backend flushes a quiet bucket `TAPE_10SEC_FLUSH_GRACE_SEC`
after its ten seconds, and neither side reopens a closed candle. The 10-second pane's forming candle is the
tape's while the tape delivered a print within `CHART_10SEC_TAPE_OWNS_MS` (`chart/useChartLiveTrade`,
`tapeOwns10Sec`). The ticker's `trade_update`, stamped with Nova's clock when the Level 1 tick lands, opened
the next candle while prints still filled the last one, and now paints it only when no tape feeds it (Time &
Sales hidden, lent or silent). Minute candles and Sim replays keep their clocks.

The L1 last every quote reader takes (`ibkr/ticks_handler.py`) is IBKR's Last (tick 4, or 68 delayed). It is never the RTVolume or AllLast price that ib_async also writes into the one `ticker.last` it keeps per contract. A line that has not yet delivered a tick 4 falls back to `ticker.last`.

**The prior close is not a trade (#541).** Before a line's first trade its price is IBKR's prior close (tick 9), flagged `quote_quality: "close_fallback"`. Scanner rows show it as such; nothing else takes it as a trade: no live 1-minute candle (`ibkr/l1_minute`), no HOD Momo trade or L1 archive tick, no `trade_update` to a chart tip, no HOD enrichment price or change, and `snapshot_quotes` rows carry the same flag. `ibkr.ticks.last_quotes` rows add `quote_quality` and `last_trade_ts` (IBKR's Last Timestamp, tick 45 / 88, epoch seconds, `null` when IBKR has not sent one); a quote change keeps a line fresh but is not a trade. The ticker snapshot (`ticker_ibkr.fetch_ticker_snapshot_ibkr`) answers `latest_trade: null` and `daily_bar: null` before today's first trade (the prior close stays `prev_close`), stamps `latest_trade.timestamp` with the trade's own time (a stored bar's minute, a row's quote time, `null` when unknown -- never "now"), takes a stored 1-minute bar only from today's Eastern date, and reports an unknown volume as `null`, never `0`.

**Level 2 books are Nova's own (#540).** ib_async 2.1.0 keeps each side of a depth book in a dict keyed by row: an IBKR insert overwrites the row instead of shifting the rows below it, a delete leaves a hole, and a row inserted after a delete lands at the end, so `ticker.domBids` / `domAsks` fell out of price order (GRML 2026-09-22: 466 of 111,116 recorded books, 269 with a first bid or ask that was not the best). `ibkr/depth/book.py` keeps each line's book from `ticker.domTicks` with IBKR's row rules, reset on every depth request and on IBKR error 317 (depth reset); every Level 2 reader -- the ladder, Session Record quote and L2 rows, the tape gate, Time & Sales sides -- gets that book. A kept book found out of price order is sorted and logged once per line. Books recorded before this are read best-price-first (`sim/capture_player.book_at`, `l2/recall.book_before`); quote rows recorded from them are not rewritten.

### The tape archive never stops writing (operator report, 2026-09-24)

Owner `ibkr/tape_sink.py`. The L2 tape archive writer (`l2.db`
`tape_trades`, the prints Paper resting orders fill on) takes up to
`TAPE_RECORD_BATCH_MAX` prints per transaction off a queue of
`TAPE_RECORD_PENDING`. It **never latches**. A full backlog sheds the prints it
cannot hold (`backlog_full`) and a failed write loses that batch
(`write_failed`). Either way the loss is counted and stated, and the writer
takes prints again as soon as it can. `/api/l2/status` `tape.writer` is
`{error: string | null, pending, written, dropped, losing: boolean, losses:
[{cause: "backlog_full" | "write_failed", since, until: number | null,
dropped, symbols: string[], first_print_ts, last_print_ts, detail}]}`.
`losses` holds the newest `TAPE_RECORD_LOSS_KEEP` episodes, with `until: null`
while an episode is still open. `error` states an open episode or one that
ended within `TAPE_RECORD_LOSS_RECENT_SEC` (it also carries a shutdown that
timed out). `dropped` counts every print lost in this process. The Paper
matcher (and Sim at the live edge) reads resting orders' prints only as far as
the writer's written-through mark (`Sink.written_through`: every print
stamped earlier is written or counted lost), so a print the writer reaches late
is read next pass. `/api/diagnostics` adds the `tape_archive` row (group
`practice`, `evidence: {writer, resting, blind, unwatched, symbols}`):
`fail` while an order rests on a symbol whose prints are not reaching the
archive (the writer is losing prints now, the line prints with nothing
archived for over `TAPE_RECORD_STALE_SEC`, or the symbol is not archived),
`warn` on a recent loss or a blind symbol with nothing resting, `off` with
nothing archived. Before this fix, the first full backlog shed every print
until a restart. On 2026-09-24 that left every Paper resting order unfilled
from 07:29 ET: an APUS SELL limit at 4.96 sat while APUS printed 5.00.

### When IBKR data stops arriving (#672, #673, operator report 2026-10-01)

"There was a moment of lag, and that entire graph stopped working. Time and sales stopped ... This should
never happen." At the open the desk PC's Wi-Fi re-authenticated five times. Each time no IBKR data reached
Nova for 4, 4, 8, 16 and 4 s, while both loops stayed under 15 ms. The silences matched Windows' WLAN log
(11004 -> 11005) to the second. Nothing on the desk said why: the header read "STALE 0S" before and after.
Then everything IBKR held arrived in one burst, stamped on arrival (#563).

- **The heartbeat** (owner `ibkr/feed_pulse.py`, constants `constants_feed.py`). The L1, tick-by-tick and
  depth handlers call `note()`. A **gap** is a stretch with no market-data message on any line for at least
  `FEED_GAP_SEC` (3 s), after a busy stretch: data in at least 80% of the 10 whole seconds before it, not
  counting seconds inside an earlier gap. It must fall inside 04:00-20:00 ET of one exchange day, and an open
  gap also needs the Gateway session ready. A thin feed, the 20:00 close or a disconnect is never a gap.
  Gaps live in memory only.
- **`GET /api/ibkr/feed`** answers `{schema_version: 1, now, connected, in_session, last_data_ts, silent_sec,
  gap: Gap | null (open), recent: Gap[] (closed, newest first, at most FEED_GAP_KEEP), rule: {gap_sec,
  settle_sec, busy_window_sec, busy_fraction}}`. A **Gap** is `{start, end: number | null, silent_sec,
  ongoing, cause: "wifi" | null, wifi: {state: "read" | "pending" | "unknown" | "off", drops: [{stopped,
  back}]}, text}`. Times are epoch seconds, and `text` is the gap in plain words.
- **Wi-Fi** (owner `ibkr/wifi_drops.py`, read-only). Windows' WLAN AutoConfig log is read on a worker
  thread with `wevtutil`, never on a loop. Each 11004 "security stopped" pairs with the next 11005
  "succeeded". A drop that was down from 15 s before the silence to its end makes `cause: "wifi"`. A log that
  cannot be read is `unknown`, never "no drop"; off Windows it is `off`.
- **The desk** (`ibkr/feedPulse.ts`, `ibkr/feedPulseStore.ts`) reads the route once a second while it
  shows. The header chip reads **NO DATA 9s** (red) while a gap is open and **DATA GAP 16s** (amber) for 60 s
  after one closed, with `text` first on hover. Time & Sales' LIVE badge says the same. A replay desk leaves
  them out. The chip says **STALE** only when the newest scanner price is older than
  `SCANNER_PRICE_STALE_SEC`: an L1 subscription error with fresh prices (Error 101) is no longer
  "STALE 0s", and its words stay in the hover's scanner line.
- **The tape hold** (owner `setup_scanner/tape_gap.py`, pure). A live tape read reads `blind` with the gap as
  its reason when its window touches a gap. The gap runs from its last message to `FEED_GAP_SETTLE_SEC` (5 s)
  after the first one back. This covers the gate (`metrics.feed_gap`) and the flow reading (score `null`,
  `gap`, so no flush exit acts on a burst). A flow baseline starts again after a settled gap. The bot and
  Auto-entry skip such a trigger, and the skip line quotes the tape's first reason. Replays hand in no gaps.
- **`/api/diagnostics`** adds the `ibkr_feed_gaps` row (group `market_data`). It is `fail` while a gap is
  open, `warn` with the count and the longest in the last `FEED_DIAG_WINDOW_SEC` (30 min), naming Wi-Fi when
  Windows logged it, `off` while disconnected or outside the session, and otherwise `ok`.

### A Level 1 line IBKR refused (operator report 2026-10-05)

"Find out why 10 of the 50 after-hours rows never get a price." From 16:08 ET IBKR answered 176 Level 1
requests with Error 101 ("Max number of tickers has been reached") while Nova held 51-56 lines of its own: the
cap is the login's, and IBKR counts its other platforms against it (TWS and the API share it, per IBKR). ib_async 2.1.0 keeps a refused request
registered and hands it back to the next request for that contract, so the line stayed "subscribed" for good.
17 of the 50 After Hours rows had no price (INBS for 53 minutes), and Nova counted 76 of its 100 lines open.

- **A refused line is not open** (owner `ibkr/l1_refused.py`). Every Level 1 request id is kept with its symbol.
  Error 101 on a line's own id marks the line refused. It keeps its owners and handler (a Trader tab, the
  scanner, HOD Momo), but no longer counts as open, and is let go without a cancel (IBKR never opened it).
- **The cap Nova plans to.** The lines Nova held at the refusal become the cap (the fewest held within one
  burst of refusals). It rises by `IBKR_L1_CAP_RELAX_STEP` every `IBKR_L1_CAP_RELAX_SEC` without a refusal, and
  is forgotten at `IBKR_L1_STREAM_BUDGET`. The scanner plans within it, less the open lines no scanner or HOD
  owner holds (a Trader tab's own quote) and `IBKR_L1_STREAM_RESERVE`. Displayed rows come first and HOD Momo's
  other names get what is left, as before.
- **Asked for again.** The scanner's reconcile re-requests a refused line in place once its wait
  (`IBKR_L1_REFUSED_RETRY_SEC`: 15, 30, 60, then 120 s for refusals in a row within
  `IBKR_L1_REFUSED_RESET_SEC`) is over, and only while Nova holds fewer lines than the cap. A Trader tab's line
  goes first, then the displayed rows, then HOD Momo's.
- **On the wire.** `/api/ibkr/status`:
  - `reqMktData_lines` counts the open lines only;
  - adds `reqMktData_refused` (integer) and `reqMktData_cap` (`integer | null`, null while none is learned);
  - `reqMktData_remaining` is measured against the cap.

  The scanner subscription state (on `/ws/scanner` price patches) adds `refused: string[]` and
  `line_cap: integer | null`, and its `error` names the refused symbols. The desk shows that error in the
  header's scanner hover. The `market_data_lines` diagnostics row warns while any line is refused.

### When one tape line goes silent (#722, operator report 2026-10-05)

"time and sale is fully frozen". At 09:35:42 ET the AllLast lines of SAIQ (a Trader tab) and VEEA (a Session
Record) stopped together while both books kept updating, with no IBKR error and no farm notice. SAIQ's Time &
Sales sat on its last print under LIVE until about 09:42; its socket's only frame was the idle `ping`. Level 1
kept arriving, so this is not a feed gap (above).

- **The reading** (owner `ibkr/tape_silence.py`, memory only): `{schema_version: 1, state: "halted" | "silent"
  | "quiet", since, last_print_ts, book_at, halted, text}` or `null` while the line prints.
  - The facts are the line's last print and opening (`tape_recording.producer_status`), when its Level 2 line
    last delivered a book (`ibkr/depth/state.last_book_at`, stamped by the depth handlers) and
    `halt_status.halted_now`.
  - `halted`: a halt prints nothing, so it is never read as a dead line.
  - `silent`: no print for `TAPE_SILENT_SEC` (30) while a book came within `TAPE_SILENT_BOOK_FRESH_SEC` (10):
    the line may be down.
  - `quiet`: the book is quiet too, or there is no Level 2 line.
  - The silence counts from the newest of the last print, the line's opening and the last ping that found the
    symbol halted. Nothing here asks IBKR for anything.
- **The wire.** Each idle `ping` on `/ws/ibkr/tape/{symbol}` (every `TAPE_STREAM_HEARTBEAT_SEC` without a
  print) carries `silence: reading | null` on a live line, and `null` on a replay desk.
- **The desk** (`ibkr/tapeSilence.ts`). The badge reads SILENT 47s or HALTED (amber), or QUIET 47s (grey),
  counting on the desk's clock, with the backend's words on hover. For the first two, a short line above the
  rows says why. Any print clears it, and NO DATA on every line (#672) comes first.
- **Not done here:** why a line goes silent, and what brings it back. Asking IBKR again did not bring VEEA's
  back that morning; SAIQ's came back without a new request.

### Orders refuse a stale view; the market path stays real time (ADR 045, operator report 2026-10-05)

"If it lags, then we cannot place an order." At 08:30:25 ET the operator sold APUS at a 6.58 bid their Level 2
had shown since 08:30:18-21 (Nova's own book was 6.50 x 6.55 by then; Time & Sales showed 08:30:20 as newest);
the order reached the backend 2-3 s after the click and rested above the market.

- **Versions** (owner `market_view/versions.py`, memory only). Each symbol's Level 2 book (`book`) and quote
  (`quote`) has a version: `seq` (an integer, +1 per change, never reset while the process runs) and `at`
  (epoch seconds when Nova applied it), with the last `MARKET_VIEW_HISTORY_KEEP` versions kept so the gate can
  tell when any `seq` it is shown was replaced.
- **Level 2** (`/ws/ibkr/depth/{symbol}`). Each viewer holds the newest book only, never a backlog, plus a
  short FIFO of control frames; the IB thread wakes the socket's loop thread-safely, once per burst. A book is
  pushed only when its rows changed (an L1 tick or a print on the same contract no longer re-sends it).
  - `{"type": "subscribed", "symbol", "instance"}` -- `instance` is the backend process (`/api/health`
    `instance_id`).
  - `{"type": "book", "symbol", "data": {bids, asks, l1_fallback}, "seq", "at", "sent"}` -- `data` unchanged.
  - `{"type": "beat", "symbol", "seq", "at", "now"}` every `MARKET_VIEW_BEAT_SEC` (0.25) without a book frame:
    the line's newest version (`seq` 0 and `at` null before its first book) as of `now`. It replaces the
    15 s `ping`.
- **Time & Sales** (`/ws/ibkr/tape/{symbol}`). Each viewer's prints wait in a thread-safe FIFO
  (`IBKR_TAPE_QUEUE_MAXSIZE`, oldest dropped and counted in `tape.viewer_dropped`) with the same wake-up; two or
  more waiting prints go as one `{"type": "prints", "symbol", "items": [print...], "sent"}` frame, a single one
  as the `print` frame it was.
- **Quote** (`/ws/ticker/{symbol}`): `trade_update` adds `seq` and `at`, the symbol's quote version.
- **The view an order carries.** `POST /api/ibkr/order` and `PATCH /api/ibkr/order/{id}` accept `view:
  {schema_version: 1, symbol, action_wall_ms, instance: string | null, book: {seq, at, bid, ask} | null, quote:
  {seq, at, price} | null, desk: {silent_ms, transit_ms, undrawn_ms} | null}` -- when the operator acted
  (epoch ms), the Level 2 book and the quote the screen showed (null when it showed none), and the desk's own
  measures at that moment. The desk attaches it to every order it sends (`ibkr/placeOrder.ts`).
- **The gate** (owner `market_view/gate.py`; constants `constants_market_view.py`). For a `manual` place,
  bracket or replace that came through those routes (it carries `client_timing`), the execution door refuses,
  after the duplicate-key replay and before anything is validated or sent, HTTP 200 `{ok: false, reason_code,
  error}` like its other refusals:
  - `VIEW_STALE`: the book or quote the screen showed had been replaced for more than `ORDER_VIEW_MAX_LAG_MS`
    (500) at `action_wall_ms` (`lag = action - at(seq + 1)`), a `seq` older than the kept history, a `seq` past
    the newest, or an `instance` that is not this process;
  - `ORDER_LATE`: the door saw it more than `ORDER_MAX_ARRIVAL_MS` (500) after `action_wall_ms`, or the broker
    send would leave more than `ORDER_MAX_SEND_MS` (750) after it -- checked again just before the send, and
    on Live by the IB loop as it sends (`gate.send_deadline`, below);
  - `FEED_STALE`: an IBKR feed gap is open or settling (`ibkr/feed_pulse`), or the IB loop is stalled now for
    more than `ORDER_MAX_IB_STALL_MS` (500) (`perf/stall_watch.stalled_ms`) -- never on a Sim desk off the live
    edge, whose market is the replay;
  - `VIEW_MISSING`: no `view` (an older desk).

  The protective sources (`flatten`, `kill`, `cancel_working`), cancels and every command without
  `client_timing` (the bot, stock modes, the breakers) are exempt. The arithmetic mixes the desk's and the
  backend's wall clocks, sound because the backend binds 127.0.0.1; an action more than 1 s in the backend's
  future is `VIEW_STALE` ("the clocks disagree"). The execution row's payload keeps `view` and `view_check:
  {schema_version: 1, verdict: "ok" | "refused" | "exempt" | "missing", code, arrival_ms, book_lag_ms,
  quote_lag_ms, feed_gap: boolean | null (null on a replay desk), ib_stall_ms}`.
- **The desk locks first** (owner `frontend/src/market_view/`). A symbol's view is stale while its Level 2 has
  had no frame or beat for `VIEW_SILENT_LOCK_MS` (750), a frame took more than `VIEW_TRANSIT_LOCK_MS` (500)
  from `sent` to arrival, or a received book has not been drawn for `VIEW_UNDRAWN_LOCK_MS` (500). Then Place,
  the quick bar's and the hotkeys' priced actions and Fill now are locked with the reason (`data-why`); Flatten
  and cancels never are. No age readout: locked or live.
- **The Live send awaits the IB loop, and goes out once or never** (#725; owners `ibkr/send_hop.py`,
  `execution/live_send.py`). A Live place, replace or bracket runs its whole `ibkr.orders` call on the IB loop
  while the socket loop keeps serving every socket (`call_on_ib` blocked it for as long as the IB loop was busy,
  up to 15 s). One lock both loops take decides whether it went out:
  - the IB loop starts a send only while its caller still waits;
  - a caller that gives up marks a send not yet started abandoned, and it is never sent: refused
    `IB_LOOP_WEDGED` after `IBKR_SEND_HOP_TIMEOUT_SEC` (15), or `ORDER_LATE` past the desk order's deadline,
    which the IB loop enforces as it sends and at which the caller stops waiting;
  - a send already running reached IBKR and is awaited to its end. One that has not finished within
    `IBKR_SEND_RUNNING_GRACE_SEC` (30) is `SEND_UNKNOWN`: Nova says it cannot tell.

  The order's watch is registered in the IB-loop callback that placed it, and the order id joins its in-flight
  commitment there, so no status can arrive unheard and a fill heard first still frees the shares.
  `OrderWatch`'s ack and fill wake their waiter from any thread at once (an `asyncio.Event` set from the IB
  thread is not thread-safe and woke nothing). IBKR's order events are wired at READY on the IB loop
  (`ibkr/session_usable.py`); the order path's own wiring awaits too and refuses `IB_LOOP_WEDGED` past
  `IBKR_ORDER_EVENTS_WIRE_TIMEOUT_SEC` (5).
- **Nothing slow on the socket loop.** `ibkr/gateway_process.py` reads Windows' process list and listening
  ports in-process (no `tasklist`; the Gateway is the `java.exe` IBC launches, or an `ibgateway*` / `tws*`
  image); `paths.cache_dir()` / `log_dir()` create their folder once; the Closed blotter's place overlay is
  read again only after the ledger is written (`execution/place_overlay.py`); the IBC log and the gateway trail are re-read only when
  their file changed; a Time & Sales subscribe warms its 10-second bars off the loop.
- **Priority** (owner `process_priority/`, Windows only). The backend raises itself to Above Normal, opts out
  of Windows power throttling and keeps normal memory and I/O priority at start and every
  `PROCESS_PRIORITY_RECHECK_SEC` (2); its IB and socket loop threads run Above Normal; it keeps IB Gateway's
  process at Above Normal and IBC's launch loop, whose relaunch the Gateway inherits, at Normal. Nothing is lowered; a priority found lowered is raised and
  logged. `/api/diagnostics` adds the `process_priority` row (group `process`), `evidence: {processes: [{role:
  "api" | "gateway" | "ibc_loop", pid, name, priority, raised, error}]}`. The desk's Electron main raises its
  own and its desk windows' processes (`frontend/electron/processPriority.mjs`).
- **Freezes** (owner `perf/freeze_watch.py`). A C-level watchdog (`faulthandler`) re-armed every 0.5 s dumps
  every thread's stack when the process stops for `PERF_FREEZE_DUMP_SEC` (2), to
  `<cache_dir>/perf/freezes/YYYY-MM-DD.txt`, and `freezes.jsonl` beside it logs `{schema_version: 1, armed_at,
  noticed_at, frozen_sec, file, offset}` per dump. `/api/diagnostics` adds `perf_freezes` (group
  `performance`). Perf samples' `process` adds `page_faults` (in the interval) and `working_set_mb`, and `gc`
  adds `pause_ms_by_gen` and `max_pause_ms_by_gen`.

### The trading session ends at 20:00 ET (operator report, 2026-10-01 23:33)

"How come these things are getting triggered right now? ... the entire market is closed, no?" -- the Bots
page showed OM's first pullback and flat top forming ("new high 4.20 on a 12% leg"), NAMM's bull-flag pole and
RIBBU / XRPNU "pushing HOD". After the 20:00 close IBKR keeps the same SMART Level 1 lines moving with its
overnight session (20:00-03:50 ET, its OVERNIGHT venue; IBKR dates those trades to the next trading day): the
last moves while IBKR's own day volume and day high stand still (XRPN printed 27.49 over a 23.99 day high).
Nova made each of those prints a one-minute candle and a HOD Momo trade (78 HOD Momo alerts after 20:00), and
the setup scanner's day ran to midnight with no close: OM's leg was one 200-share print at 20:48, RIBBU's a
15:52 move nothing had ended, and after midnight the same prints began the next day (red to green read a 23:59
print as "the 09:30 open" and armed SDEV at 00:12).

- **One rule** (`market.trading_session_bounds` / `in_trading_session`, pure): Nova's trading session is
  04:00-20:00 ET on an exchange day (a weekday that is not an NYSE holiday; half-days are not modelled).
- **Candles.** `ibkr/l1_minute` makes a minute only from a last inside the session; outside it a last opens no
  bucket, reaches no listener and drops the volume baseline, so the next session's first print is a baseline.
  The `ibkr_l1` minutes already stored between 20:00 and 04:00 stay in `bars_intraday`.
- **HOD Momo, its L1 tick archive and volume boost** take only trades inside the session (`ibkr/l1_apply`,
  beside #541's prior-close rule). The rows' price patch still carries the line's last.
- **The setup scanner's day is the session** (`setup_scanner/engine.py`). A minute or price outside it is not
  read; the seed reads 04:00-19:59 (`hooks.default_seed`: the newest 960 rows had let overnight minutes push a
  busy morning out). From 20:00 every lane ends its day on each tick: a setup still forming goes back to
  `watching` and an armed or near one is disarmed, its open proposal withdrawn, with the reason
  `SETUPS_SESSION_CLOSED_REASON` ("the session closed at 20:00 -- the scanners start again at 04:00"),
  journalled, so the playback and the past setups end it there too. A restart after the close replays the day
  and ends it the same way.

### Chart bars say when IBKR history stopped answering (ADR 012, #555)

`GET /api/ticker/{symbol}/bars` on the IBKR store-first path (not a Sim replay, not Alpaca) and every `bars_patch` frame on `/ws/ticker/{symbol}` carry, in `coverage` beside `filling`, `last_error: string | null` and `last_error_ts: number | null` (epoch seconds): the backend's reason and time for the last historical fetch of that (symbol, timeframe) that IBKR did not answer -- a timeout (504) or an error answer / failed qualify (502), never a Gateway-down 503 or a 400 / 404. Both are `null` when there is none; a success clears the pair at once, and a failure nobody has asked about again is forgotten after `IBKR_HISTORICAL_FAILURE_MEMORY_SEC` (owner `ibkr/historical_failures.py`, in memory only, never stored in `bars_coverage`). A failed pair is not sent to IBKR again, for any priority, for `IBKR_HISTORICAL_FAILURE_BACKOFF_SEC`: the request is shed and the pane's own retry asks again, so a farm outage stops spending the 60 / 10 min budget. A pane with no bars that is filling with `last_error` set reads "IBKR history did not answer — retrying" with the reason, not "Loading IBKR historical…"; a painted pane's header hint says the same.

**A crashed pane says why** (operator report, 2026-09-25: "Chart unavailable. The scanner is still running."). A chart pane that crashes (`components/TickerChartErrorBoundary.tsx`) shows the error's own words under that line and reports its timeframe (`source: "ticker-chart:1Min"`). It draws itself again once, after `CHART_CRASH_AUTO_RETRY_MS`; a second crash within `CHART_CRASH_AUTO_RETRY_WINDOW_MS` stays down. Its Retry button now takes the click. It had inherited the overlay's `pointer-events: none`, which passes clicks through to the chart, so it could never be pressed.

### The forming candle's volume (operator report, 2026-09-24)

"i do not see a volume coming up": a chart pane draws its forming candle from
`/ws/ticker/{symbol}` `trade_update` frames, which carry a price and the day's
running volume (`volume`: IBKR's RTVolume total, else tick 8) but no bar. The
bar store refreshes from IBKR history at most every
`IBKR_BARS_STORE_FRESH_INTRADAY_SEC` (the pane asks every `CHART_REFETCH_SEC`),
so the forming bar's volume used to appear only after the bar closed. Minute
and hour panes now count it on the desk (`chart/liveTradeApply.ts`): a bar's
volume is what the day volume grew by between its first update and its last.
The first day volume a pane sees is a baseline, so the bar it joined mid-way
has no live count -- the store's figure, or nothing, never a partial one. A
total that goes down restarts the baseline and leaves that bar unknown. Updates
arrive on price changes, so shares traded at an unchanged price just before a
bar closes count in the next bar; the store's bar replaces a closed bar's figure
when it lands, and a forming bar shows the larger of the two counts. 10Sec
volume stays the tape's own prints and daily volume the store's. No wire field
changed. A store refresh no longer rebuilds the forming candle from the last
trade (which flattened its open, high and low to one price every 30 s): the
live tip is put back on top, merged with the store's bar for the same minute.

### Why it's moving (ADR 028, operator ask 2026-09-23)

`GET /api/why/{symbol}` (owner `backend/move_reason/`, read-only, no network wait; rules
`move_reason/rules.py`, pure, thresholds in `constants_move_reason.py`) answers the Trader tab's
"Why it's moving" section: `{schema_version: 1, symbol, generated_at, session_date, rules_version,
likely: {kind: "not_moving" | "news_pending" | "news" | "short_squeeze" | "routine_news" |
"split_squeeze" | "low_float_momentum" | "thin_trading" | "unexplained", label, detail,
confidence: "likely" | "possible"}, checks: [{id: "news" | "halts" | "float" | "float_rotation" |
"reverse_split" | "short_interest" | "borrow" | "volume", label, state: "yes" | "no" | "unknown",
value: string | null, detail: string | null, source, as_of: number | null}], facts: {price,
change_pct, volume, rel_volume, float_shares, float_contradicted, float_rotation, short_interest,
short_interest_ts, short_above_float, short_pct_float, days_to_cover, split: {factor, ts, reverse,
days_ago} | null,
halts: {news, luld, volatility, other, source} | null, borrow: {listed, fee_rate, rebate_rate,
available, available_capped, as_of, since, open, prior, max_fee_today, min_available_today} | null,
catalyst: verdict | null, shares_issued: {published_ts, source, form, items, title, url} | null}}`.
`shares_issued` is the filed share issuance of "Float credibility and short-interest dates" (#700); while
one is on file the float and float-rotation checks read `unknown` ("631K? shares", "Float traded 82x?")
with the filing named in their `detail`, because Yahoo's float and share count predate it -- so the
likely cause is never low-float momentum on a float the filings say is out of date. The
news check's `detail` names the verdict's `prior_session` item while today's window holds no catalyst,
and the likely cause then says "no company news since the prior close" and names it. `price` / `change_pct` / `volume` are the scanner row's, repriced by the
symbol's L1 line when it holds a trade (`move_reason.facts.with_live_trade`; never IBKR's prior close
before the first trade): a board stops repricing a row when its session ends (XRPN 2026-09-30 read
16.40, its 16:00 price, while it traded 17.11 after hours, so the stock read judged every level against
the close). `float_contradicted` / `short_interest_ts` are the scanner row's (#532,
"Float credibility and short-interest dates"); a contradicted float's check reads "54K? shares"
with the reason as its `detail` and keeps its state, and the short-interest check's `as_of` is the
FINRA settlement date. `short_above_float` is judged on the float and short interest shown here; when
it is `true` the short-interest check's `detail` adds its reason and its state is unchanged (a
warning, never a gate). `days_to_cover` is Yahoo's short ratio and its value says "(Yahoo ratio)".
`fee_rate` / `rebate_rate` are IBKR's annual percent; `open` / `prior` are `{listed, fee_rate,
available, as_of}` at the day's first poll at or after 04:00 ET and the last poll before it (null
when not recorded); `since` is the first poll the store holds. A symbol IBKR's file does not list is
`listed: false` (nothing to lend). Every unknown is `null` and its check `unknown`, never guessed;
`confidence` is `possible` when a deciding input is unknown. Descriptive only: nothing places or
gates on it.

The borrow feed (`move_reason/borrow_feed.py`, always on; `NOVA_BORROW_FEED=0` off) polls IBKR's
public short-stock file (`ftp://ftp2.interactivebrokers.com/usa.txt`, USD rows) every
`MOVE_BORROW_POLL_SEC` into `<cache_dir>/move_reason/borrow.sqlite3` (owner
`move_reason/borrow_store.py`; `PRAGMA user_version = 1`, unknown versions refuse): `polls (ts,
file_ts, rows)` and `changes (symbol, ts, listed, fee_rate, rebate_rate, available, capped)` -- a
row only when a symbol's listing, fee or availability changed, pruned after
`MOVE_BORROW_RETENTION_DAYS`. `/api/diagnostics` adds the `borrow_feed` row (group `recorder`).

### The Cryptos page (ADR 040, operator ask 2026-09-30)

"give us a new tab called Cryptos ... what a person needs to see in the crypto world", then mockup v1
approved ("go ahead and build exact replica"). Owners `backend/crypto/` (read-only; constants in
`constants_crypto.py`) and `frontend/src/cryptos/`. Nothing here places, stages or cancels an order, and
nothing here feeds a scanner row, a stock's chart, HOD Momo, a setup lane or a bot. Percentages on this
page's wire are percent points (`2.84` = +2.84%), never fractions.

`GET /api/crypto/board` answers `{schema_version: 1, generated_at, enabled, loading, replay_desk, clock,
market, coins[], leverage, flows, bridge, next[], news[], sources[]}` from memory; asking marks the board
wanted for `CRYPTO_WANTED_SEC` and never waits on the network. `loading` is true until every source has
answered (or failed) once since it was wanted; `enabled` is false with `NOVA_CRYPTO=0`.
- `clock`: `{now, stock_session: "premarket" | "regular" | "after_hours" | "closed", stock_next: {kind:
  "premarket" | "open" | "close" | "after_hours_end", at}, crypto_day_start (the last 00:00 UTC),
  crypto_day_start_et ("HH:MM"), regions: {asia, europe, us} (that region's market hours by the clock),
  next_funding (the next 00:00 / 08:00 / 16:00 UTC settlement of the 8-hour exchanges), lanes: {asia, europe,
  premarket, regular, after_hours, funding}}` -- each lane `[[from, to], ...]` in minutes after ET midnight of
  today's ET date (Asia and Europe from their own clocks, weekdays; the stock lanes empty on a closed day; funding
  as `[m, m]`). The clock's own facts, no source.
- `market`: `{total_cap_usd, total_cap_change_24h_pct, btc_dominance_pct, btc_dominance_change_24h_pt,
  total_volume_usd, volume_x_30d, fear_greed: {value, label, week_ago, at} | null, eth_btc,
  eth_btc_change_24h_pct, btc_qqq_corr_30d}` -- CoinGecko's `/global` and `/coins/markets`; the dominance
  change is BTC's share 24 hours ago worked out from both answers' 24-hour changes; `volume_x_30d` is the
  listed coins' 24-hour volume over their own 30-day daily average (not the whole market's); Fear & Greed is
  alternative.me's; `btc_qqq_corr_30d` is the correlation of BTC's 16:00 ET-to-16:00 ET returns with QQQ's
  regular-hours closes over the last 30 shared sessions.
- `coins[]` (the `CRYPTO_COINS` table, rank order): `{symbol, name, rank, price, high_24h, low_24h,
  change_1h_pct, change_24h_pct, change_7d_pct, volume_24h_usd, volume_x_30d, market_cap_usd,
  from_ath_pct, spark_7d: number[], funding_8h_pct, groups: string[], why, news_checked, ibkr, etf,
  chart}`. `volume_x_30d` is the 24-hour volume over the coin's 30-day daily average (CoinGecko's
  `market_chart`, refreshed every `CRYPTO_VOLUME_HISTORY_TTL_SEC`). `funding_8h_pct` is Hyperliquid's hourly
  rate x 8. `why` is `{kind: "catalyst" | "negative" | "noise" | "news", title, source, published_ts, url} |
  null` -- the best Alpaca headline naming the coin in the last 24 hours, labelled by `crypto/classify.py`
  (rules `CRYPTO_NEWS_RULES_VERSION`); `news_checked` is true once Alpaca answered for the coin, so
  `why: null` with `news_checked: true` is "no news found" and with `false` is unknown. `ibkr` is `{listed,
  venue: "PAXOS" | "ZEROHASH" | null} | null` -- IBKR's own contract answer, `null` until asked (IBKR not
  ready). `etf` is the coin's US spot ETF on the desk (`IBIT`, `ETHA`) or `null`. `chart` says Coinbase
  carries a USD market for the candles route.
- `leverage`: `{funding: [{symbol, funding_8h_pct}] (high to low), open_interest_usd (the listed coins,
  Hyperliquid), btc_open_interest_usd, liquidations_24h: null, liquidations_note}` -- liquidations have no
  free source reachable from the desk and stay a stated absence.
- `flows`: `{etf: null, etf_note, stablecoins: {supply_usd, change_7d_usd, daily: [{date, net_usd}]} | null}`
  -- daily spot ETF flows have no free source and stay a stated absence; stablecoins are DefiLlama's USD-pegged
  supply and its daily change.
- `bridge`: `{reference_close_at (the last regular-session 16:00 ET close), phase: "premarket" | "regular" |
  "after_hours" | "overnight", btc_since_close_pct, eth_since_close_pct, rows: [{symbol, what, driver: "BTC" |
  "ETH", beta, close, last, since_close_pct, implied_pct, read: "ahead" | "behind" | "in_line" | null,
  gap_pt}], error: string | null}` for `CRYPTO_BRIDGE` (IBIT, ETHA, MSTR, COIN, MARA, RIOT, CLSK, HOOD).
  `close` is IBKR's regular-hours daily close of that session (`historical_service.request_rth_daily_closes`,
  background priority), `last` IBKR's snapshot (`snapshot_quotes`, cold), `null` when IBKR has not answered
  (a snapshot with no trade since that close is `null`, never the close). `beta` is the least-squares slope of
  the stock's close-to-close returns on the driver's 16:00 ET-to-16:00 ET returns over the last
  `CRYPTO_BETA_DAYS` shared sessions (`null` under `CRYPTO_BETA_MIN_DAYS`); `implied_pct` is the driver's
  move since the close x beta; `read` is `ahead` / `behind` when `since_close_pct - implied_pct` (`gap_pt`)
  is beyond `CRYPTO_BRIDGE_READ_BAND_PT`, else `in_line`, `null` when either is unknown. The driver's 16:00 ET
  prices are Coinbase's (the open of the hourly candle that starts at 16:00 ET).
- `next[]`: `{at, kind: "funding" | "expiry" | "stocks" | "crypto_day", title, detail: string | null}`,
  soonest first, at most `CRYPTO_NEXT_MAX` -- the clock's events, and Deribit's options expiries (every
  Friday 08:00 UTC; the month's last Friday is the monthly) with the BTC open interest expiring then when
  Deribit answered. No macro calendar or token unlocks: no free source.
- `news[]`: `{published_ts, symbol, kind, title, source, url}`, catalysts and negatives first, then newest,
  at most `CRYPTO_NEWS_MAX`.
- `sources[]`: `{id: "coingecko" | "coinbase" | "fear_greed" | "hyperliquid" | "defillama" | "deribit" |
  "alpaca" | "ibkr", label, ok: boolean | null, at: number | null, error: string | null}` -- `ok: null`
  until asked. A failed source keeps its last good answer for at most `CRYPTO_STALE_MAX_SEC`, then its
  numbers read `null`; no source's numbers ever stand in for another's.

`GET /api/crypto/candles?symbol=BTC&tf=15m` (`tf`: `15m` | `1h` | `4h` | `1d`) answers `{schema_version: 1,
symbol, tf, product, source: "coinbase", loading, error, candles: [{t, o, h, l, c, v}] (oldest first, `t` the
bucket start, `v` null when Coinbase gave none), last, change_24h_pct, levels: {high_24h, low_24h, day_open,
day_open_at, stock_close: {at, price} | null}, sessions: [{kind: "premarket" | "regular" | "after_hours",
start, end}]}` -- Coinbase
Exchange's public candles (4h built from hourly), the levels from the 15-minute series, the US stock sessions
inside the window; 400 `CRYPTO_UNKNOWN_SYMBOL` / `CRYPTO_UNKNOWN_TF`. Nothing is fetched on the request:
it answers the cache (`loading` while the first read runs) and asks the refresher.

Refresh while wanted (`backend/crypto/refresh.py`, two daemon threads, web and IBKR): CoinGecko markets
every `CRYPTO_MARKETS_TTL_SEC`, global every `CRYPTO_GLOBAL_TTL_SEC`, volume history one coin at a time;
Hyperliquid every `CRYPTO_PERPS_TTL_SEC`; Alpaca news every `CRYPTO_NEWS_TTL_SEC`; Fear & Greed,
DefiLlama and Deribit every `CRYPTO_SLOW_TTL_SEC`; IBKR snapshots every `CRYPTO_BRIDGE_QUOTE_TTL_SEC`, daily
closes once per session (again after 16:00 until that session's bar lands), the crypto listing once per
process. Nothing polls when the page has not asked within `CRYPTO_WANTED_SEC`. `COINGECKO_DEMO_API_KEY`
(optional) is sent as CoinGecko's demo key. On the desk every number, chip, level and lane opens a hover
card (`frontend/src/cryptos/tips/`): what it means, a small drawing, what it reads now, why it matters.

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

### The operator's watch list and its toasts (operator asks, 2026-09-23 and 2026-09-24)

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

### The close-of-day reminder (operator ask, 2026-10-01)

Owner `frontend/src/close_reminder/`, mounted once with the app bar (never on the sample desk). At
15:50 ET a card per Paper or Live position still open ("Still holding 500 GRML at 15:50 -- be flat by
15:55"), escalated at 15:55 ("close it now", pulsing), gone at 16:00; a position that goes flat
takes its card with it. Once per position per day per stage: a dismissed card does not return at
its stage. Sim is left out (its clock is the replay playhead); weekends too; there is no holiday
calendar on the client. `localStorage` `nova.closeReminder.fired` (a `prefStore` envelope) holds `{schema_version: 1, date:
"YYYY-MM-DD" (ET), keys: ["<date>|<venue>|<SYMBOL>|<warn | final>", ...]}`; another date or an unknown
version is ignored. On Live the rows may be last-known (the Gateway dropped) and the card says so.
Nothing here places, stages or cancels an order.

### Short selling (ADR 048, operator decisions 2026-10-01 to 2026-10-07; #778)

"Short selling: Paper and Sim first, Live last" -- built in six steps under #778 (ADR 048 "The build"),
each safe alone. This section says what is on master; ADR 048 is the whole design and ADR 049 the five
short strategies, pre-registered.

- **The one short check** (owner `short_sale/door.py`, run by `execution.validate.check_account_and_position`
  under the execution lock for every place or bracket carrying `short_entry`). In order, the first failure
  refuses with its rule, its numbers and its fix:
  1. the Live key, `IBKR_SHORT_ENABLED` (`SHORT_DISABLED`, ADR 009);
  2. a short entry is a SELL and a limit -- a place's `limit_price` on a `LMT`, a bracket's `entry_price`
     (`SIDE_INVALID`, `SHORT_NEEDS_LIMIT`);
  3. never while the account holds the stock long (`SHORT_WHILE_LONG`: Nova never flips);
  4. a margin account (`account_class: "margin"`, `SHORT_NOT_MARGIN`) with at least $2,000 of equity
     (`SHORT_EQUITY`); unreadable equity is `SHORT_MARGIN_UNKNOWN`;
  5. borrow: the cached tick-236 read, fresh and `shortable_est`, covering this order plus the shares
     already short plus the short entries in flight (`SHORT_STALE_BORROW`, `SHORT_NOT_SHORTABLE`,
     `SHORT_BORROW_TOO_SMALL`);
  6. margin by the published rules (`short_sale/margin.py`, labelled "published rules"; constants
     `constants_shorts.py`): a short's maintenance is $2.50 a share under $2.50, 100% of value to $5,
     $5 a share to $16.67 and 30% above, a long's 25% of value. The account's maintenance now is IBKR's own
     on Live (`NetLiquidation - ExcessLiquidity`) and the published rules over the ledger's marked
     positions on a practice venue; shorts in flight elsewhere add theirs at their limits. `SHORT_MARGIN`
     when the requirement does not fit at the entry, `SHORT_CUSHION` when IBKR would liquidate within a
     25% move against the short (the liquidation price, where equity meets maintenance with every other
     position held still, under `entry * 1.25`).

  Paper and Sim still refuse every opening short `PRACTICE_NO_SHORTS` (`execution/practice_checks.py`)
  before this check; ADR 048's step 2 teaches them.
- **Borrow never under the lock.** The door reads `ibkr.shortability.for_order(symbol)` -- the cached read,
  never IBKR -- before it takes its lock; a missing or stale read asks IBKR on a worker thread
  (`request_refresh`, `IBKR_SHORTABILITY_REFRESH_WORKERS`) and the short is refused with the fix ("place the
  short again in a moment"). An open Trader tab's ticker socket re-reads a known state every
  `IBKR_SHORTABILITY_REFRESH_SEC` (20 s), under the 60 s TTL, and an unknown one every 30 s.
- **Shorts in flight.** A short entry, a place or a bracket, is committed in `execution.inflight` as side
  `SHORT` with its limit (never as `SELL`: it spends no long, so a closing sell keeps its shares) until its
  order resolves; the borrow and margin checks count it.
- **A cover is a close.** A BUY place while the account is short the stock (`execution.position_checks.covers_short`)
  is held to the short less the covers in flight (`OVERCOVER`) and never to buying power, and the all-stop's
  day lock never refuses it (`bot.buy_lock.buy_refusal(..., covers=True)`). A position Nova cannot read is no
  cover: the BUY then meets buying power and the position check, as before.
- **Order rows say what they are.** Working and closed order rows add `short_entry: boolean | null` --
  Nova's record that the row is the SELL it sent as a short entry: a practice row stamps it when placed, a
  Live row takes it from the execution row that sent it (`execution/sent_by.py`; a bracket's BUY exits read
  `false`); absent or `null` when not recorded. Practice rows also add `position_side: "long" | "short"` and
  `effect: "opens" | "closes"`, what the order does to the position as placed (`practice.order_rules.side_fields`;
  a bracket's exits close what their entry opens). **Fill now** refuses a row with `short_entry: true`
  before it cancels anything: it would re-send the short without its buy stop.
- **Never past flat at the fill.** The practice broker cancels a cover that would buy past the short when its
  print arrives (`PRACTICE_OVERCOVER`: "A cover never buys past flat: Nova never turns a short into a long"),
  as it cancels a SELL past the long (`PRACTICE_NO_SHORTS`, QA R42).
- **Freeze all orders keeps protective stops** (`kill_switch/sweep.py`). A working stop (`STP`, `STP LMT`,
  `TRAIL`) on the side that closes a position the venue holds -- a SELL stop under a long, a BUY stop over a
  short -- no larger than that position stays resting; a bracket exit still waiting on its entry protects
  nothing and is cancelled with it. Each venue's sweep adds `kept: [{order_id, symbol, side, qty, order_type,
  stop_price, why}]` and the trip's answer `kept_order_ids`; positions Nova cannot read keep no stop, and the
  venue's `note` says so. The header's red KILL, which flattens, still cancels everything first.

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
 "intent": null,
 "expected_venue": null,
 "origin": null
}
```

**Who sent it** (operator report 2026-10-01: "Could you see who sold here? I don't remember selling it." -- the Paper bot trip sold 100 ACN, and the row read like any other market sell, because the ticket's Flatten, the header's KILL, both loss breakers and the bot's own last-resort exit all send source `flatten`). `origin` names which part of Nova sent an order, one of `constants_nova_os.EXECUTION_ORIGINS`: `ticket_flatten` (the ticket's, quick bar's or a hotkey's Flatten), `emergency_kill` (`POST /api/ibkr/flatten-account`, the header's KILL), `bot_trip` / `all_stop` (the loss breakers' flatten), `bot` (Nova's bot: entry, exits, last-resort close), `auto_entry`, `approve` (Who trades the stock) and `bot_api` (the localhost bot API); `null` for the operator's own ticket. A label, never a permission: no gate reads it. The execution record's payload keeps it, a practice order row (Paper / Sim, working and closed, every bracket leg) carries it as `order_origin` beside `order_source`, and a Live row -- working (`GET /api/ibkr/orders`) or closed (`execution/closed_blotter.py`) -- takes both from today's execution row for this desk that sent it (`execution/sent_by.py`, #677: by permId, else order id, the symbols agreeing; a bracket's exit legs share their entry's sender, so a closed leg reads Nova's, not "Outside Nova"); a Live row no execution row claims carries neither. A row placed before 2026-10-01 has `order_origin: null`: a `flatten` there could be any of the five, and the desk says so rather than guessing. The Working and Closed order tables add a **Sent by** column (`frontend/src/ibkr/orderSentBy.ts`: You, You · Flatten, KILL, Bot trip, All-stop, Bot, Auto-entry, Approve, Bot API, Outside Nova; a breaker's or KILL's in amber), its reason on hover; a layout saved before it gets the column where the defaults put it (after Status), not off the far edge.

`STP LMT` requires both `limit_price` and `stop_price`. `TRAIL` uses `stop_price` as the IBKR trail dollar amount (`auxPrice`); trail percent is not a ticket field. `tif` defaults to `DAY` (`IBKR_ORDER_TIF_DEFAULT`), so a caller that omits it is unchanged; anything outside `DAY | GTC` is refused `TIF_INVALID`. `place` and every `bracket` leg carry `tif` and `outside_rth`; `replace` keeps the working order's own TIF. **Market orders need regular hours** (operator decision, 2026-09-21): a `MKT` place from a non-protective source is refused `MKT_OUTSIDE_RTH` ("use a limit at the ask") whenever the venue's clock is outside weekday 09:30-16:00 ET, NYSE holidays excluded -- no US exchange takes an unpriced order then and IBKR would hold it until the next open (Warning 399) while ignoring `outsideRth` on it (Warning 2109). The clock is the venue's (the replay playhead on Sim). Owner `execution/session_gate.py`; the practice broker repeats the check (`practice/order_rules.py`). Protective sources are exempt (flatten plans an extended-hours limit); `STP` orders are unchanged.

**The ticket's Flatten** (QA R32 / R42, 2026-09-22): `POST /api/ibkr/order` may carry `intent: "flatten"` -- the rail's Flatten, the quick-bar Flatten and the `exit_pos` / `cancel_and_exit` Nova Actions send it. The route sends it as source `flatten` with `ExecutionCommand.intent: "flatten"` (a protective source: never clamped by the test quantity gate and placeable while disarmed, like KILL), and the execution door accepts it, inside the execution lock, only when it closes shares not already being closed -- the side reduces the venue's own position, and the size does not exceed that position less the closing orders already working on the venue (open orders) or committed and not yet listed; no `short_entry` and no legs. Anything else is refused `FLATTEN_NOT_A_CLOSE` before any send ("cancel that order first, or use KILL" when a close is already working), so two flattens can never both fill into a short. The practice broker also cancels, at the fill, a SELL that would fill past what is held (`PRACTICE_NO_SHORTS`). A protective order that fills inside the send frees its in-flight commitment at once (QA R31). The mirror holds for a cover: the practice broker cancels, at the fill, a BUY that would buy past the short (`PRACTICE_OVERCOVER`, ADR 048).

**Manual-ticket protective legs** (operator decision on #91, 2026-09-20 -- supersedes "OCO / bracket stay off the manual ticket"): OCO stays off the manual ticket. A bracket reaches it only as the operator's optional default take-profit / stop-loss from Settings > Trade (`nova.trade.defaults.v1`), **off by default**. When on, an opening **Limit** entry (BUY while not short, or SELL with `short_entry`) posts `take_profit_price` + `stop_loss_price` with its `/api/ibkr/order` request, and the route sends `operation: "bracket"` (`entry_price` = the limit) through the same `execution.service.execute` -- never a second place path. Other entry types are refused while the defaults are on rather than sent unprotected; exits never carry legs; protective sources (`flatten`, `kill`, `cancel_working`) are refused a `bracket`. A bracket is checked like a place: whole shares, side agrees with `short_entry`, leg prices on the correct side of the entry, BuyingPower for a long entry, and no long bracket while the account is short that symbol.

Receipt includes stage timings (`validation_ms`, `persisted_ms`, `broker_sent_ms`, `broker_ack_ms`, `filled_ms`). The receipt adds `venue` (`live | paper | sim`), the desk venue the order was sent on (`mode` is the broker's label: `paper` there can also be the legacy Gateway).

**One venue per send** (#655, audit 2026-09-30; owner `execution/venue_door.py`). `execute` reads the desk's venue once, under its lock, and the order is validated against, committed on and sent to that venue -- a venue pill clicked mid-check refuses the order `VENUE_CHANGED` ("the desk moved ... it was not sent; place it again") and never sends it elsewhere. An order id is only meaningful on the venue that issued it (practice ids restart at 1 per venue; IBKR's are IBKR's), so in-flight commitments (`execution.inflight`), order watches (`execution.telemetry`: IBKR's by id, a practice venue's by `(venue, id)`) and releases are all per venue: a Paper sell still working never refuses a Live exit, and Paper's fill of order N never marks Live's order N filled. `expected_venue` on the command (cancel / replace by id) makes the door refuse `VENUE_CHANGED` when the desk is elsewhere; `DELETE /api/ibkr/order/{id}?venue=` and `PATCH` `venue` accept it, and the bot's and Who-trades cancels send their trade's venue. The desk's Cancel sends the venue its row came from: the account snapshot (`ibkr/ibkrAccountPoller.ts`) carries `venue`, a venue change clears the old venue's rows and reads the new one at once, and a read that finishes after the switch -- or another window's snapshot of another venue -- is dropped, so the desk never shows the old venue's orders or positions, not even as "last known" (#657). The Who-trades view resets on a venue change too.
Paper and live share this path; only Gateway credentials/port and safety gates differ. `auto_live` remains rejected -- a spend command whose `source` is not one of the listed values (e.g. `auto_live`) is refused `SOURCE_INVALID`; so are `approve` and `auto_paper`, the retired Phase D executor's sources (ADR 025), while ledger rows that already carry them still read. Short opening requires `short_entry: true` and the short check ("Short selling" above, ADR 048), `IBKR_SHORT_ENABLED` on Live (ADR 009).

**Kill switch** (D-037, ADR 025; owner `backend/kill_switch/`): a persisted latch (`kill_switch_state.json` under the operator cache, `schema_version: 1`; unreadable or unknown version reads tripped) that `execution.service.execute` checks before every `place` / `bracket` from a non-protective source, manual and bot included -- refused `KILL_SWITCH`; `kill`, `flatten`, `cancel_working` and every cancel still reach the broker. `GET /api/kill-switch` -> `{tripped, reason, ts}`; `POST /api/kill-switch` trips it (latch first, then the working orders of every venue that has any are cancelled through the `kill` source -- Live while IBKR is connected, else a stated error "Gateway disconnected: Live orders were not swept"; Paper always, even with the Gateway down (#656); Sim while its scratch account is open -- each cancel through the execution door with `ExecutionCommand.target_venue`, which only a `kill` cancel may carry (anything else is refused `TARGET_VENUE_REFUSED`), and a failed read is a stated failure, never "nothing to cancel"; the stops that protect a held position stay resting, ADR 048, "Short selling" above) and answers the status plus `sweep: [{venue, cancelled, failed, kept, error, note}]`, `persisted`, `receipt_error` and the legacy summed `cancelled_order_ids` / `failed_cancel_order_ids` / `kept_order_ids` (the route is async, on the app's loop: #656's lock from a second loop is gone); `POST /api/kill-switch/reset` clears it and is the only thing that does. A trip writes a `kill_switch` receipt to the event log. The control is a card on the Bots page. The header's Emergency KILL (bot to L0, desk lock, cancel, flatten) is a separate composite. The Nova OS verdict, the `signal | confirm | auto_paper` ladder, the staged approval queue and `/api/strategy/executor/*` were removed (ADR 025).

---

## 4. 🔗 Integrations & Services

| Service | Purpose | Status |
|---------|---------|--------|
| Alpaca API | News + listing metadata (not price discovery) | ✅ Verified |
| IB Gateway (local) | Scanner discovery + market data + optional orders | ✅ Verified |
| Web UI (Localhost / Desktop) | Delivery dashboard for gappers | ✅ Verified |
| yfinance | Fundamental data (float, short interest, etc.) | ✅ Verified |
| CoinGecko, Coinbase Exchange, alternative.me, Hyperliquid, DefiLlama, Deribit (public, keyless) | The Cryptos page's crypto reference data (ADR 040): read-only, each labelled on the page, never a stock or order source | 🧪 Fixture-tested |

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

- **Market data / trading:** Scanner and prices are IBKR-only (see `single-market-data-feed.mdc`). Alpaca is news/listing metadata only. The Cryptos page (ADR 040) shows the crypto market from labelled public reference sources (rule 13 there); it is never a scanner, stock chart, order or bot source. Orders are allowed only via gated `backend/ibkr/` (Invariant #7). Gateway port default is live (4001); the paper Gateway (4002) is legacy, by hand only, never an automatic fallback (ADR 020). Spend stays gated; `auto_live` remains NO-GO. Header Live / Paper / Sim are **venue** pills (ADR 020): **Live** places to IBKR; **Paper** is Nova's practice account on the live feed -- fake money, full live data, fills estimated locally, never an IBKR place; **Sim** replays a **real recorded or downloaded session** and fills locally on a scratch account that unwinds when the playhead is scrubbed back (ADR 019); at the **live edge** -- the Sim clock following the wall clock on today's date, not paused, not scrubbed, no past day loaded (`live_edge` on the clock payload and on `/api/ibkr/status`) -- a Sim tab shows the live IBKR feed exactly as a Paper tab does and the scratch account fills against the live reference, and scrubbing back leaves the edge for the loaded replay (today's Session Record when one exists, a stated absence otherwise; ADR 020 live-edge amendment). The IBKR paper Gateway (4002) is legacy with no desk button -- `POST /api/ibkr/gateway-mode {"mode":"paper"}` by hand is its only door. The venue never changes the bot: operator and bots are gated identically everywhere, and a bot fires only on an allowlisted symbol whose depth line the backend itself holds (`409 BOT_NO_DEPTH_LINE` otherwise); after a Sim rewind (`practice_rewind`) bots re-read the ledger. There is no synthetic instrument: a Sim desk with nothing loaded is empty off the live edge, and live at it. `NOVA_BROKER=sim` is bootstrap only. Switching to Live restores the IBKR paths.
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

### 6.7 Lint

- `ruff check backend` is part of `py -3 tools/maintainer_checks.py --gate` (`tools/maintainer_lib/lint.py`),
  so a lint finding is caught before the push. The rules are in `backend/ruff.toml`, and the version is
  the `ruff==` pin in `backend/requirements-dev.txt`, which CI installs. If ruff is missing or cannot
  finish, the gate fails: an unrun lint is never a pass.
- CI's Backend tests job runs pytest even when its Ruff step fails, so a lint finding never hides the
  test results. Before this, five findings on master skipped pytest on every backend PR (PR #603).

---

## 7. 📝 Documentation Requirements (Enforced)

### 7.1 CHANGELOG.md -- RETIRED. The PR body is the record.

There is no changelog. `CHANGELOG.md` is archived under `docs/archive/` and is not
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

- **Mandatory for every agent** (parent + all specialists). Rule: `.cursor/rules/deferred-log.mdc`. Source of truth is GitHub Issues labeled `deferred` -- https://github.com/aaltaay/Nova/issues?q=is%3Aissue+label%3Adeferred . `docs/deferred-log.md` is the how-to, not the to-do.
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
scripts/windows/Run Nova.bat

# Desktop (Electron + local API sidecar):
scripts/windows/Run Nova Desktop.bat
# or: cd frontend && npm run electron:dev

# Windows installer:
cd frontend && npm run electron:pack

# Or manually:
# Terminal A (backend/): py -3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
# Terminal B (frontend/): npm run dev
# Open: http://localhost:5173
```

### Deploy

- **Backend:** local only right now -- no cloud host (not Railway, not another PaaS). Run via `scripts/windows/Run Nova.bat`, Desktop sidecar, or local uvicorn on `127.0.0.1:8000`.
- **Public site:** not in this repo. `nova.altaystudio.com` is built from [`aaltaay/nova-site`](https://github.com/aaltaay/nova-site), which owns the page, its screenshots, the AI-in-trading digest and the Vercel deploy. Nothing here builds, deploys or tests it.
- **Frontend (app UI):** local Vite / Desktop only (`http://localhost:5173`). Do not host the trading SPA on the public domain: a public page that runs the desk could reach a visitor's own Nova on `127.0.0.1:8000`. **One exception (ADR 043):** the demo build (`npm run build:demo`), the desk on Nova Marketing Sample Data with its backend inside the page, is hosted at `nova.altaystudio.com/demo/`. It has no path to any backend: `fetch`, `WebSocket` and `sendBeacon` are replaced before the app loads, every API call, loopback request and socket is answered in the page, and nothing is ever sent.
- **Desktop:** Electron + local API sidecar. A "Starting Nova" window (`frontend/electron/startupSplash.mjs`) is on screen from launch until the desk window shows, naming the step (looking for, starting or connecting to the local engine, loading the desk); closing it calls the launch off. **Installer only** (#347): local pack produces `frontend/release/Nova-Setup-vNNN.exe` plus `latest.yml` + `.blockmap` -- the in-app update feed. The portable EXE is retired; it could never self-update. Application-affecting PRs run the advisory `Desktop pack` GitHub Actions job, which uploads those three files; docs/site-only PRs skip packaging under `.cursor/rules/ci-scope.mdc`. Every commit that lands on master gets its `vNNN` tag, and an application-affecting one also gets a GitHub Release (see below).
- **Releases are automatic (operator decision, 2026-09-23 -- supersedes #347's tag-only publishing):** every commit that lands on master -- a human push, or PR delivery's dispatch after an Actions merge (#346) -- is tagged `vNNN` (its commit count) by `Desktop pack`, which tags the commit through the API. An application-affecting commit packs the installer and publishes it as the `vNNN` GitHub Release with the installer, `.blockmap` and `latest.yml`; a docs/site-only commit gets the tag and no Release, because a Release without `latest.yml` would break the update feed. A Release is marked latest only when no higher `vNNN` Release exists, so a slow run never rolls the feed back. The tag is pushed with `GITHUB_TOKEN`, so it starts no second run. A hand tag still works: `py -3 tools/bump_version.py --ensure-tag --push-tag` on an up-to-date `master`, and the pack refuses a tag that is not that commit's revision. Re-run one with `gh workflow run desktop-pack.yml --ref vNNN`. GitHub's Source code zip/tar is automatic and is not the app.
- **In-app updates (#347):** the installed desk checks GitHub Releases shortly after launch. A newer release is **offered, not fetched** (operator ask, 2026-09-23): a notice under the header names it, with the release notes of every release since the installed one, and asks **Update** / **Later**. Nothing downloads before Update; the notice then follows the download to **Restart to update** / **Later**. It never installs or restarts on its own -- not on quit, not on a timer -- and the notice never takes keyboard focus, so a hot key still reaches the desk. From the Restart click until the new version's window is up, an "Updating Nova" window (`frontend/electron/updateSplash.ps1`, its own PowerShell process, since the installer ends every Nova.exe) names the step -- closing, installing, starting -- and says so if Nova does not reopen; the silent installer otherwise leaves nothing of Nova on screen for most of a minute. Later hides it for that version until the next launch or Help > Check for Updates; a download the operator chose that stops is resumed by the next check without asking again. **Update takes the newest release** (operator report, 2026-09-24): a notice whose release was found more than a minute before the click asks GitHub again first and downloads what is newest then, so a release that shipped while the notice waited out trading hours is not missed (`frontend/electron/newestRelease.mjs`); that check never shows on the notice, and if it fails the release on offer downloads as before. A window that cannot show the notice (an error page) gets the same two questions as dialogs. While the desk stays open it checks again every two hours, but never 07:00-16:00 ET on a weekday (operator decision, 2026-09-23): a re-check neither downloads nor asks in trading hours, because the 150 MB download shares the desk's link with the market data. A release a re-check finds as trading starts waits in Help > Update to vNNN and is offered after 16:00; the launch check and Help > Check for Updates are not held. The first launch of a new version shows **What's new** -- a floating card with the notes of every release the update brought -- until the operator closes it; Help > What's New reopens the latest releases. `NOVA_UPDATE_CHECK=0` (desk `.env` or process env) turns the automatic checks off; Help > Check for Updates still works. Builds are unsigned, so SmartScreen warns on a fresh download.
- **Release notes (operator ask, 2026-09-23):** every Release's body is written by `Desktop pack` from the commit that made it (`tools/release_notes.py`): the PR title, and the first paragraph of its `## What` written for the operator (quotes of an operator report, tables and engineering bullets are skipped; a list the paragraph introduces, or a list of bold lead-ins, comes along). The schema is in §3, "Release notes and the update notice".
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

### Execution venue provenance (#713)

Execution ledger payload JSON adds `venue: "live" | "paper" | "sim"`, stamped
from the execution door's resolved venue at reservation. The broker `mode`
label remains unchanged; `paper` can name the legacy IBKR Paper Gateway.
Ambiguous legacy rows remain unverified rather than joining a practice book.

## 11. 🔧 Maintenance Log

| Date | Change | Author |
|------|--------|--------|
| 2026-10-07 | Short selling, step 1 of 6 (ADR 048, ADR 049; #778; the operator's design, approved 2026-10-07: "Paper and Sim first, Live last"). The design is recorded whole -- one short check on every venue, margin from IBKR's what-if with the published rules as the fallback, a 25% liquidation cushion, a buy stop on every short, no flips, halts, 09:35-15:50 and a 15:55 day cover, SSR above the bid, Paper and Sim shorting like IBKR, Entry · Exit, one bot for both sides, and Live last behind the operator's Live short proof and their own `IBKR_SHORT_ENABLED` -- and the five short strategies are pre-registered before any code reads a bar. This step closes the eight gaps the design found on master, so nothing new can short yet: a short entry is now checked against margin and the cushion (published rules), refused while the account is long, and its borrow is read from the cache before the execution lock (the door had asked IBKR for up to 10 s under it); a short entry is held in flight (`SHORT`); a cover is never locked by the day lock or held to buying power; Freeze all orders keeps the stops that protect a position; Fill now refuses a short entry instead of re-sending it as a plain sell; Paper and Sim cancel a cover that would fill past flat. Invariant 7 and §3 amended. | User Directive + Claude Code |
| 2026-10-06 | The 5-minute flat top is a strategy, bought on the 1-minute hold (ADR 031 amendment (b); operator: "Make the 5-minute flat top a Paper buy with a 1-minute hold entry, as the material trades it; done when its lane proposes and the bot can take it"). The material reads the flat top on the 5-minute chart and buys the 1-minute pullback that holds it after the break; Nova drew the 5-minute flat top and scored it in silence (2026-09-30). `flat_top_5m` is a sixth strategy with its own Off / Eyes / On, templates, read-out and bot rules: a 1-minute lane whose detector (`setup_scanner/flat_top_5m.py`) reads the flat top on 5-minute candles made of the minutes and, after a price over it, triggers on the first 1-minute candle that holds the touch zone and closes green, the stop at the pullback's low. It replaces the built-in 5-minute flat-top lane, starts Off, arms 07:00-15:30 (so auto-record's setups window runs to 15:30), and draws on the 5-minute chart, with its level, break and hold on the 1-minute. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-06 | The PC's power button is named, and a power-off is said as one (#14). The desk's 06:45 ET 2026-10-05 and 07:16 ET 2026-10-06 shutdowns were System 1074 from `winlogon.exe` on behalf of SYSTEM, reason `0x500ff`, Shutdown Type `power off` -- the power button -- and `premarket_verify.py` / `relogin_reason.py` said "This PC was restarted from the Start menu": every `winlogon.exe` was the Start menu, and every restart was "restarted". That signature is now `power_button`; `winlogon.exe` on behalf of a user stays `start_menu`, and on behalf of SYSTEM otherwise names winlogon (a restart with the same reason, 2026-09-12, cannot be the power button). The restart object carries `reason_code` and `shutdown_type`, and the text says "powered off" or "restarted" by it. Found alongside: the `wevtutil` query took every event 12, and an ASUS power tool wrote 818 in 8 days, so the 400-event cap held about 4 days while the report said it had read 8; each id now asks its own provider (30 days: 21 restarts, was 6). §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-06 | The flat top counts its touches (ADR 031 amendment; operator, with a sketch: "Make it something special like this ... when it starts forming. I doubt real life is going to be perfect as this, so we may need a drift or a ratio to still consider flat top"). The flat top read no taps of the level at all: it armed any 2-6 candles closing within 2% under the high of day, a tie of the high started it over on a new row, and a cent over the high reset the base. Now the level is the high of day, and a touch is a high within 0.5% or a cent under it (a candle a little over the earlier touches drifts the level up and keeps the row). The base runs from the first touch, needs a retest, is drawn forming from the second touch, arms at the third, and may run 20 candles. The hold reads the zone as the level. The research's P2 stays one setting away (and a saved template keeps it); the flat top's default revision moves to 2. The desk draws it as the sketch on the 1-minute and 5-minute charts: the violet level, a ring per touch with the count, the base boxed, the break and the hold candle marked. No flat-bottom short (Invariant 7). The catalogue's tables moved to `setup_templates/params.py`. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-06 | LULD bands on Level 2 (ADR 047; operator: "do we have LULD levels?", then, with DAS screenshots, "1 go.. make it obvious"). IBKR passes on the halt, never the band, and the Nasdaq halt feed's threshold is blank, so Nova computes each stock's limit up / limit down from the published Plan rules over the tape and NBBO it holds (`backend/luld/`): the opening or reopening print first, then the 5-minute mean, moved only on a 1% change after 30 s, held in a limit state. Where the Plan's text leaves room, the SIP's own band flags in the Massive NBBO decided. A limit state's end makes no reference (the text says it does: 64% exact against 81%), and the mean is unrounded. On 10 days of SIP data Nova's band matched the exchanges' to the cent on 81% of 593 band touches and within 1c on 87%; on Nova's own recordings, GRML's three pauses of 2026-09-22 land exactly (14.18, 17.18, 15.87). The Level 2 ladder draws a red `LULD` row in each column and a strip above the book that counts a limit state's 15 s down to the pause; an approximate band (no open or reopen seen) shows `≈`. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-06 | Agents find stock-days and show them in the Sim (ADR 050; operator: "if I speak to you ('Go to a small-cap stock that increased, where the high of the day was 300% or something like that'), I can ... punch it in on the simulator", then "this is just going to be for agents for now ... like some secret endpoints that they can manipulate and show me", and "If I'm obviously asking for a command ... I want it to be added to our dictionary"). Finding the day was the gap: the Scanner boards cover 75 days, and nothing searched the 2,515 sessions of Massive candles on E:. Massive's day bar is regular hours only (2,477 of 11,866 tickers on 2026-09-09 had a higher premarket or after-hours high), and of 6,104 regular-hours +300% days since Oct 2016, 90% were warrants, rights, sub-50c names or likely reverse splits. A day movers index (`research/movers/build_movers.py` -> `backend/day_movers/`, on E: beside the files) keeps one row per stock per session that moved: the official prior close through listed splits, premarket and after-hours highs from the minute bars with the minute each printed, the first minute of each +N% mark, split suspects tagged. Private `/api/agent` endpoints (loopback, writes keyed) search it with plain numbers and percentages back, and queue a show or move that the main desk window takes by a long poll and runs with the desk's own steps (the venue pill's door, the Sim Day jump, the Trader tab, Load from files, the playhead, paused); the venue moves and a new Sim window loads only when nothing is at stake, else the agent asks. The operator's words live in a dictionary (operator data, seeded with the plain commands; no shape word is defined by Nova). A float limit passes only on evidence: the float Nova knew that day, or SEC shares outstanding under it. `tools/nova_agent.py` and the `nova-sim-navigator` skill let any agent session use it without seeing the key. Voice and TypeSafe's Jev are parked. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-06 | A rebuilt day confirms the splits Massive's list misses from SEC filings (#772). PHGE's 1-for-10 reverse split on 2026-09-09 was not in the list, so the rebuilt boards read +925% (0.155 -> 1.60) and it topped Gainers and the frozen Gappers. `research/leaderboard/confirm_splits.py` takes each overnight jump of 1.8x or more (0.7x or less) that no listed split explains, reads the ticker's 8-K (Item 5.03 / 3.03) or 6-K filed from 60 days before to 3 after, and confirms a split only when the filing states one ratio outside a range, the split-adjusted open sits 0.5-2x the prior close and the filing's effective date falls on the session (`split_confirm.py`, pure). Never on the price jump alone. On 2026-06-16..09-21: 285 suspects, 181 with such a filing, 1 confirmed (PHGE, its own 8-K: "effected a one-for-ten reverse stock split ... split-adjusted basis ... September 9, 2026"), 107 refused, 0 unread; the refusals read on sample were right (GCDT's consolidation takes effect October 7; SGLD's "1 ADS for every 20 shares" is a new listing). `splits_confirmed.json` beside the store (schema in §3) is read by `lb_io.load_splits` and `spot_check.py`; `build_leaderboard.py --dates` rebuilds the days a split touches. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-06 | A rebuilt day has Losers and Gappers (ADR 023 amendment; operator report on 2026-09-09 at 07:00 in Sim: "Don't we already have the data for this day ... Why do we not see gainers, losers, and gappers for that hour?"). The Massive files for the day were on disk, but the rebuild kept one board a minute, the top 100 risers (`market`), which the desk showed as Gainers; no stored row that day was under 0% at 07:00, 09:45 or 16:30, so Losers could not be read back, and nothing projected Gappers. `research/leaderboard` now writes `losers` (the worst 100, `LOSERS_RULES`) and `gappers` (the live premarket rule, `GAPPERS_RULES` = `ibkr/gapper_view.row_qualifies`, frozen at 09:30 in its 09:30 order and repriced after, as the live list is) beside `market`, every board covering every minute; a day counts complete only with all three, so the 66 days rebuilt before are rebuilt again. The desk fills Gainers, Losers and Gappers from a rebuilt day, and After Hours and Large Cap say why they are not rebuilt. Found alongside it: PHGE's 1-for-10 reverse split on 2026-09-09 is missing from Massive's split list, so the rebuilt boards show it +925% (one such jump in the 66 rebuilt days; the other 30 overnight jumps of 3x or more traded 10-1,000x more volume). §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-06 | The 1-minute chart keeps the operator's zoom when the plan's lead setup changes (operator report: "As I was zooming in and watching the chart, all of a sudden it resized itself randomly ... We fixed it before"). The 2026-09-25 fix stopped the plan's zones from moving the view, but the stock read still framed every newly leading setup: FRGT's plan followed red to green (near) at 09:31 and Gap and Go (armed) at 09:34, and each change reframed the pane -- red to green on 40 candles, Gap and Go from its 04:05 premarket high. The screenshot's window was exactly that frame (40 candles plus 12 of room). `chart/operatorView.ts` notes when the operator zooms or pans a pane (a range change during a press that began on the chart, or within 300 ms of a wheel or a release); after that no automatic frame or zone slide moves it, until a first paint or Reset chart hands it back. A setup is framed once per symbol, so a flip-flopping lead no longer reframes an untouched pane either. Driven in the demo desk: zoomed to 36 candles, a new lead setup jumped the pre-fix build to 333 and left the fixed one at its 208; the badge and Reset chart still frame. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-06 | The hot list is watching only, and its ★ shows next to every ticker (ADR 044 amendment; operator: "if i star a ticker can we please see 'star' next to it", then "a star[red] ticker ... shouldn't be buying and selling if it's signal only ... just because it's [starred] or not, it shouldn't be a reason", and "1 go" on the five questions). The star decided trading three ways: setting Buy to Nova starred the stock, taking the star off flipped it to You · You, and the bot refused any unlisted stock (`BOT_SKIP_NOT_LISTED`). All three are gone, with the list's default Buy / Sell; the bot buys where the Bot is on, the strategy is On and the stock's Buy is Bot. The 04:00 reset of yesterday's bot buys stays, on its own: nothing buys until today's file shows it ran (`BOT_SKIP_DAY_NOT_RESET`), and a failed reset is retried every pass -- the not-listed rule had covered that by accident. Bot-buy stocks take HOD Momo's reserved slots ahead of the list, since the bot only buys what a lane reads. A filled ★ (yours) or outlined ☆ (an auto star) now sits beside the symbol on the Trader tab, the Focus rail, the HOD Momo strip, the quote card and the Who trades row, as on scanner rows; the Buy / Sell switch reads You | Bot and the chart says BOT BUYS AT. The triggers table loses its Hot list square (nine gates) and lists bot-buy stocks with a "now" row. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-06 | The Sim replays the operator's Massive flat files (ADR 046; operator: "u wanna populate the data inside the sim? that way when we go back in time, the data we downloaded all of its information gets picked up?", then "1 go also do the bid and ask"). A historical window could only be an IBKR download -- about 90 prints a second (a full AAPL day of 628,348 trades in two hours, over the 500,000 a selection holds) and no bid or ask. Now `auto` takes a day's Massive files when they are on disk: one import reads the ticker's trades, 1-minute bars and NBBO from the day's gzip files (its own process, below normal priority, unaltered rows, csv-parsed), and selecting such a day starts it. The snapshot answers the bid and ask at the playhead (never ahead), colours prints from the NBBO before them, shows the NBBO as a one-level Level 2 when no book was recorded, and practice orders fill at the far side. Candles built from the prints that set a price matched Massive's own minute bars exactly (AAPL 2026-10-02 09:30-09:40, 10 of 10). On the desk the Sim Day calendar now opens every day in the files (before, a day needed a Scanner board or a Session Record, so nothing before September 2021 could be), a Sim tab offers Load from files with no Gateway, and the quote card, ticket, tape and Level 2 show the bid and ask. Massive data never enters the IBKR chart store; the single-market-data-feed rule's Sim exception names the source. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-05 | PR delivery checks issue state once more after a refused fallback close. Native GitHub closure can race the open-state read and PATCH (#737: #653 closed while its PATCH returned HTTP 422); only a fresh closed-state read counts as success, while still-open or failed readback retains the write error. No blind retry; pack dispatch and guarded head cleanup remain independent. | Backlog triage + Codex |
| 2026-10-05 | Shared API ownership across checkouts (#653 follow-up): one per-user runtime guard excludes checkout and packaged engines even when caches differ. Diagnostic JSON stays cache-local; independent tests inject guard-path isolation directly. ADR 038 amended before behavior code. | Authorized backlog follow-up + Codex |
| 2026-10-05 | PR delivery verifies explicit same-repository completion references from the full PR body after merge, closes eligible open issues and reads back their actual state. Partial `Refs`, foreign repositories, quoted/code examples and PR references are excluded; failures remain visible without skipping Desktop pack dispatch or guarded head cleanup. | Backlog triage + Codex |
| 2026-10-05 | PR delivery grants `issues: write` to both merging token paths, guarded across parsed workflow jobs and their effective permission blocks. The delivery rule requires checking actual closure after merge; a closing reference alone does not prove issue completion. The suspended GitHub App installation was the connector write blocker; missing Actions scopes are a separate delivery gap, not a proven sole cause of stale issues. | Backlog triage + Codex |
| 2026-10-05 | Startup reliability (#653, #713): an OS-held lifetime guard serializes API startup before PID metadata; the desk starts its checkout immediately after a requested stop, and previous-boot executions reconcile against their own venue, abandoning lost Sim scratch with an explicit reason. ADR 038 and ADR 007 amended before behavior code. | Authorized backlog fixes + Codex |
| 2026-10-05 | The Live send awaits the IB loop, and goes out once or never (#725, ADR 045 amendment; operator: "1 go" on the follow-up). A Live place, replace or bracket reached the IB loop with `call_on_ib`, which held the socket loop -- every Level 2, Time & Sales and quote socket -- for as long as the IB loop was busy (0 turns in a 300 ms busy spell, measured). It now awaits the IB loop (`ibkr/send_hop.py`), and one lock both loops take settles whether the order went out: a send the IB loop has not started when its caller gives up is never sent, and one already running is awaited, never reported unsent (`run_coro`'s timeout cancelled a hop that could still reach IBKR). The 750 ms deadline is enforced by the IB loop as it sends (it was checked before the hop). The order's watch and its in-flight commitment's order id are set in the callback that placed it, its ack wakes the reply safely from the IB thread (on a quiet loop an ack at 50 ms was seen when the wait ran out), and IBKR's order events are wired at READY instead of on the first order. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-05 | A Level 1 line IBKR refused is not open (operator: "find out why 10 of the 50 after-hours rows never get a price"). From 16:08 ET IBKR refused 176 Level 1 lines with Error 101 while Nova held 51-56 of its own: the cap is the login's, shared with its other IBKR platforms. ib_async keeps a refused request registered and hands it back, so each line stayed "subscribed" for good and 17 After Hours rows had no price (INBS 53 minutes). A refused line now keeps its owners but is not counted, the lines held at the refusal become the cap the scanner plans to (rising again over time), and the line is asked for again in place once there is room; `/api/ibkr/status`, the scanner subscription state and the `market_data_lines` row say so. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-05 | Orders refuse a stale view (ADR 045; operator report on APUS: "If it lags, then we cannot place an order ... Everything needs to happen in real time"). At 08:30:25 ET the operator sold at a 6.58 bid their Level 2 had shown since 08:30:18-21, while Nova's own book read 6.50 x 6.55; the order reached the backend 2-3 s after the click and rested above the market. Each Level 2 viewer replayed up to 100 old books in order from a queue the IB thread filled without waking the socket loop, the socket loop ran `tasklist` and re-read files on every status poll, and the backend and IB Gateway ran BelowNormal. Every book and quote now has a version; a Level 2 viewer holds the newest book only, woken thread-safely, with a beat every 250 ms; Time & Sales sends a backlog in one frame. Every desk order carries the view its screen showed, and the execution door refuses one whose book or quote had been replaced for more than 500 ms when the operator acted, that arrived more than 500 ms later, or that met a feed gap or a stalled IB loop (`VIEW_STALE`, `ORDER_LATE`, `FEED_STALE`, `VIEW_MISSING`); the desk locks Place, the hotkeys and Fill now first, with the reason, and never Flatten or a cancel. The socket loop's slow reads are gone, the backend keeps itself and the Gateway Above Normal (the desk app its own windows), and a freeze dumps every thread's stack. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-05 | A silent tape says so, and 10-second candles keep one clock (#722, #721; operator reports: "time and sale is fully frozen", "two candles drawing together ... the previous candle should never move"). At 09:35:42 ET two AllLast lines stopped while their books kept updating, with no IBKR error, and Time & Sales read LIVE for six minutes; each idle `ping` now carries a silence reading (`ibkr/tape_silence.py`) and the pane reads SILENT / HALTED / QUIET with the reason. The recorder no longer calls a halted name's line dead (MI was dropped and re-asked through two halts). 10-second candles from prints are keyed by IBKR's own second, which IBKR delivers in order (1.2M October prints, none out of order) and its history uses; arrival time had built most candles differently. The pane's forming candle has one writer, the tape: a Level 1 trade stamped on Nova's clock opened the next candle at the boundary while prints still filled the last. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-05 | The desk draws with the graphics card (#707; operator: "when I move the chart left and right with my mouse and hold, even when I have the eyes off, the setup off, and the levels off, it really feels laggy"). Software drawing had been the Windows default since the 2026-09-17 black-window fix, which changed three things at once; measured alone in Electron 41 on the demo desk at 4K/150%, a chart drag ran at about 22 fps in software and with 5 ms frames on the graphics card. The graphics card is the default now, kept in `graphics.json` and switched in View > Draw with the graphics card, with a safety net: a crash of the graphics process turns it off from the next start and says so; a blank window -- the screen under the focused desk window, read from the screen recording's own capture, one flat colour three looks in a row while the page draws content -- restarts Nova in software. The menu has one owner (`appMenu.mjs`) so the View switch and the updater's Help rows never drop each other. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-05 | The close countdown keeps clear of the pane's words (operator report: on a 5-minute pane the timer sat on top of the setup's "5m ... +83.3%" label, and asked to check every chart). The chip drawn over the forming candle on every minute pane (`chart/BarCountdownPrimitive.ts`) knew only the candle, so any label or price near the tip ran under it -- a live lane's label starts at its box's left edge, a few candles back, so a forming setup always put its label over the chip. Each primitive that writes words on a pane now publishes the rectangles it drew (`chart/paneWords.ts`: the stock read's labels, pins, fixed labels and edge column, and the fill arrows with their prices), and the chip takes the first clear spot: beside the candle, under it, then a row at a time, never on the forming candle, and not drawn when nothing is clear. Only the chip yields; the labels place as before. Rendered headless with the real primitives on the screenshot's scenario: the chip moved from over the label to beside the candle. §3 amended. | User Directive + Claude Sonnet 5.5 |
| 2026-10-04 | A practice order's execution rows close when its venue closes it (TNMG, 2026-10-02). Nova's bot cancelled its unfilled Paper bracket entry 77 at 09:47:22 ET, three seconds after the venue answered `Submitted`. The bracket's row and the cancel's row stayed `acked` until the 10:36 restart, when the startup sweep called the venue's Cancelled `failed`. Three causes: the practice broker skipped the notice for an order Nova cancelled; the cancel path set only the place row's `broker_status`; and no callback follows a practice venue's first answer, so resting Paper fills also read `acked` until a restart (AIFF, NXL, CNTB). The ledger gains a terminal `cancelled`, classified by one rule (`execution.order_outcome.ledger_close`). Every practice close now ends its rows at once (`practice.watch.close_rows`), and the sweep reads a cancel as `cancelled`. A bracket's row keeps its entry's `perm_id`: TNMG's read the stop leg's 79. `tools/order_timing.py` no longer prints the order's status now beside the venue's first answer. Live's same gap is #712; the sweep's venue scoping is #713. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-02 | Auto-heal (operator: "when I view a stock or a ticker, the recorder will empty a space for me"; "Shouldn't this be fully auto-healed?"). The stock you look at outranks every recording you did not start: a recording a restart brought back with no owner on file is auto-record's and gives way (SDEV, SSM and CELU held all three lines from 10:36 and AZTA read "Symbol cap reached" for over an hour); the operator's own starts are kept in `auto-record.json` `operator`; the ladder names who holds the lines and backs off to 5 s (it asked every second). A Gateway logged in but refusing its API port (after the 12:12-12:45 Wi-Fi drop) restarts itself through IBC's `RESTART` on its saved login, no 2FA; IBC's command server turns on, on this PC only. The launcher no longer starts a second Gateway beside a running one (`ibgateway1.exe`), which is what took over the IBKR login at 12:46, and its process check is cached (a PowerShell run held the HTTP loop 250-935 ms per status poll). §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-02 | Gap and Go gets its scanner, like every other strategy (ADR 031 amendment; operator, after SDEV's open and being offered a chart-only lane: "why dont u treat it like every other strategy we already got?"). Decision C of ADR 031 had made it next, and the four setups with scanners failed their bar-level backtests worse than Gap and Go did (PF 0.54 / 0.20 / 0.58 against 1.00). A fifth detector (`setup_scanner/gap_and_go.py`) reads the research's pre-registered A2 rule on the same lanes: the pre-market high, armed at the 09:30 open when the open is under it (a gap through it skips the day), a live price over it by 10:00, stop min(20c, 4%) under the entry, target 1 at 2R, one try a day; before the open the levels are drawn as forming. It has Off / Eyes / On per venue (starting Off), templates, scoring, its own read-out, the tape gate, the grade, the cards, the Tickers today squares and the charts, and Nova's bot plays it at On on Paper and Sim only. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-02 | A symbol followed mid-session is seeded from 04:00. The scanner followed AMOD at 07:51:22 with nothing stored before its Level 1 line opened, so every lane warmed up from scratch: the 1-minute first pullback's first line came at 08:23 (32 bars), the 5-minute one read "warming up (17/32 bars)" at 09:19. On five days of the eyes' journal no name first followed after 04:10 warmed within 2 minutes. A short seed now waits on IBKR's 1-minute history of today, asked one symbol at a time against half of IBKR's historical budget (`setup_scanner/seeder.py`). The wire is unchanged. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-02 | One row per trigger (ADR 022 amendment). The lane named `setups.db` rows by the setup's key (the leg), so a setup armed again on that key after its trigger was written over the trade's row. AMOD's first pullback triggered at 08:48:04, and at 08:49 a candle tied the leg's high and re-armed the same leg as the second pullback. The stored row became `second_pullback` with the new levels, and the read-out, which counts the first of the day, lost the trigger. A second trigger on one id replaced the first trade's score (LITS 2026-09-24, GOW 2026-09-30). A later setup on a key now opens `KEY#N` (`setup_scanner/lane_ids.py`), and a restart never writes over a stored trade. A detector made mid-day (a restart, a symbol back in the universe, an edited template) starts from the day's triggers, so a later setup reads as the second and red to green's one try stays spent. The eyes' journal 2026-09-24..10-02 shows 18 rows written over; they keep their ids and are not repaired here. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-02 | AMOD's missed catalyst (ADR 024 amendment, rules v8). AMOD ran +120% while `/api/why` and `/api/catalysts` read "noise_only" and "Low-float momentum -- no company news". Its 8-K closing a PIPE of 51.6M shares for 3,170 bitcoin was filed at 11:30 ET the day before, so the window (from the prior close) never read it; Benzinga's after-hours piece named that cause but was tagged AMOD + BTCUSD and so was not read as a one-ticker rewrite. The verdict adds `prior_session` -- the prior session's own filing or release, shown and never counted; the window is unchanged. A raise paid in or spent on a crypto treasury is `crypto_treasury` (weak, with dilution); `PIPE` is a raise word; `n_tickers` counts names, not symbols. A filed share issuance (an 8-K Item 3.02, or 2.01 labelled a raise, in the last 30 days) marks Yahoo's float "631K?" with the filing on hover on scanner rows and the Trader, and `/api/why` reads it as unknown; no gate reads it (operator decision on #700: warn, don't block). The feed's memory reaches back to the prior session's open: on a Monday it had lost Friday's after-hours filings. 72 of 255,139 backfilled labels change. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-02 | Time & Sales comes back by itself (#698; operator report on AMOD at 07:54 ET: "should that be fully self-healing?"). IBKR refused AMOD's tick-by-tick line with 10190 while three recordings and two leaked resumes held the lines, and the socket sat on a dead line until the operator switched tabs. Four causes, all fixed: a refused line was never asked for again (`line_lending/tape_heal.py` now frees room and asks again, saying so, while a socket watches; the desk reads RETRYING); a resume refused a slot kept the lines it opened (`capture/keepalive.py` opens none with every slot taken and releases on a refused start); a line auto-record gave back lingered 16 s and was taken back by its next tick (cancelled at once, kept for the operator 30 s); and a restart forgot which recordings were auto-record's, so the setups' recordings lost their slots to fresh leaders and one came back as a recording auto-record could never give back (`auto-record.json`, `leaderboard/auto_record_state.py`; resumes' slots are left to them). The tick-by-tick cap is not the depth cap of 3: 4 lines were live at once. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-02 | The Trader's Decisions and past setups follow the trading day (#695). Like the triggers table before PR #696, `GET /api/stock-read/{symbol}/decisions` and `/past-setups` with no date answered the calendar date, so from midnight to 04:00 ET the Decisions sheet and the 1-minute chart's past setups read a day with no session (SCKT on the desk at 00:45 ET: 0 events and 0 episodes, against 400 and 17 for the day). Both now default to the hot list's trading day. The day's news stays tied to the calendar date: the News panel's window moves to the next session at midnight. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-02 | Tickers today follows the hot list's trading day (ADR 044). `GET /api/bot/triggers` with no date answered the calendar date, while the hot list's day starts at 04:00 ET: from midnight to the rollover the desk's table asked for a day with no list ("no hot list kept for 2026-10-02"), so its listed tickers and their "now" rows vanished and the day's triggered tickers gave way to the new date's file (one overnight trigger, against the day's 21, on the desk at 00:36 ET). Today is now the hot list's trading day in the route and in its hot-list read, from one clock read. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-02 | The trading session ends at 20:00 ET (operator report 2026-10-01 23:33: "How come these things are getting triggered right now? ... the entire market is closed, no?"). After the close IBKR keeps the SMART Level 1 lines moving with its overnight session (20:00-03:50 ET), and Nova read those prints as more of the day: one-minute candles, HOD Momo trades (78 alerts after 20:00) and setup-scanner bars -- OM's "12% leg" was one 200-share print at 20:48 -- while the scanner never ended its day, so legs from 15:52 still read as forming at 23:33 and, after midnight, red to green armed SDEV at 00:12 on a 23:59 print taken for the 09:30 open. One rule (`market.in_trading_session`: 04:00-20:00 ET on an exchange day) now bounds the bar builder, HOD Momo's L1 feed and the scanner, which ends every lane's day at the close with a stated reason. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-01 | Dilution on file (ADR 036 amendment; operator ask: show the dilution filings on file on the stock read). The float group adds the row `dilution_on_file` from SEC EDGAR's submissions file for the symbol's CIK: an S-3 / F-3 shelf within 3 years, a 424B within 180 days, an S-1 / F-1 within 180 days, an 8-K Item 3.02 within 180 days. It reads `warn` when any is on file, `ok` when the registrant is known and none is, and `unknown` with the reason otherwise (never clean). The stock read never waits on it: a background reader (`stock_read/dilution_reader.py`) reads EDGAR on first ask, one request a second, and keeps each symbol's read for its session day in `stock_read/dilution.sqlite3`. Nothing places, stages or gates on it. §3 amended. | User Directive + Claude Fable 5.1 |
| 2026-10-01 | The close-of-day reminder (operator ask: be flat before the close, nothing held overnight). A loud card at 15:50 ET per open Paper / Live position, escalated at 15:55, gone at 16:00, once per position per day per stage, remembered for the day in `nova.closeReminder.fired`. §3 amended. | User Directive + Claude Fable 5.1 |
| 2026-10-01 | One Bots page (ADR 044; operator: "I definitely don't like it if we have redundancies ... put everything on one page", after AISP's three triggers went unbought for five reasons no screen showed together: the Bot off since the 09:43 bot trip, AISP not on any list, the bot windows closed at 10:00, its tape BLIND while three Trader tabs held IBKR's three lines, a 1-share sleeve). One Bot switch per venue replaces the master dial and Activate (`POST /api/bot/session/switch`; the bot trip now leaves Eyes running); each strategy is Off / Eyes / On with its own grades, setups a stock a day and bot window; today's hot list (`backend/hot_list/`, auto top N of the Gainers plus your stars, fresh at 04:00) is what Nova may buy, and the watch list folds into its ★; Tickers today (`GET /api/bot/triggers`) shows every ticker's ten checks now and at each of the day's triggers, red with why; a Trader tab you are not looking at lends its Level 2 and Time & Sales lines to a setup near its trigger; the kill switch is Freeze all orders; and the Trader's charts get one Eyes switch for everything Nova draws. Measured on today's journal: 32 triggers on 21 tickers, 29 of them BLIND. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-01 | The repository root tidied (operator: "It just does not feel professional ... I need you to clean it up"). Removed: `findings.md`, `progress.md` and `task_plan.md` (April planning logs), `gemini.md` (a legacy alias of this file), `.tmp/` (a scratch file that should never have been tracked) and `brand_guideline/` (an unused reference image). Moved: `_archived/` to `docs/archive/`, `DEFERRED_LOG.md` to `docs/deferred-log.md`, the four `.bat` launchers to `scripts/windows/` (they find the repo two levels up; no scheduled task calls them) and the launcher icon into `tools/nova-launcher/`. Every reference moved with them; the README gains a layout map. | User Directive + Claude Opus 5.5 |
| 2026-10-01 | A public demo of the desk (ADR 043; operator: "I want the demo to be live ... I just care about the interface, really, with fake data"). The sample desk (`?view=sample`) runs without a backend but is a thin shell (its charts read "no candles here"); the README screenshots came from the real desk driven by a fake backend. `npm run build:demo` builds the real desk with that backend inside the page (`frontend/src/demo/`): every API call and socket is answered with Nova Marketing Sample Data, the clock starts at the sample morning and runs, the open symbol's tape and book tick, and orders, arming and settings are refused with the reason. §8's "do not host the trading SPA" keeps its reason, and the demo meets it by construction: `fetch`, `WebSocket` and `sendBeacon` are replaced before the app loads, the API base is a name that never resolves, and loopback and API requests never leave the page. Hosted at nova.altaystudio.com/demo/. §8 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-01 | Managing a trade you hold (ADR 036 / 037 amendment; operator: "If I enter a trade, can it tell me on the chart when I should sell ... if we pass that level, okay, this is the next level ... I can instruct Nova to sell it for me", then on mockup v4b "1 go" and "lets move these targets ... to the 10 seconds chart"). Fed a position, the plan box measured from the entry: holding APUS at 6.64 it said "$5.50 is 42c above" and the price sat off its ruler. The read now takes the held position (`held_*`) and answers `held` from `stock_read/held.py`: the stop (yours, Nova's or proposed), the rounds a 1-minute candle closed over (broke) or only traded through, the raise they offer, the 2R target and a ladder of the levels over and under the price; the plan box keeps its look and becomes the trade's while you hold; the 10-second chart draws the ladder; the 1-minute calls SELL NOW (stop, or a flush in trial T1 from a 1-second `/flush` read), BROKE and TARGET. "Nova takes the exit" (Paper, and Sim at the live edge) hands Nova the sell of a stock you bought: a resting stop, raised at each round a candle closes over (`stock_mode/exit_trade.py`, origin `nova_exit`); a target beside it waits on an exit-only one-cancels-other pair in the execution door (#681), which today lets one order sell the same shares; Live stays locked. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-01 | Too thin to trade (ADR 022 amendment; operator report on LPA, Gainers #41 at +10%: "there's no way I will ever trade something like that with a 20-cent spread ... the volume is almost dead", then "1 go"). LPA passed HOD Momo's floor (549K shares, RVOL 15x against its own 74K-share day), so the scanners armed five setups and drew them like trades, with a "STOP FIRST -1.00R" badge. They were already NOT A TRADE (grade C, tape blind), but nothing measured whether the stock could be traded: every spread check read only the inside quote, and only with a Level 2 line. One pure rule, `setup_scanner/liquidity.py`: too thin under $2M traded today, under $100K in the last five minutes, or when buying the desk's size walks the asks more than 0.25R past the ask. A thin setup never proposes, is NOT A TRADE for every reader, and is scored outside the read-out (`setups.db` schema 5). The desk greys it with its numbers, never hides it, and draws no plan for it. Measured first: 82 of 102 triggers since 9/23 were blind; triggers under $2M averaged -0.72R gross against -0.17R (37 vs 49, a cut chosen in sample); the real premarket runners traded far above $2M. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-01 | Who sent a Live order (#677). The Sent by column read "—" on every working Live order (IBKR's open orders carry no sender), and a Live bracket's exit leg, whose id is its own, read "Outside Nova" once it closed. `execution/sent_by.py` joins Live working and closed rows to today's execution rows for this desk (permId, else order id, the symbols agreeing; bracket legs share their entry's sender), and the Account page's Source column names the sender the same way. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-01 | Who sent an order, and the loss breakers say so (operator report: "Could you see who sold here? I don't remember selling it."). At 09:43 ET the Paper bot trip (day P&L -$66.07 against a -$50 limit) sold 100 ACN, and the Orders table showed one more market sell: the row's only stamp, source `flatten`, is shared by the ticket's Flatten, the header's KILL, both breakers and the bot's last-resort exit, and the trip was said only on the Bots and Account pages. Every sender now stamps `origin`; the execution record, practice rows and Live closed rows carry it; the order tables add a Sent by column; a breaker's audit line lists what it sold and every desk window raises a notice that stays until dismissed. Rows placed earlier stay `origin: null` and read "Flatten", never guessed. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-01 | When IBKR data stops arriving (#672, #673; operator: "that entire graph stopped working. Time and sales stopped ... This should never happen"). At the open the desk's Wi-Fi re-authenticated five times, and no IBKR data reached Nova for 4-16 s each time while both loops stayed healthy. Nothing said so: the header read "STALE 0S" all morning, from an Error 101 subscription error with fresh prices. `ibkr/feed_pulse.py` notices a busy feed going silent on every line and `GET /api/ibkr/feed` says so, naming a Wi-Fi drop from Windows' WLAN log (`ibkr/wifi_drops.py`). The header and Time & Sales read NO DATA / DATA GAP, and STALE now means late prices only. The catch-up burst no longer reads as tape: a gate or flow read across a gap is `blind` with the reason (`setup_scanner/tape_gap.py`), so a bot cannot enter, and a flush exit cannot act, on 16 s of prints that landed in one second. Checklist row `ibkr_feed_gaps`. A 5-s backend freeze found alongside it is #674. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-10-01 | The stock's own round numbers (operator report on ACN at $223: "How do we address this without losing important visibility on important resistance and support levels?"). Every half dollar was a level at any price: the plan listed 26 between ACN's stop and target, one check each, the ruler printed 27 prices on top of each other, and today's map was zones of six half dollars that buried the real tops, VWAP and the open. Round numbers now scale with the price (`stock_read/rounds.py`: half and whole dollars up to $25, $5 and $10 on a $223 stock, a minor round always 2% of the price or more), one scale for the map, the notes, the marks, the checks and the next-round row; the rounds between entry and target are one check line, and the ruler leaves off a label that would touch a stronger one. Where the level study did not look (anything but half and whole dollars on $1-$20 stocks) the plan says so instead of quoting it, and Room is not trial T7's. On ACN's bars: checks 32 to 7, the map names "217.99 · triple top" and "$215.00 · top ×15 · bottom ×5 · VWAP · open". §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | EDGAR acceptance times on their own clock (ADR 024 amendment). SEC's bulk submissions JSON writes every `acceptanceDateTime` with a `Z`, but some filers' JSON holds Eastern wall time behind it (about 30% of 2021's filings, 0.5% of 2026's), and the research fetcher read every one as UTC: 753 of the 5,454 EDGAR filings in the catalyst store were 4-5 hours early, 292 in the wrong session and 418 at 01:00-06:00 ET, when EDGAR is closed. `research/catalysts/edgar_clock.py` places each row by its own time (EDGAR's 06:00-22:00 ET hours, its 17:30 filing-date rule), else its JSON neighbours; `fetch_edgar.py --reclock` repaired the store and 34 of 7,976 verdicts changed. The live feed reads EDGAR's Atom, whose times carry their offset (equal to each filing's "Accepted" time): unaffected. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | The tape at a trigger is the tape Nova saw (ADR 022 amendment; operator: "Why didn't we trade it? ... do we have an audit trail to check why we didn't trigger a bot for this one?"). LGHL's first pullback triggered at 07:16:10 and ran to its target in under a minute, while its tape read said WAIT, "burst of red". The read's window ended at the trigger's stamp, IBKR's whole-second trade time; the prints that crossed the trigger are stamped on arrival (#563), 0.6 s later, so the gate judged the pullback's own selling. A lane now reads the tape for a trigger, and for a setup coming near, when it handles the price; a read drains the print queue first, and every read stamps `metrics.read_at`. The gate replayed on the Session Records reproduced the live verdict on all 5 recorded triggers since 09-23, and 2 change: LGHL from WAIT to GO (124 prints, 7,882 shares at the ask), PFSA 09-24 from GO to VETO (its spread had widened). The replay already read after the price's second, so live and backtests now read the same moment. A trigger's age still reads the stamp, which lagged arrival by more than 2 s on 13 of 84 triggers (#667). §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | One column at a chart pane's right edge (operator report: "everything is getting on top of each other in the charts!", LGHL after hours). The levels' labels, the EMAs' and VWAP's tags (drawn by lightweight-charts on its own), the plan lines' names and the off-view tags each stacked alone, so "5.20 · double top" sat under "200 EMA" and "↑ HOD 9.79" under the 1-minute pane's Bot chip. The stock read claims each pane's edge (`chart/edgeWords.ts`), the overlays and price lines hand it their names, the position tag reserves its spot, and `stock_read/edgeColumn.ts` places every word in one column, nearest its line, dropping the least important first. The EMAs no longer stretch the price scale (the Full Day candles were a flat line under a 200 EMA at 7,500), and the +40% run labels make room for each other. Verified on LGHL's real bars rendered headlessly through the real components. §3 amended ("One column at a pane's right edge"). | User Directive + Claude Opus 5.5 |
| 2026-09-30 | One owner for Nova's buys (ADR 042; operator: "why is it a radio button? We are already choosing if it's off, eyes only, or strategy independently in each strategy", then "do you see other stupid mistakes like this one? run deep dive", then "fix these problems, all of them ... I don't want just silent blockers ... We don't want anything invisible to the user"). A read-only audit found about 30 leftovers of the kind: two automatic buyers (the bot and Auto-entry) with different rules and no shared owner. Now the chosen setup and its radio are gone -- the hero's level is a master ceiling and each setup's own Off / Eyes / Strategy is the decision; one Activate, refused with a stated reason and cleared by the backend on restart and when the padlock is locked; every gate drawn with its reason; one sleeve per venue sizes every Nova buy (risk per trade, also the Trader's), one entry timeout, one persisted daily count; the bot list written only through Who trades, per venue; Auto-entry follows the bot's rules and hands over the exit; NOT A TRADE is one rule for the plan, the bot, Auto-entry, Approve and proposals; Nova's bot plays every Strategy setup with its stop resting at the broker; the localhost bot API refuses Live; the day lock and the bot trip lift at 04:00 ET (they lifted at midnight and tripped again on yesterday's practice P&L) and lock their own venue; the kill switch sweeps every venue and says what it could not reach (#656); the breakers stop counting Live commissions twice; bot parameters never restart a read-out; auto-record keeps setups' lines through their arming windows; the Decisions tab counts each setup once. §3 amended (Bot playbook, Activate, sleeve, breakers, the level belongs to a venue, Nova's bot, Every setup's scanner, Who trades, NOT A TRADE, Setup templates, Auto-record, the kill switch, Who may arm the desk); ADRs 027, 029, 030, 031, 032 and 037 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | The desk's account view follows the venue (#657, the second half of #655). After a venue switch the orders, positions and summary of the old venue stayed on screen until the next read (up to 5 s for orders), a failed read kept them, and a disconnected Live showed Paper's as "last known". The snapshot now names its venue, a switch clears it and reads the new one at once, late reads and other windows' snapshots of another venue are dropped, and Cancel sends the row's venue so the door refuses it if the desk moved. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | 5-minute setups (operator: "we need 5-minute strategies ... clear patterns in the 5-minute chart, but they're not clear in the 1-minute chart"; on the mockup of IOVA 2026-09-29: build it this way, chart only, a chip and the trigger on the 1-minute, 07:00-15:30). One built-in lane per setup (first pullback, bull flag, flat top) runs the setup's own detector on 5-minute candles made of the scanner's minutes, with the default template's rules but a 5-minute candle, arming until 15:30, a risk up to 6% of the entry and a 60-minute scoring read (`setup_scanner/five_minute_lane.py`; the detectors and the scoring take the candle's length). It scores on its own `~5m` rows and never proposes, tells the bot or reaches the Setups board or a Bots card. The 5-minute chart draws its lanes and the day's 5-minute setups that ended (`past-setups?tf=5m`); the 1-minute chart shows one in reach as a chip and its trigger line. On IOVA the 1-minute scanners triggered once in 33 setups and the 5-minute lanes four times; the bar-level 5-minute versions still lost over five years, so nothing trades on them. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | The 5-minute chart on every 1-minute setup, shown and tested (trial T8; operator: "sometimes the 1-minute setup aligns well with the 5-minute setup ... I want to make sure we are utilizing all of that", then "Show it and test it"). Nothing combined the two before: every scanner read 1-minute candles only. Each lane now reads the 5-minute chart from its own minutes (`setup_scanner/five_minute.py`: the last complete 5-minute candle over its 9 EMA and the 5-minute MACD up), records it when a setup arms and when it triggers (`setups.db` schema 4), and the setup rows and the plan show "5m agrees" / "5m against" without blocking anything. Measured first on five years of history: it leaned the right way and did not hold (+0.10R, CI -0.08 to +0.28, the agreeing trades still losing), so trial T8 (`knowledge/signal-trials-3.json`, registered before its data) decides whether "against" ever warns. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | Each chart draws the levels its own candles show, with a Key and a plain card (operator report on XRPN after hours: "why does it say it's a double top when, on the graph, we only see one top? ... Every chart has special needs and special powers ... There's no reason to have duplicate information"; "these hovers are very ugly"; "i get lost"). The 5-minute pane drew today's map, whose tops were counted on 1-minute candles: the HOD's "double top" was two 1-minute tops (17:41, 17:44) inside one 5-minute candle. The level map adds `five_minute`, read from 5-minute candles made of the session's minutes (no VWAP, nothing from yesterday, a round dollar only in a zone with another reason); the 5-minute pane draws it, the 1-minute pane draws its own nearest tops and bottoms, the high of day, the nearest round each side and the plan's levels, and the premarket high and the open moved to the 5-minute. The 1-minute levels were price lines without an axis label, and lightweight-charts 5.1 shows a line's title only beside one: they never showed their names; they are scene levels with labels and cards now. Labels say what the candles made ("$17.50 · double top"); the card is the level, how far, why it is there and what usually happens; every pane has a Key chip. Found with it: the read's price came from a board row the Gainers board stopped repricing at 16:00 (XRPN 16.40 against 17.11), so it now takes the L1 line's last trade; the read's VWAP ran from 04:00 while the chart's restarts at 16:00 (16.29 against 18.62 after hours), so both restart now. Trial T7 still reads the 1-minute map, unchanged. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | The execution door keeps Paper, Sim and Live apart (#655, from the audit that followed the per-venue bot level). In-flight commitments, order watches and releases were keyed by symbol or a bare order id while the Paper matcher runs on every venue: a Paper sell still working refused a Live exit of the same stock, and Paper's fill of order N wrote "Filled" into Live's order N. Commitments and watches are now per venue, `execute` reads the venue once and sends to the one it validated on (`VENUE_CHANGED` when the desk moves mid-check), and a cancel or replace may name the venue it means. §3 amended. | User Directive + Claude Sonnet 5.5 |
| 2026-09-30 | The bot's level belongs to a venue (operator report: "When I switch between L0 and L2 in the paper, it stays persistent when I switch to live, and I feel like that shouldn't happen"). The session kept one `level`, so Paper's Strategy was Live's the moment the desk moved. Each venue now keeps its own level, setup levels, bot trip latch and bot orders (`bot/venue_levels.py`), and a venue change deactivates the bot. Found with it: the all-stop never tripped again after its first trip (a stale lock date read as locked), the bot trip's latch never lapsed and was shared across venues, the daily entry cap counted every venue, a TTL cancel or a take-over could send a Paper order id to Live, and a ticket's open confirm survived a venue switch. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | Support and resistance on the charts and in the plan (ADR 036 amendment; operator: "say our target is 1:2 ratio for trades is too generic, sometimes we have to look at the very obvious resistance/support levels", then "the material teach us that there are stops at half dollar or full dollar which are great psychological triggers", and on mockup v3 "we are overloading the 1min chart"). Measured first on five years of minute bars: half and whole dollars turn price back before they break (76% of fresh approaches printed through within 10 minutes, against 84% at a random price) and trigger once through (77% ran +1.5% first, against 70%); the high of day and tested tops slow price a little; old daily highs do not; capping a target at a level costs. So the target stays 2R, and the levels describe: `stock_read/level_map.py` builds today's map and the daily map, the 5-minute pane draws today's, the Full Day pane the daily one, the 1-minute only the plan's levels between its stop and target, each label or axis tick opens a card with what the study measured, and the plan says Room, the round at the target and at the stop and the next round. Room under 2R is amber and trial T7 (`knowledge/signal-trials-2.json`, the second registry version) decides whether it ever blocks. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | Desk and backend are one version (operator: "it ask me first to reboot the backend or whatever cuz its older, then i press that, then it ask me to pull master!! why cant we just update both frontend and backend in one go after every update!?", then "now it says frontend 1050 and backend 1051 ... lets keep them walking in a single version!" and "i need them to be treated as ONE"). The backend notice offered Restart backend now while the checkout was ahead of the backend, then Pull master and restart once it was not; and the pull took master's newest commit, v1051, while v1051's installer was still building, so the backend overtook the desk. The backend's checkout now only ever comes to the desk's own release tag. Restart to update carries it: the desk lists what a backend restart would interrupt, brings the checkout to the release being installed, and the new desk restarts the backend onto it. The notice has one action (Update backend to vNNN, or Update desk to vNNN when the backend is ahead), and the title names one version when they match. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | Past setup labels make room (ADR 036 amendment; operator: "i do really like seeing the details, but perhaps it is extremely too crowded. how do we help that? maybe a checkbox or compact form"). The 1-minute chart wrote each past setup's whole label at its box's corner with no idea where the others were: LGHL that morning drew 15, and on the Trader's 400 px pane they stacked into unreadable piles. A legend chip beside "Past" now sets Compact (the default, then "maybe the compact form should just show (x) and when we hover, it shows the full failed setup": a mark alone, ✕ ○ ✓, whose hover tells the whole story) or Full, and in both the labels are placed: live labels, levels and the pin stay put, and each past label -- a trigger's result first, then the newest -- takes the longest form that touches nothing already placed, down to its mark or none; its box and hover stay. Checked by rendering LGHL's real day through the real primitive, before and after, and pointing at each of its 9 marks (all outside their boxes) in headless Chromium. §3 amended; `nova.stockRead.layers` adds `labels`. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | Signal trials, and setups first for the Level 2 lines (ADR 041; operator: "how can we use all this data to determine if we should buy or sell or hold?", then "combining time and sale with all 4 colors ... think about all of that!", then "i like it. go"). A study of every Level 2, Time & Sales and setup signal on 25 Session Records over 6 days, each result checked by two reviewers, found no buy edge (a random long loses 6.85c; every green Time & Sales event, a 12-feature model and every setup type lose too) and, in sample only, a 30 s flush exit and two don't-buy states. None of it becomes a call until it passes a trial registered before its data exists: `knowledge/signal-trials.json` (T1-T6), frozen by hash. Nova held no depth line at 50 of 62 setup triggers, so auto-record now gives its free lines to setups in a trade, near or armed before the leaders, and keeps a trade's line to the end of its scoring window. The operator's calls (risk under 5c warns; a flush-30 template on the Paper bot; Approve may hold Nova's exits on Paper) are recorded for later changes. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | The Cryptos page (ADR 040; operator: "give us a new tab called Cryptos and create a dashboard showing what a person need to see in the crypto world", then mockup v1: "go ahead and build exact replica ... when the user hover over things, make sure you show in friendly visual way what does it mean"). A nav-rail page laid out as the approved mockup: market tiles, 13 coins, a Coinbase chart with the day's levels and the 16:00 ET stock close, a 24/7 clock, the stocks that move with crypto (IBKR quotes and regular-hours closes, a 60-session beta and the move it implies), funding and open interest, stablecoin flows, what comes next and classified news. Crypto numbers come from named public reference sources (CoinGecko, Coinbase Exchange, alternative.me, Hyperliquid, DefiLlama, Deribit, Alpaca news), each labelled, a carve-out written into `single-market-data-feed.mdc` rule 13; nothing on the page places or feeds anything. Liquidations, daily ETF flows, a macro calendar and token unlocks have no free source and are stated absences. Nothing polls while the page is closed. Every number opens a hover card: what it means, a small drawing, what it reads now, why it matters. §3 and §4 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | A level a print traded through reads traded (ADR 033 amendment, #636; the operator: "1 go"). IBKR's book trails its tape: a lit print above the best ask (below the best bid) proves the size the book showed at the levels up to its price traded, yet the book can show it for seconds more, and its drop then read pulled. For 3 s after such a print, a drop at one of those levels now first takes that print's own prints at its price, at most the size the book showed there when it went through; new size posted at the level ends it (`matching.Sweeps`). A first build without that limit passed both chance tests, yet 84% of what it relabeled sat at levels refilled after the sweep (on BKYI a 5,600-share bid posted after a sweep and then pulled read traded): a placebo cannot see real prints credited to the wrong drop. Measured on the 27 Session Records of 2026-09-21..29 through the detector itself: the rule adds 0.37% of the size called pulled, 98% of it beyond chance against a tick past and 76% against moved sweeps (on the recordings that kept every book: 0.14%, 91% and 49%); large pulls 11,121 -> 11,071. #637's late book, split: of the through-levels shown late, a third had new size posted first (`depth_late.grew_first`). The window stays 0.5 s. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | The book watcher's matching window, measured (ADR 033 amendment; asked after the hidden-seller study, "change it only if the evidence is clear"). The lit size at the quote that no drop claimed often had a pulled drop at its price nearby, which looked like fills the 0.5 s window missed. `tools/book_watch_window_study.py` (owner `book_watch/window_study.py`) runs the detector over the 27 Session Records of 2026-09-21..29 at 0.5, 1, 2 and 3 s and weighs what a wider window adds against the same prints moved 30-60 s and one tick out: the nearby pulled drops are chance on busy prices (45.3% moved against 44.9% real), the book trails the tape for about 1 in 10 levels a print traded through, and for each late fill a wider window would recover it claims three to five chance prints before the earlier book, six or more past the later one. The window stays 0.5 s; the detector takes it as a parameter (`book_watch/matching.py`), and a lit print now fills only a level at exactly its price (the half-tick test matched midpoint prints to the level below by floating-point error). A targeted fix for the late book is parked as #636. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-30 | Hidden sellers and buyers on Level 2 (ADR 033 amendment; operator: "do we have a way to detect hidden sellers? like we have spoofing!?", then the mockup and "1 go"). The book watcher's mirror of a pull: at a price that held, what traded beyond the most the book ever showed there (`book_watch/hidden.py`). Measured first on every Session Record (`tools/hidden_study.py`, 26 hours with a book): a per-print "unclaimed" count called 60-75% of the volume at the quote hidden (the book and the tape arrive seconds apart), and without a hold the rule fired on sweeps and said nothing. The defaults -- held 10 s, 2,000 printed, 3x the most shown -- are what the study supported: a minute after a hidden seller the price was past the offer 37% of the time against 46% after an offer that showed its size; a hidden buyer made no difference. The ladder outlines the row and marks it in violet, each side's minute line adds "◆", the Tape tile reads "Hidden seller", and `/sensors/flow`'s `iceberg_hint` -- true whenever any level grew -- is now the watcher's word. The setup tape gate is unchanged (the operator's call). §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-29 | Share clips (ADR 039; operator: "I want to be able to record videos. Can I have maybe a small red button ... to share with the world?", seven decisions, then mockup v1 approved: "1 go"). A red ● on every Trader tab opens one Record menu: Market data (the Session Record, unchanged) and Video clip. A clip is marks on ADR 035's always-on screen recording -- no cap, no load, it survives a restart with the gap marked, and Save the last 5 min reads the tab's past. High quality adds a 30 fps capture of the tab's window in its own hidden page (at most 2, 30 min each). The header shows CLIP chips beside REC, a pointed-at chip frames its tab, and Records gains Video clips. Exports are MP4 (H.264) made on a hidden, sandboxed page with WebCodecs + mediabunny: the Trader tab with the header left out by default, the size and P&L panels blurred, hidden stretches cut, high quality where it ran and the screen recording around it. Verified end to end against the desk's real recording on F:, and through the desk itself (the red button, the chip, the toast, the dialog): that run caught an order-ticket blur that named an element no component renders (a test now checks every blur target) and a trim that took the tab to be shown before the clip, so the export now leaves out, and says so, any stretch Nova did not follow. `GET` / `POST /api/clips` and a `clips` checklist row; two unbound Nova Actions. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-29 | GC policy (#619): FinBERT off by default (`NOVA_NEWS_SENTIMENT=1` turns it on) -- its warm-up imported torch and transformers (1,434 modules) on every start and failed anyway -- and the long-lived heap frozen once, `GC_FREEZE_AFTER_SEC` after start (`NOVA_GC_FREEZE=0` off), so full collections walk only what the process made since. Read off the first live census (732,138 objects, 7,037 modules). New package `gc_policy/`; §3 Performance recorder amended. | User Directive + Claude Opus 5.5 |
| 2026-09-29 | Heap census (#619): `GET /api/perf/heap` and an hourly census in the perf day file (`kind: "heap"`) -- tracked objects by type and the backend's biggest containers. Full garbage collections ran about once a minute at a median ~430 ms all day (4.95 s at the open), and only ~60 ms of that was imported code, so the cause is read off the live process before anything is changed. §3 Performance recorder amended. | User Directive + Claude Opus 5.5 |
| 2026-09-29 | The grade you can see, and "not a trade" (operator report: "So why does it think this is a good trade when it's obviously not? ... there is barely any trade or volume"). AVAT's first pullback triggered at 08:06 on one pillar of five, with the tape at WAIT; the scanner scored it stopped out at 08:08, and the Trader's plan still read TRIGGERED with Stage in ticket at 08:28. The % change pillar was unknown on about 40% of arms: it is now measured from the board's prior close when HOD Momo's snapshot has none. Forming rows carry the pillars read at their leg, a filtered setup stays on its card greyed for its whole life, and rows add the tape at the trigger and when the first touch printed. The plan says NOT A TRADE with its reasons (grade C, the template's filter, the tape at the trigger, already played out, a spread at least the risk), locks Stage and Approve, never calls ENTER NOW on it, and shows a played-out setup's result. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-29 | Setups that ended stay on the chart, and what price did next (ADR 036 amendment; operator: "after it fails to form ... it says 'pole' with a gray square. Eventually, it removes itself ... we could probably go back and study them", then "i like this! 1 go"). The 1-minute chart drew only each lane's current state, so a failed or faded setup vanished at the next bar, and nothing scored a setup that died before it armed. `eyes/episodes.py` folds a day's journal into one episode per setup's life on a symbol; `eyes/aftermath.py` measures what price did in the 15 minutes after one died (over the high it was building under, or under the low it would have stopped at, first; a candle doing both counts as the low) and scores the refused trade the way an armed setup is scored. `GET /api/stock-read/{symbol}/past-setups` serves them; the 1-minute pane draws them faint (a failed one from the moment it failed) with `✕` / `✓` / `○`, the rule and what came next, a hover tells the whole story, and the live failed box now says `FAILED` with its rule. `tools/setup_failures.py` totals them by setup and reason across days. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-29 | One backend restart at a time (operator: "Why is it taking forever?"). At 09:35 ET "Restart backend now" stopped v1025. The header's API-down auto-heal asked for its own reload, which queued behind the first; once the watchdog brought up v1030 at 09:36:53, the queued reload stopped it. Each start waited behind the watchdog's ~80 s wait on a Vite that could not start, so the API was down about three minutes at the open. A reload asked while one runs now joins it, the auto-heal restarts nothing that answers `/api/health`, and the watchdog stops waiting on an exited Vite and backs off one that keeps failing. Also: Copy diagnostics copies the rows on screen when the API cannot send its bundle (it said "select the text below" with nothing below), and "UI older than API" no longer offers Reload backend. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-29 | What left the book, on the Level 2 ladder (ADR 033 amendment; operator: "I see massive orders in level 2, and I just think they're disappearing. I don't see them on time and sales"). The book watcher already judged every drop in resting size as traded or pulled, but only a sensor and the Tape tile showed it. The ladder now marks each large drop where the size was, "✕ 2,000 pulled" or "✓ 8,200 traded", for 6 s. The mark is solid when the size was pulled as the price came closer. Rows at a price pulled in the last minute are hatched. Each side gets a line of pulled against traded for the last minute. The verdicts ride on the depth socket (`book_watch` frames); the detector adds `drop` events for large levels that left, traded or not, and per-side totals. Measured on that morning's SSTI, MSGY and MEDS recordings (205 large pulls): 1-5% had the same size reappear 1-3 ticks away, so these are not quotes stepping a tick; about a quarter came back at the same price within 2 s. Also fixed: the reading's `pulls` count was overwritten by the recent-pulls list (the Tape tile read "None pulls"). §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-29 | Who owns the backend (ADR 038, amended; operator: "is this a good design solution?", then "1 go"). The first ADR 038 (`64a25abe`, released as v1028) prompted at every launch for the watchdog's checkout engine, and its default button pointed at the bundled engine, which keeps a separate Paper account and bot session. Now the desk uses whatever answers `:8000` without asking. It remembers the checkout engine as the owner (`engine-owner.json`) and starts that engine on an empty port; the bundled engine starts only without an owner, or by explicit choice after the owner failed. A backend notice offers Restart backend now, or Pull master and restart (fast-forward only, clean master, refused on a requirements change), after asking the backend what is open (`GET /api/diagnostics/restart-check`, new). `/api/health` adds `frozen` and `repo_root`. An unattended nightly pull and restart was proposed and not built, pending the operator's say-so. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-25 | The 1-minute chart stays where the operator put it (operator reports: "Chart unavailable. The scanner is still running.", then "I just sold the stock, and the chart moved"). The stock read set the time scale's `rightOffset` whenever the plan's zones appeared or went. That option is the scroll position, so a buy, a sale, a plan coming or going, or a Trader tab shown again snapped the 1-minute pane to the live edge. Now only a view that follows the live edge slides over to give the zones room. The crashed-pane box names its reason, redraws once on its own, and its Retry button works; it had inherited `pointer-events: none`. The crash itself was not reproduced; its reason now shows on screen. The 04:00 jump from a `bars_patch` swapping histories was fixed separately the same morning (`mergeBarsPatch`). §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-25 | A restart loads only what its checkout holds (operator report: "What does it want? I closed the app and clicked reload backend."). The title read "backend v1017 (older -- restart it)"; the operator reloaded at 07:56 ET and a fresh process came up v1017 again. The engine runs from the git checkout, which was still v1017 until a pull at 07:57, while the desk had updated itself to v1024. `/api/health` and the checklist add `checkout_tag` (the checkout's revision on disk now, re-read off the request path), and the title, Reload backend's confirmation and note, and the `frontend_revision` row say "pull master, then restart" when a restart would load the same code. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | Who trades the stock (ADR 037, #604, #606). Operator asks: "can we have two modes where the entry is automated but the exit is manual?", then "When may Nova buy for you? I want a clear option next to level 2 ... if I selected the exit is on me, then I'm going to be the one who exits, not the bot"; mockup v2 approved, then "1 go". Each stock gets a Buy / Sell switch, above Level 2 and as a chip on the chart, with four modes: Signal only, Approve, Auto-entry and Bot at Strategy. Nova places for a stock only on Paper and on Sim at the live edge; Live is locked with the reason (`auto_live` NO-GO; Approve on Live waits on #604). Auto-entry buys one go trigger at the scanner's entry, sized by the operator's risk per trade, and never sells. Approve sends the plan as one bracket at the trigger. Bot at Strategy is the bot's own list. Take over the exit cancels Nova's exits, and a bot trade ends `handed`. Paper and Sim now fill brackets in Live's shape: the exits are held until the entry fills, then one-cancels-other (#606 step 1). The chart shows the trade's moments live (Forming, Trigger, Holding, the exit) with ENTER NOW / SELL NOW, and Level 2 marks the plan's prices. §3 amended; ADRs 007, 019 and 030 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | Lint never hides the tests (operator pick after PR #603). Five ruff findings on master had skipped pytest on every backend PR since they landed, because CI runs Ruff first in the Backend tests job, and nothing local ran ruff. CI's Run tests step now runs after a Ruff failure (`!cancelled()`, only once the install succeeded), and `ruff check backend` joins `maintainer_checks.py --gate` (`tools/maintainer_lib/lint.py`; kinds `ruff`, `ruff_unavailable`, `ruff_error`). The Agent contract job installs the pinned ruff, so CI's gate and a local one agree. The pin stays in `backend/requirements-dev.txt`, and a test holds every `ruff==` in CI to it. §6.7 added. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | Short interest above the float warns, never gates (#532 follow-up, operator decision: "make sure it never blocks those setups, just gives an on-screen warning"): `float_contradicted` -- the flag every max-float gate reads -- now comes only from the shares-outstanding check. More shares short than the float is also what a heavy short looks like (a lent share can be sold and lent again), so a name with an 8M float, 9M shares short and 12M outstanding had been refused every 10M Low Float gate as a "stale float". It is now `short_above_float`, shown as "9.0M!" in amber with the reason on hover. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | Recorded eyes in Sim (operator ask: "i want this stuff to be recorded when they show up, do they work so they are viewable in the sim ok? when something pops up. that way we can use that data to fine tune them when things dont match"): the setup cards' every change was already journalled (today: YDES's bull-flag pole, PFSA's first pullback armed, near, proposed and triggered at 08:07), but the desk never read the journal -- off the live edge the Bots page kept showing the live board. Now the Sim desk off the edge folds the live journal to the playhead (`eyes/playback.py`): each card's rows and funnel as they stood, proposals popping up as the playhead plays across them, gaps stated, never recomputed. The lanes now write the detector's state whenever it differs from what their lines imply, its price and leg on every line, a `price` line for names in reach, and the engine a minute `beat`, so the played-back card is exact (a test checks the fold against the lanes' own board at every moment). `GET /api/eyes/at` and `tools/eyes_journal.py board` answer the same for an agent. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | The bot's read on one stock (ADR 036, #598; operator ask: "show me the bot's decisions specifically for that stock ... if something is forming, can we start highlighting it on the chart? ... all the tiny signals", then "i want it to tell me my entry/exit .. we typically want to aim for 2:1 ratio, like right on top of lvl2"; mockup v1 approved). Every scanner lane answers for one symbol (`GET /api/setups/symbol/{symbol}`), with the levels a forming setup would arm with (computed, then thrown away until now) and its own MACD / 9 EMA; `backend/stock_read/` composes the owners into seven groups of signals, a plan (entry, stop, target at least 2R from the setup's own rule, and what stands in the way), one symbol's day from the eyes' journal (ADR 029 amended: the desk reads it through the decisions route) and its history. The Trader rail shows the plan and seven tiles above Level 2, a sheet lists every signal, and the 1-minute chart draws each setup as it forms. The plan opens whole only when the quote card has room for it and Level 2 both; below that it is one line (at 1080p, Level 2 kept 302 px of its 354 against 118 with the whole plan). Fixed with it: the VWAP sensor covered only the last 240 bars, the halt sensor read not halted when it did not know, the Level 2 shortability chip asked once per tab. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | Screen recordings are kept (ADR 035 decision 7, operator: "Keep every screen recording until I say otherwise; just warn me when F: gets low"). Nothing deletes a recording; the drive guard -- the header chip amber under 50 GB free and red under 10 GB, and the `screen_recorder` checklist row -- is the warning. No code change: this is what #597 shipped, now decided. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | The trading screen is always recorded (ADR 035, operator: "I always, always, always want the screen that I'm trading to be recorded. Everything ... That's definitely not negotiable."). The desktop app records every monitor from launch to quit, with no off switch: H.264 at 15 fps, each monitor at its Windows layout size, a new file every quarter hour (started before the old one stops) under `F:\Nova\screen`, a day manifest beside them. A hidden recorder window encodes off the desk's threads; the main process restarts any monitor that fails, stalls or disappears (forever, with backoff), replaces a crashed recorder and re-plans on display changes. The header shows a quiet icon while recording and a red "Screen not recording" when not; `POST` / `GET /api/screen-record` and a `screen_recorder` diagnostics row that fails whenever nothing says the screen is recorded. Nothing deletes a recording; retention is the operator's call. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | Watch list toasts follow the setups too (operator ask on a "PFSA is running up" toast: "shouldn't these toast notifications be watching if a strategy is forming?"): the toasts listened only to the HOD Momo feed, so a watched symbol's bull flag or first pullback forming, arming, coming near its trigger or triggering said nothing. The toast now also follows the setup scanner's live board: each setup's climb up the ladder raises it once (flicker and the first frame after a load, a reconnect or Sim are read silently), one toast per symbol still, and its setup lines follow the board while it is up. The board names the symbols it follows (`universe_symbols`), so the Watch list tab's new Setup column says "Not followed" for a watched symbol the scanner does not watch (it follows the HOD Momo names only). §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | A practice send answers when the venue answers (operator report: "This is extremely dangerous. Why are things not getting sent fast enough?"): the Paper ticket read "Placing..." for five seconds after its order filled. The practice broker's notice of a fill at placement reached a watch the send then replaced, and a resting order sent none, so the execution door's acknowledgment wait ran out its full 5 s -- 21 of 23 Paper orders that day, fills in under 150 ms. The broker's own answer is now the acknowledgment (`practice/watch.note_answer`); a replace answers the same way; an order the venue cancels at the fill is refused in its own words instead of reading as placed. Live is unchanged (its record: IBKR's first status in 40 ms to about 1 s). `tools/order_timing.py` prints each order's stages from the running backend. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | The tape flow score and a flush exit (ADR 034; operator ask on a GLND flush in Time & Sales: "can my bots detect ... flush ... so we can exit a position or burst of greens where we can enter ... a small piece of the final decision", then "fine tune the SHIT out of this ... hybrid creative solution and mixing it in the strategies"). One score from -1 to +1 (ask vs bid shares, pace against the tape's own baseline, price move, book depth; an unknown reading drops out, never 0) with every number a template parameter; a template may enter on the score instead of the gate's print counts, and tighten or exit on a flush -- the scoring exit and Nova's bot follow one rule; the defaults are the pre-registered rules. The flow study reads every recorded second (15 recordings: a flush after a rise was followed by -43 bp over a minute; a burst from a flat minute faded) and backtests sweep run-only template variants against a base. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | The forming candle carries its volume (operator report: "i do not see a volume coming up", 1-minute and 5-minute): the live candle was drawn from price ticks only and its volume waited up to ~75 s for the bar store, and every 30 s store refresh flattened the forming candle to one price. Minute and hour panes now count the forming bar's volume from the day volume every trade update already carries, only for bars whose start the pane saw, and a refresh puts the live tip back instead of rebuilding it. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | Ctrl+F finds on the page (operator ask: "can we also do like CTRL+F so maybe we can search on anything in that screen instead of looking everywhere?"): the desktop app had no find at all (Electron ships none). Every window now gets a find bar (`ux/findBar.ts`, searching with `ux/findText.ts`): it marks every shown match, moves with Enter / Shift+Enter, follows the live desk as it changes without scrolling on its own, leaves Ctrl+F to a trading hotkey bound to it, and keeps every key typed in it away from the page. The shortcuts menu lists it. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | Which backend answers, and a reload that is one (operator reports after ADR 031 shipped: "weren't we supposed to see scanners here?", "i clicked the 'reload backend' button, does it still work?", "something in the software title that shows us what backend v### we are using"): the desk had updated while the backend still ran the morning's code, so the Bots page called three built scanners "No scanner yet", and the desktop app's Reload backend said "Backend reloaded" while the same process kept answering -- the installed app looked for the stop script beside itself, found none and re-attached. `/api/health` names its `release_tag`, the window title shows the backend's revision after the desk's and flags an older one, the desktop reload restarts an attached engine from its own checkout and succeeds only on a new `instance_id`, and the Bots page says a backend older than ADR 031 needs a reload. The setup radio now reads "the bot trades this": every scanner runs at once, Eyes on as many as you like, and only the one the bot trades by itself is picked. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | Update takes the newest release (operator report: "when the app detected v1004, there was v1005 already in the pipeline but it didn't catch it"): the desk found v1004 at 10:42 ET; v1005 shipped at 11:30; Update at 13:20 downloaded v1004 from the morning's answer, because re-checks hold 07:00-16:00 and Update never asked again. An Update click on an offer older than a minute now checks GitHub first and downloads the newest release (`frontend/electron/newestRelease.mjs`); the check stays off the notice, and a failed one downloads the release on offer. §8 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | File an issue from the desk (operator ask: "when I do the update, I can also click and say 'File an issue' ... it goes directly to GitHub", then "link the issue/dump file as part of this issue automatically", "humans are not going to ... give you a title or description", and "I really don't want any personal information about my computer ... this is real money"; approved mockup v2): the What's new card and Help > File an Issue… open a form -- Bug or Feature, optional title and description, the desk details and a diagnostics dump attached. One click with nothing typed files a bug that Nova titles and describes from the dump, with no model. The backend (`backend/issue_report/`) files through the GitHub CLI already signed in on the desk, uploads the dump as a secret gist and links it; the operator previews the exact dump first. Everything posted passes one scrubber: no secrets, account ids, balances, paths, user or machine names, e-mail or IP addresses. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | Nova's data leaves C: (operator ask: "we also have PLENTY of space in F drive, any recording and data, lets keep them off the C drive!"): the checkout's `backend\.cache` held 26 GB on C: (the archive, 19 GB of nightly backups, the cold archive, `l2.db`, the ledgers, perf) and `backend\logs` 236 MB, while captures, downloads, the leaderboard, catalysts and eyes were already on F:. `tools/data_root.py move` copies both to `F:\Nova\cache` / `F:\Nova\logs`, verifies every file and leaves directory junctions at the old paths, so every writer keeps its path; it refuses while Nova runs and resumes after an interruption. A per-checkout junction, not a machine-wide F: default, because `api_instance_lock` stops a lock holder it cannot see on its own port: a worktree sharing the desk's cache could stop the live API. `/api/diagnostics` adds the `data_folders` row. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | Sensors for agents (ADR 033, operator ask: "when I have a fast question, you can answer me"; "do we have sensor endpoints? ... our bots have more things to rely on"): `GET /sensors/focus` names the window Windows has in front, its page, symbol, monitor and the operator's last input, reported by every desk window and the Electron main process -- no more guessing which ticker the operator is on. The book watcher (`backend/book_watch/`) follows every held depth line with its tape off the IB loop and splits every drop in resting size into filled and pulled, with `pulled_on_approach` / `repeated_pulls` flags -- hints consistent with spoofing, never a detection (`GET /sensors/book-pulls`, a journal, `tools/book_watch_replay.py`). The L2 sensor's venue rows no longer overwrite each other at one price. A Session Record keeps every book IBKR sends (up to 50 a second, batched to the writer; it kept at most 8 and held back 63% of GCTK's and 76% of PFSA's books on 2026-09-24 while `l2_coalesced` read 0), and the manifest counts every book lost. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | A scanner for every setup (ADR 031, #572; operator: "Weren't we supposed to have a small scanner for each one of these strategies?", then "we are going to need lots of hovers, explaining in detail what each means" and "add a strategy called bull flag"; decisions A / B / C on the mockup). The flat-top breakout (research P2) and red to green (P3) get live detectors on the first pullback's lanes, and the bull flag joins the playbook with rules pre-registered in ADR 031 from the operator's material; each watches the HOD Momo names on every template, reads the same tape gate, scores the same way and keeps its own read-out. A level per setup: the chosen setup's is the session's; every other setup with a scanner is Off (watches and scores, silently -- the first pullback no longer pings at Off) or Eyes (proposes), several at once; only the chosen setup reaches Strategy, and Nova's bot trades the chosen setup on Paper and Sim. `setups.db` schema 3 (`setup_type`, `detail`), the board schema 2 (`setups[]`), `PATCH /api/bot/session {setup_levels}`. Every setup card carries its own small scanner; `ux/hoverTip.ts` explains every chip on hover. Gap and Go's scanner is next; the micro pullback stays parked. Also the loss breakers become the operator's, per venue (ADR 032, operator: "move that slider ... make sure these changes are persistent"): the bot trip and the all-stop are sliders saved in the bot session for Live, Paper and Sim separately, within bounds, and the session file is written atomically. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | Paper resting orders fill again when the tape archive falls behind (operator report: "I don't understand why this is not going through my working order"): an APUS SELL limit at $4.96 rested unfilled while APUS printed $5.00. Resting Paper fills read the L2 tape archive, and its writer had latched at 07:29:41 ET. It wrote one print per connection (about 190 prints/s at best), a 256-print backlog filled as the tape reached 150 written prints/s, and the first overflow shed every later print until a restart. Only `/api/l2/status` said so. The writer (`ibkr/tape_sink.py`) now writes a batch per transaction (about 49,000 prints/s), holds 8,192, states each loss and keeps going. The matcher reads only as far as the archive has written, so a late print is no longer skipped. A `tape_archive` diagnostics row fails while a resting order's prints are not reaching the archive. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | The gap is never yesterday's (operator report: "massive discrepancy between the focus window and the stock quote ... it shows 9.9 when I don't think it is", "the digits on the left side are frozen"): GCTK's Focus rail read +9.9% at $4.13 and $4.16 while the Stock Quote read +103.46% on the 2.03 prior close. IBKR's open tick is the previous session's until 09:30 ET, so the Gainers row's "gap" was yesterday's open-to-close move, and every L1 patch tagged `gappers` wrote it over the Gappers row's real move (a roster replace put the move back: the flicker). The open tick now counts only once today's session has opened (`ibkr/open_tick.py`), and a Gappers patch carries its own gap (`gapper_view.patch_for_table`). §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | Leftover-issue sweep (operator ask: "Do we have any still-leftover issues on GitHub? Can we go ahead and address them?"): all 28 open issues checked against master; five were already fixed and closed (#430, #448, #481, #484, #516). §3 amended for what shipped: scanner snapshots dated by their exchange session (#483); the replayed session's previous close is IBKR's own -- a recorded tick 9, the leaderboard, a download's regular-hours daily close, else none, never a 15:59 or after-hours close (#542); a recording's lost tape line is named, asked for again and counted in the manifest (#525, cause unproven); Time & Sales dims prints that do not set a price, and a capture replay's chart tip and last trade skip them (#543); Form 4 open-market insider purchases are a weak catalyst, rules v7 (#517); a float Yahoo's own counts contradict is flagged and short interest carries its FINRA date, no gate changed (#532, point 2 awaits the operator); the leaderboard store is schema 2 with per-day catalyst items for Sim playback (#498); chart bars coverage says when IBKR history stopped answering, and a failed pair backs off 30 s (#555). Also: the session commission read is cached exactly by ledger generation (#554), the Gateway port probe and HOD Momo's alert writes left the loops (#505, #553), Nova Action cancels and flattens work on a disarmed desk (#548, ADR 018 decision 4), tape and depth lines from an ended IBKR session stop counting as subscribed and are asked for again (#562, `ibkr/line_session.py`), the 17 stale Playwright specs match today's desk (#502), and several QA leftovers (#459, #486, #487). Decisions recorded on their issues: #449, #485, #499, #504, #514, #564; new bugs filed: #563, #565, #566. | User Directive + Claude Opus 5.5 |
| 2026-09-24 | The first-pullback bot trades Paper and Sim; the read-out gates Live (ADR 030, #514; operator report: "When I'm on paper, I cannot activate the button for the bots" -- then "Paper/Sim skip it + build"). Activate at Strategy was locked on every venue by the first-pullback read-out (0 of 50 go setups: a go needs Nova to hold the name's Level 2 at the trigger), and nothing placed a trade on a trigger anyway. Now Paper and Sim skip the read-out (Live keeps it; an unreadable venue counts as Live), and `bot/first_pullback/` trades the template in play's go triggers there through every bot gate: a limit at the scanner's entry, a resting target, a watched stop, a 15-minute time stop, one trade a day (a miss gives the day back). Nothing places on Live. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Nova shows a window the moment it starts (operator pick after the update fix): the desk window was created only once the local engine answered and shown only once its page loaded, so a cold start -- a 2.5 s look for a running engine, the engine's own start, the page load -- had nothing on screen. A small "Starting Nova" window now opens about 0.6 s after launch, names the step (looking for, starting or connecting to the local engine, loading the desk), closes the moment the desk shows, and calls the launch off when the operator closes it. After an update it takes over from the "Updating Nova" window. `startApiSidecar()` now says whether it reused, attached to or spawned the engine. §8 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Release notes and an update you are asked about (operator ask: "after we update to a new version, can we have a release note show up in front of the user? If ... we identify a new update, could we also notify the user if they are interested in updating it or not?"): a check that finds a newer release no longer downloads it in the background -- a notice under the header names the release with its notes and asks Update / Later, then follows the download to Restart to update; it never takes keyboard focus, and a window that cannot show it gets the same questions as dialogs. The first launch of a new version shows What's new, a floating card with the notes of every release the update brought (Help > What's New reopens it). Release bodies were boilerplate; `Desktop pack` now writes them from the commit (`tools/release_notes.py`: PR title plus the first paragraph of `## What`, and a hidden record the desk parses). §3 and §8 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | "Restart to update" shows that it is working (operator report: "I said yes, and nothing happened"): v976 had installed and reopened correctly, but the silent installer left nothing of Nova on screen for 46 s. An "Updating Nova" window now appears at the click and names each step it can see (Nova closing, the installer running, the new Nova starting), closes itself when the new window is up, and says "Nova did not reopen" with the log path if it does not. It is a separate Windows PowerShell process started through `cmd /c start`, because a detached powershell.exe quits without a console and an attached child dies with Nova. §8 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | A watch list of the operator's own (operator ask: "When I highlight a row in any ticker, I want the option to say 'Add to watch list' ... anytime it crosses the HOD/MOMO, it shows me a toast notification"; the old list renamed, "come up with a creative name"): `watch_list/` keeps hand-picked symbols in `localStorage` `nova.watch.list` (schema 1, shared by every window), added from a highlighted scanner row's Watch action, the symbol menu on every ticker list, the chart menu (its disabled "Add to Watchlist" now works) or the new Watch list tab; the Focus rail and Desk board can mirror it. A live HOD Momo or Running Up alert for a watched symbol toasts on every page of the main desk. The ranked Five Pillars tab is now **Contenders** and the scanner's "Watch" column **Pillars**; ids and API paths unchanged. Also: a pop-out Trader window mounts its own symbol menu, so right-clicking its tabs or Focus rail rows no longer eats the browser menu and shows nothing; and that menu is redesigned (operator: "it's so hard to even know they are clickable") -- the symbol once in its head, each action a button-like row with a coloured icon, a line saying what it does and a chip when it is already on, opening upward near the bottom of the screen. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Level 2 books kept with IBKR's row rules and the prior close never a trade (#540, #541, found by the data-accuracy audit): ib_async's dict-keyed depth book put 466 of GRML 2026-09-22's 111,116 recorded books out of price order, so `ibkr/depth/book.py` now keeps each line's book from `ticker.domTicks` and recorded books read best-price-first. IBKR's prior close before a line's first trade no longer makes live minute candles (APLX 2026-09-23 16:00 opened at the 9.52 prior close while trades printed 8.55-8.71), HOD Momo trades, L1 archive ticks, chart-tip trade updates or HOD enrichment prices; Paper and Sim-at-the-edge take the L1 last only when IBKR's Last Timestamp is inside `PRACTICE_LIVE_FRESH_SEC`; the ticker snapshot carries the trade's own time, `null` volume when unknown, and no last before the first trade. §3 and `architecture/practice-fills.md` amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Every locked control says why; setup templates; the eyes on the record (ADR 029, operator asks: "these are always unclickable, at least it should explain why ... gaps may exist everywhere"; "I also need to see all their parameters and be able to change them myself"; "each strategy will have templates"; "when we activate the eyes I also want it to be recording what it sees ... and when we are in the Sim I want to be able to use these eyes so we can backtest them"). One tip per window shows a locked control's `data-why` on hover and on a refused press; all 134 disabled controls across 64 files carry a specific reason and a test fails the build on a new one without. Each setup lists every parameter it runs on (a catalogue; the Bots page renders it, never prose -- the old card said 07:00-10:00 and $3-10 where the scanner arms 07:00-11:30 on any HOD Momo name); each setup keeps a locked pre-registered default and the operator's templates; every first-pullback template is watched at once and scored on its own rows (`setups.db` schema 2), only the one in play proposes, and the read-out is per template revision. The eyes' journal records everything the lanes see, per day, backend only; the same lanes replay a Session Record to follow the Sim playhead or backtest templates. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Session Record replays draw candles from their prints (#535, operator decision: option a): the capture player no longer reads the stored `bars_*.jsonl` buckets, which recordings made before candles took only price-setting prints had built from every print (GRML 2026-09-22: 82 of 480 one-minute candles with a false wick, a low of 13.19 where trades bottomed at 15.43). Every timeframe is aggregated from the prints that set a price, filtered once per loaded recording, so the chart and the practice fills (#511) read the same prints. `replay_load.counts` drops the `bars_*` counts. §3 and ADR 012 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Practice fills only on prints that set a price (#511): a volume-only print (odd lot, average price, derivatively priced, prior reference, or anything IBKR flags `unreported`) can sit dollars from the market -- PLTR `190.38 x 100  4 W` against a 192.64 x 192.80 book -- and a resting practice limit used to fill on it. Paper's live reference (newest print and resting-order matcher) and a capture replay's last and matcher now use `sale_conditions.row_sets_price`, the rule candles already follow; `tape_trades` keeps IBKR's `unreported` flag; the unused batched tape writer, which stored prints without their conditions, is removed. §3 and `architecture/practice-fills.md` amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Why it's moving (ADR 028, operator ask: "I want to know why from the user interface ... especially if it's squeezing and without news"; "run that through data and analytics where we don't need to consume tokens"): `GET /api/why/{symbol}` and a section at the top of the Trader tab's News panel give a rules read -- company news, halts, float and its turnover, a recent reverse split, short interest and IBKR's borrow market -- each check yes / no / unknown with its source, and a likely cause (news, short squeeze, supply squeeze after a split, low-float momentum, routine item, thin trading, nothing found) that says `possible` when a deciding fact is unknown. No model, no tokens. The borrow market is new data: IBKR's public short-stock file, polled every 15 minutes into `borrow.sqlite3` (changes only) so a restart keeps the day's fee and availability history. On 2026-09-23's gainers it named MSS and WHLR squeezes, VSA / IPDN / ONCO low-float momentum on tight borrow, and ARTL a routine item on a low float -- matching the hand audit. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | The open desk re-checks for updates (operator ask: "Should Nova also check for updates every few hours while it's open, still asking before it restarts?" -- "go"): a desk left running all day checked only at launch and missed every release until it was reopened. It now re-checks every two hours while open, never 07:00-16:00 ET on a weekday -- a 150 MB download mid-trade shares the lossy link with the market data, and the restart prompt takes keyboard focus from the hotkeys; an update found as trading starts is offered after 16:00. Installing is still only the operator's Restart to update. Same day, on the desk: v962's one-shot download failed 3 of 3 on the lossy link, and v964's resumable one fetched v965 through a dropped chunk in 11 s, then installed and reopened in 26 s. §8 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Who may arm the desk (ADR 018 amendment, operator decision: "I want the bot to be able to unlock [Paper / Sim] themselves through an endpoint, but I don't want the live trade to ever get unlocked without my permission"): one door (`POST /api/ibkr/arm`) and one rule (`ibkr/safety.arm`) -- Live arms only with the operator's PIN, now checked by the backend against a PBKDF2 hash in `.env` (`tools/set_live_arm_pin.py`), with a lockout after wrong PINs; Paper and Sim arm with no PIN, from the padlock in one click or a bot. The PIN had been a constant in the public frontend source, compared in the browser, while the endpoint armed Live for any local caller. The latch is stamped with its venue, so a practice arm never reads as a Live arm. The frontend's per-tab unlock flag and its cross-window sync are gone: every window reads the backend latch. Also from the same after-hours test run: a running recording is never finalized by another process's startup, tests never resolve the F: archives, Vite's dependency cache moved out of the shared `node_modules`, and Flatten on a flat practice position says it is not a close. §3 and §5 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Movers get the news that moved them (operator report: "most stocks don't have news, and they are moving"). Audit of the day's boards: 24 of 28 checked movers had no release or filing at all, so an empty News column is often the truth; the desk's own misses were a backend still running code from before the verdict reached the rows, a Windows Update restart that cost the wire feed the whole premarket, Benzinga "what's going on" pieces whose summaries named the cause (BENF, ARTL, BFRG) filed as movers lists, and screens / plural lists / cover-page addresses mislabelled. Rules v6 reads a one-ticker rewrite's stated cause; Finnhub company news joins the live verdict (`catalysts/live_finnhub.py`: answers for the window after the fact, carries Yahoo copies of GlobeNewswire / PR Newswire / ACCESS / Business Wire releases; its Benzinga copies are dropped for their four-hours-early clock, #516, in research too). Honest clocks move the research's leaderboard coverage (none found 23% -> 40%) but not the first-pullback split. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | In-app updates survive a lossy link (operator report: "Update check failed -- net::ERR_SSL_PROTOCOL_ERROR" on v959): the check worked, the 150 MB installer download failed every time. This PC's Wi-Fi corrupts a TLS record every few dozen MB (Windows curl `SEC_E_DECRYPT_FAILURE` from GitHub, Hetzner and OVH; 6 GB over loopback TLS clean), and electron-updater restarts a failed download from zero. `frontend/electron/updateDownload.mjs` now fetches it in resumable, individually retried chunks, keeps the part, checks the release sha512 and hands the file to electron-updater's cache; the Help menu names a stopped download as one ("stopped at N% -- Resume"); `update.log` records every step. §8 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Code-shape rules measure behavior, not a snapshot (operator ask: "'All files are under 400 lines' -- is this an actual rule? ... how do we create better rules to manage the scalability of this project?"). §2 rewritten: the hand-kept file trees become ownership statements next to the code (backend package docstrings, `frontend/src/FOLDERS.md`) that the checker keeps complete, printed by `tools/module_map.py`; the hard 400-line cliff -- which bunched ten files at 395-400 lines -- becomes a soft limit that asks for a one-concern reason, a no-growth check without one, and an 800-line ceiling; constants tables are exempt; the .tsx 300 rule (which contradicted §2.3) is gone; feature-slice deep imports are frozen per file (340 on the day) instead of checked for 9 of 34 slices. §6.3: silent failures on the money path fail the gate; 22 sites fixed or given a reason, three of them real misreports (a practice flatten reported flat when its re-read failed, the startup sweep could call a filled order abandoned when `ib.fills()` failed, a partly unreadable commission total was shown as the total). CI runs `maintainer_checks.py --gate`. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | The Bots page as approved (mockup v4; operator report: "my screen looks nothing like the mock up + half of buttons don't work", "I want to see that L2 stuff in my header"): Bots is a shell page like Account, not a tab squeezed between the HOD strip, the positions dock and the quote panel. Every control works or says why not: the gate chips carry the link that opens them (unlock the padlock, open a symbol's Level 2 in a pinned Trader tab, see the read-out, add a symbol, reset the kill switch), choosing Strategy with the padlock locked says so, the setup radios and each setup's level switch are real (disabled with the reason where no scanner exists), "+ Add a setup" explains the door and copies the catalogue path, the sleeve is sliders that PATCH once let go, and the breakers draw today's P&L. Symbols say who holds the line with Last and Change; proposals keep the ones the scanner withdrew (closes now on the audit stream); the timeline adds the setup scanner's own day (setups.db); Today adds bot P&L from the practice ledger. The header carries the bot pill ("Bot L2 First pullback · Not active") and the rail a state dot. The quote panel folds to a strip on the right like the Focus list, streaming nothing while folded, and grades any symbol's Five Pillars (`GET /api/strategy/watchlist/{symbol}`). An API older than ADR 027 is named as such instead of "every gate is open". The course vendor's name left the UI. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | Automatic release tags (operator ask: "after every commit we make to master, can we create a release tag"): `Desktop pack` tags every master commit `vNNN` and publishes an application-affecting one as a GitHub Release with the installer and update feed; docs/site-only commits get the tag only. Master runs group by commit so a burst of merges tags every one, and a Release is marked latest only when it is the highest. Supersedes #347's operator-tag-only publishing; the installed desk now offers an update after each application merge. §8 amended. | User Directive + Claude Code |
| 2026-09-23 | The catalyst verdict on the desk (ADR 024 amendment, operator report: "still just seeing garbage"): the Gainers' top three all showed one Benzinga market wrap as their news, IPDN's panel called it "moved price 90%", and real releases (HCTI's PR Newswire LOI, BENF's 8-K) showed nothing -- the verdict fed only the setup scanner. Scanner rows now carry `catalyst` (`catalysts/board.py`); the News column, "Has news" chip, Trader tab chip, HOD flame and the Watchlist pillar read it; the Trader's News panel reads `GET /api/catalysts/{symbol}` (verdict + labelled items, lists folded away). Rules v5: share consolidations are reverse splits, circuit-breaker notices are halts not news, "beat the market" is not an ATM offering, debt elimination and customer wins count, a movers-section URL needs a placed class; the SEC headline joiner stops cutting on "and". `has_news` keeps its meaning. §3 amended. | User Directive + Claude Opus 5.5 |
| 2026-09-23 | The bot plays the operator's setups (ADR 027, operator decision: "no, I don't think we need the old packs -- remove"; "keep the Strategy L2 + all setups from my material"; approved Bots mockup v4): the halt-luld / quote-spike / volume / llm-decide packs, `POST /api/bot/llm/spend` and the `nova-brain` sidecar (Electron, `scripts/windows/Run Nova.bat`, `Start-NovaBrain.ps1`) are removed; the session (schema 4) carries `setup`, `setups`, `readout` and `gates`. Strategy waits on the pre-registered first-pullback read-out (`setup_scanner/readout.py`, Bot-Trading-Plan §2g): raising to Strategy lands not active, Activate at Strategy and every L2 fire are refused `BOT_READOUT_NOT_PASSED` until 50 triggered go setups beat +0.2R net and blind / wait; L2 entries keep the material's 07:00-10:00 ET window and one trade a day. The Bots page is rebuilt (hero with level, gates and Activate; the playbook with first pullback's rules, tape gate and read-out; symbols with Level 2; sleeve and breakers; one proposals inbox; the activity timeline; today and the scoreboard) and the header's second bot row is gone. §3 amended. | User Directive + Claude Opus 5.5 |
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
