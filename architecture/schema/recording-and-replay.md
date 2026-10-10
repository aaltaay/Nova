# Data schema: Recording, replay and the practice venues

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/capture/, backend/sim/, backend/practice/, backend/l2/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## Capture / replay truth (issues #316, #317)

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

## Replay progress and capture fidelity (#321, #337)

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
`tape_losses: [{at, cause: "ib_error" | "stale" | "pipeline", detail}]` (the recording's
tape line lost while it ran, newest last, at most `CAPTURE_TAPE_LOSS_KEEP`;
both carried across segments of the day, #525). The manifest's `fidelity` is
written when a segment starts, at once on every tape loss or re-ask, and every
`CAPTURE_MANIFEST_CHECKPOINT_SEC` while it records, so a segment a restart ends
keeps them (before #722 only a clean stop wrote it: VEEA on 2026-10-05 kept its
07:00-07:13 segment's fidelity through two restarts, with none of its 09:37-09:45
re-asks); the startup finalizer takes `last_stream_ts` from the newest row of
each stream on disk. A checkpoint never touches `counts`, which the finalizer
recounts against. Diagnostics are counts except
`legacy_schema` / `l2_decimated` (booleans), `last_stream_ts` (per-stream event
timestamps) and `tape_losses`.
No automatic retention policy is selected by these additions.

## Recording persistence and coverage (operator decision, 2026-09-21)

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
carries `line_since`, when its line opened, and `last_print_exchange_ts`, the last print's
IBKR second) then reads `disconnected` with
`ended: {at, cause, code, message, req_id}`. `capture/tape_watch.py` also calls a line dead when no print
came for `CAPTURE_TAPE_STALE_SEC` and the symbol's Level 1 line reported a trade after the last
print (#722, `ibkr/tape_silence.py`); when that Level 1 line is updating and reports no trade
since, the name is quiet and nothing is asked for. Without a Level 1 trade clock it falls back to
the book: dead when the book updated within `CAPTURE_TAPE_BOOK_FRESH_SEC` (a quiet name looks the
same; asking again is harmless). A line that went silent in the same second as other live tape
lines is one event (`cause: "pipeline"`): it is said, but held -- not dropped, not asked for --
until one of those lines prints again or closes, or for `CAPTURE_TAPE_PIPELINE_HOLD_MAX_SEC`, and
then judged like any other (on 2026-10-05 asks inside the event brought nothing back). Either way
the keepalive asks for the tape only -- the depth line is
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

## Recorded depth in historical replay (#309)

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

## The replayed session's previous close (#542)

Owner `sim/prior_close.py`. The `prev_close` a Sim replay measures change and
Gap% from -- `replay_quote.prev_close`, a loaded capture's quote and ticker
projections (one value per load, whichever row is read), the historical
snapshot's `prev_close` and the eyes' replays -- is, first answer wins:
IBKR's tick-9 close recorded with the Session Record (the most common positive
`prev_close` on its quote rows from 04:00 ET of that day); the leaderboard's
`prev_close` for that symbol-day (recorded rows before reconstructed ones, the
day's most common value; read read-only, so a read never creates the store);
IBKR's regular-hours daily close of the prior session, stored with a
historical download of that symbol-day; the prior session's close in the
operator's Massive day bars (`sim/massive_daily.py`, `day_aggs_v1`: the
official close, as traded -- after the split-aware answers -- and only that
session's file, never an older one; operator 2026-10-09); else `null` -- a
stated absence, no change and no Gap%. One unreadable source never hides the
next. Never the prior session's 15:59 one-minute close (the last
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

## Massive flat files in Sim replay (ADR 046, operator ask 2026-10-06)

"u wanna populate the data inside the sim? that way when we go back in time, the data we downloaded all of
its information gets picked up?", then "1 go also do the bid and ask." A historical window comes from an IBKR
download or from the operator's Massive flat files (owners `sim/massive_files.py` the files,
`sim/massive_read.py` the import itself, `sim/massive_import.py` + `sim/massive_worker.py` its job and process,
`sim/massive_store.py` the store, `sim/history_quotes.py` the NBBO, `sim/massive_days.py` the days on disk; on the
desk `frontend/src/sim/massiveDaysStore.ts` and the Sim panes).

- **The files.** `NOVA_MARKET_DATA_DIR` (default `E:\Nova\massive`), laid out as Massive serves them:
  `<root>/<trades_v1 | quotes_v1 | minute_aggs_v1>/YYYY/MM/YYYY-MM-DD.csv.gz`, one gzip CSV per dataset per day,
  every ticker, sorted by ticker. A file counts only whole (a `.part` still arriving does not).
- **Choosing the source -- the files first** (operator 2026-10-09: "shouldn't we have prioritized it over ibkr
  data?"). `POST /api/sim/history` and `POST /api/sim/history/select` add `source: "auto" | "ibkr" | "massive"`
  (default `auto`). A download takes the Massive files when the day's trades file is on disk, else IBKR; `kind`
  does not matter for Massive (one import fills trades, bars and quotes). A selection takes a Massive import that
  holds the window; else the Massive files when the day is on disk -- **even over an IBKR download of the same
  hours**, which plays only when the files' import of the window failed or the day is not in them -- and
  **starts the import** when none is running or complete, loading the window empty until the desk's quiet
  re-select folds it in. `POST /{job_id}/pause` and `/resume` route by the job's store; a Massive resume
  imports the window again from the start.
- **Jobs.** The listing (`GET /api/sim/history`) returns IBKR downloads and Massive imports together, most
  recently updated first. Every job carries `source` (`ibkr_historical` | `massive`). A Massive job is shaped
  like a download (`id`, `kind: "trades"`, `status`, `ranges`, `count`, `volume`, `progress_pct`, `eta_seconds`,
  `stale`, ...) with `precision: "nanoseconds"` and adds `stage: "reading" | "saving" | null`, `stages:
  {trades_v1, quotes_v1, minute_aggs_v1: percent} | null`, `scan_pct`, `bar_count`, `minutes_scope: "day" |
  null` (the import kept the ticker's whole day of 1-minute bars; null for an import before 2026-10-09, or with
  no bars file), `quote_count`,
  `quote_status: "complete" | "none" | "not_downloaded" | null`, `files: {trades, quotes, minute_aggs}`,
  `elapsed_sec`. `status` is `queued | running | complete | failed | paused | interrupted` (a running job
  rewritten by no live import for 60 s). The listing adds `massive: {available, reason, root, store,
  trade_days, quote_days, first, last, last_landed, store_error}` -- `last_landed` the epoch seconds `last`'s
  trades file was finished on disk (its modified time; null when unknown), `store_error` names why the import
  store could not be read (its imports are then not listed), null when it could.
- **Days on disk.** `GET /api/sim/history/massive/days` -> `{schema_version: 1, available, reason, root, days:
  [{date, trades, quotes, minute_aggs}]}`, newest first, the folder walked at most once a minute;
  `GET /api/sim/history/massive/{date}` -> `{date, available, reason, trades, quotes, minute_aggs}` (422 for a
  bad date; `available` false with the reason when that day's trades file is not on disk).
- **The import.** Its own process (`python -m sim.massive_worker --job-id ID`, frozen `nova-api.exe
  --massive-import --job-id ID`), below normal priority, one at a time; the three files are read side by side,
  each to the end of the ticker's block, every row parsed with the csv module. The window's prints (typed), the
  ticker's whole day of 1-minute bars (operator 2026-10-09; only the window's before) and the window's NBBO
  rows -- plus the quote standing at the window's open -- are written in one transaction. More than 500,000 prints (`SIM_HISTORY_MAX_SELECTION_PRINTS`) or 4,000,000 quotes
  (`SIM_MASSIVE_MAX_SELECTION_QUOTES`) is refused with the reason before anything is written. A day without its
  quotes file imports trades and bars with `quote_status: "not_downloaded"`; a download or selection after
  that file arrives imports the window again, and the window imported before keeps playing until the new one
  replaces it; so does a window imported before `minutes_scope: "day"` once its day's bars file is on disk. Pause ends the process (`paused`); a process that ends otherwise leaves `failed` with its exit
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
  never the IBKR chart store, which a Massive import never writes -- and the day before the window is drawn
  from those bars (never past the window's end or the playhead); the replay bars answer `source: "massive"`
  for the loaded symbol (it read `ibkr`). Its session open (Gap%) is the 09:30 print in the window, else its
  own 09:30 bar -- never the IBKR chart store's.
- **On the desk.** The Sim Day calendar marks a day whose trades are in the files (a bar under the number; the
  title says whether its bid/ask is there) and lets it be opened, whatever else is on file. A Sim tab on such a
  day offers **Load from files** with no Gateway gating; its import has its own slot (an IBKR download of
  another window does not block it), Stop pauses it, and the window loads when it completes. The quote card and
  the ticket take `bid` / `ask` (a Market order is priced at the far side), Time & Sales dims prints with
  `sets_price: false` and says its colours come from the NBBO, and the Level 2 note reads "Best bid / ask
  (NBBO) at HH:MM:SS ET · no depth in the files", or why there is no quote (not downloaded yet, on disk now --
  load again, none in the window). The quiet re-select keeps the loaded window's source and reloads a Massive
  window once, when an import of it completes with something the loaded copy lacks (its trades, bid/ask, or
  `bar_count`).
- **It loads by itself on an empty desk** (operator 2026-10-09: "i dont think the entire nova app recognize
  massive as data recap for the sim"). With nothing loaded, the Trader tab on screen on a day in the files
  imports and loads its window without a click, as the agent's `show` does; never over a loaded replay, never
  an IBKR download, once per window (a failed or stopped one waits for the operator). A day newer than the
  files says so on the tab -- "Fri, Oct 9 is not in your Massive files yet: they end at Thu, Oct 8, which
  landed Fri 03:37 ET" (Massive publishes a day once it has ended) -- and that until it lands a download is
  IBKR's.

## Practice venues and fills (ADR 019, ADR 020)

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
never a guess), `PRACTICE_BUYING_POWER` (both: a buy's buying power, a short's
margin), `PRACTICE_NO_SHORTS` (both: a short is never inferred -- a SELL beyond
the held quantity without `short_entry` is refused "A SELL never sells past what
you hold: a short goes out as a short entry, with its buy stop"),
`PRACTICE_SHORT_WHILE_LONG` (both: a short entry never flips a long, ADR 048) and
`PRACTICE_TIF_EXPIRED` (both: a `DAY` order expires at its session's close --
20:00 ET on Paper, the replayed window's end on Sim -- as an `expired` ledger
event with status `Expired`; `GTC` persists across days and restarts; the row
and its `placed` event carry `tif` and `expires_ts`), and `PRACTICE_GOOD_FOR_EXPIRED`
(both: an order sent with `good_for_sec` expires unfilled at its placement plus those
seconds when that comes before its TIF's close -- "A practice order's own expiry" in
`execution.md`). Recorded prints carry
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
admission, `PRACTICE_SHORT_WHILE_LONG` -- a bracket that opens with a SELL is a
short bracket, from flat or adding to a short (ADR 048), whose target may be left
out: two consecutive ids -- and buying power, or a short's margin, at the entry's limit). The ticket's Flatten counts a
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
  `PRACTICE_TIF_EXPIRED`, `PRACTICE_GOOD_FOR_EXPIRED`, `PRACTICE_OCO_CANCELLED` or
  `PRACTICE_PARENT_CANCELLED`, closes it `cancelled` with that code;
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

## Sim at now is live -- the live edge (ADR 020 amendment, operator decision 2026-09-21 evening)

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

