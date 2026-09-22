# Historical replay (ADR 012 archive extension, D-052)

ADR 017 assigns the sole Historical replay surface to `backend/sim/history_*`.
Live tab capture is a print feeder; `backend/l2/` is the hot depth/tape sink.
AllLast fans out to their independent bounded workers. The legacy JSONL player
remains a compatibility path pending canonical import; this does not add live
quotes/depth or practice fills to Historical replay.

Any qualified stock ticker can select a historical Eastern date and same-day
window. Candles already in the local IBKR bars archive are immediately usable.
**Download candles** makes one bounded historical-bar request for the window;
nothing is fetched automatically. Completed OHLCV is revealed only at interval
close. Trade downloading is optional enrichment, not a prerequisite for candles.

`POST /api/sim/history` accepts `{symbol,date,start,end,kind}` where times are
HH:MM in America/New_York and kind is `bars` or `trades`. Windows are half-open
[start,end), past-only and within one calendar day. GET lists durable jobs, the
archive path and `default_date` (the latest weekday that is not an NYSE holiday
and whose default 20:00 ET close has passed). POST `/{id}/resume` resumes
queued, paused, failed or interrupted work; POST `/{id}/pause` requests a stop
after the current atomic page. A download request is refused, without creating
a job, while another download is active. POST `/select` accepts the same window
(without kind) and chooses historical playback. It reads an existing trades job
but never creates one. No fixed ticker allowlist.

SQLite under `F:\Nova\sim\_capture\historical` (user-selected durable area;
`NOVA_SIM_HISTORY_DIR` override, existing capture-root fallback off Windows) stores jobs,
contract identity, source, timezone, coverage, ordered events and page cursors.
Events use an ordinal primary key, never price/time/size deduplication. IBKR
finishes the last second of a historical-tick page; commit that entire second
and resume at last timestamp + one second. Page rows and cursor commit in one
transaction. A retry cannot append an already committed page. Status changes
are atomic read-modify-writes, so a pause request is never overwritten.
Errors, timeouts, invalid ordering or nonadvancing responses stop the job with
resumable progress. Coverage is a set of merged, half-open second ranges, not
one cursor: a page covers [cursor, following) and is merged in. Playhead-first
acquisition: scrubbing a selection whose trades job is running to an uncovered
second records a seek; before its next request the worker moves its cursor to
the start of that gap, then fetches forward. A page is clipped at the next
already-covered second (no duplicate prints) and the cursor jumps past that
range; reaching the window end wraps to the first gap from the start. Prints are
read back in (timestamp, ordinal) order because insertion order is no longer
time order. The job is complete only when one range spans the whole window. Completion describes the IBKR response range, not a claim of
consolidated market completeness. Downloaded candles are kept in the archive
with their job identity and are also upserted into the shared bars store.
Coarser derived bars exclude incomplete window-edge buckets.

One worker and a durable send timestamp serialize downloads and enforce a
conservative 11-second request interval (16 seconds before retrying a failed
request). Requests have timeouts and a bounded page count. A separate read-only
Gateway connection (its own client id and event loop, no account/order fetches)
tries the live port only; the legacy paper port is tried only with the
`IBKR_PAPER_GATEWAY_FALLBACK` opt-in (ADR 020, amendment 2). Its client id is
`SIM_HISTORY_CLIENT_ID`, overridable with `NOVA_SIM_HISTORY_CLIENT_ID` so a
second stack never shares it. The store follows `NOVA_SIM_HISTORY_DIR`, else
the durable `F:` archive, else the capture root. It never follows a redirected
`NOVA_SIM_CAPTURE_DIR` while `F:` exists -- the operator's own `.env` sets that
variable -- so an isolated test stack must set `NOVA_SIM_HISTORY_DIR`.
The IBKR adapter only fetches; the SIM downloader owns persistence. Tunables
live in `backend/constants_sim.py`. This budget does not account for other
applications; IBKR pacing rejections are surfaced as resumable failures rather
than retried in a loop.

Playback loads an immutable in-memory snapshot of reached download coverage
(very large windows load more slowly). Trade-derived bars take precedence only
for buckets that lie wholly inside one downloaded range; every other bucket --
in a gap, or straddling a range edge -- uses archived OHLCV. Buckets are
aggregated and flat-filled per range, never across a gap, so an undownloaded
stretch is never drawn as a quiet one. Partial bars use reached trades; all same-second prints arrive
together, in returned order. Candles, last price and volume use only prints
IBKR reports as tape-eligible (`unreported` false); Time & Sales lists every
reached print and marks unreported ones (IMCC: odd-lot/Form T `TI`/`FTI`
prints would otherwise invent highs such as 2.00 against a 1.88 bar). With that
rule replay OHLCV equals IBKR's own 1-minute bars. Past coverage the quote card
says trades end at the coverage time. Historical replay exposes no invented bid,
ask, quotes or depth. Depth it did not invent is a different matter: where the
local depth recorder (`backend/l2/`) archived a book for the replayed second,
`sim/history_depth.py` serves it as `depth` with `depth_available` true (#309).
Quotes stay absent and `bid`/`ask` stay null -- a recorded book is not a quote
stream, and practice fills still price from prints alone (ADR 019).

**Rail parity.** The Stock Quote rail keeps the live structure in historical
replay: quote head (last, change, Float/Vol/Gap/High/Low) over **Level 2 |
Time & Sales** side by side. Time & Sales is the live `TimeSalesView` (same
columns, row height, virtualized window, min-size filter) fed from the
snapshot instead of the tape WebSocket; its status badge reads REPLAY and
unreported prints are dimmed rows, not a separate column. Level 2 keeps its
pane and column headers, and draws the recorded book at the playhead when the
snapshot carries one; it never mounts the live depth feed during replay. With no
recorded book the rows stay empty and the pane states *"Level 2 was not recorded
for this moment"* inside the ladder, so an unrecorded minute never reads as a
market with no bids. Its header chip reads "Replay · Recorded L2" or "Replay ·
No L2 recorded" in place of the live halt and shortability chips, which describe
today, not the replayed session (the rail hides
`.ibkr-depth-fallback-badge`, so the notes use their own class). The
lookup is one indexed newest-at-or-before row per replayed second, memoized, and
an unreadable `l2.db` degrades to "not recorded" rather than failing the
replay. The quote head reads the snapshot: `last`, `volume`, session
`open`/`high`/`low` from reached reported prints (or reached candles when
trades are not downloaded) and `prev_close` = the prior trading day's 15:59 ET
minute close (proxy for the official close the live head uses), else that
day's stored daily close (extended hours, `useRTH=False`), else none -- never
an older session. RVOL, halt and shortability are blank in replay. Rows carry
no bid/ask aggressor tint because historical quotes are not downloaded. A seek or selection change clears UI snapshots and rebuilds
deterministically. Pause freezes event time. Capture feeds must not inject into
historical playback. Practice orders trade the loaded window itself (ADR 019);
fills price from its prints alone, because a historical download carries no
bid/ask. Loading new downloaded data is explicit: loading the same window again
keeps the playhead and pause; a different window starts at its open. **Close
replay** clears the selection and window, keeps pause, and keeps the playhead's
Eastern time of day.

Acceptance: IMCC 2026-09-18 04:00–09:30 ET; prove pagination with identical
prints, atomic resume, timezone and range boundaries, no lookahead, rewind,
symbol switches, and sum of reached reported sizes equal candle volume. Compare
IBKR bars per minute: the raw archive keeps every print unaltered, and
differences are reported rather than hidden.

## Bounded replay snapshots and progress (2026-09-20, #321/#324/#303)

ADR 017's canonical engine publishes an immutable selection only after its disk
reads and indexes finish outside the playback lock (ADR 001/003 extraction).
Readers retain that selection for the duration of a response. A selection/clear
revision fences obsolete loads; publishing selection and session clock is atomic.
The maximum is 500,000 prints per selection; SQL stops at limit + one and refuses
larger selections without dropping prints. Narrow the requested window to load
more of a large archive. This is a memory guard, not a retention policy.

One selection owns bounded archive/timeframe and event-second result caches.
Selected-symbol archive candles and prior close (including a miss) stay fixed until explicit
reload; new downloads never mutate a running selection. Rewind keys a different
event second and cannot reuse future values. Reload and clear discard every
cache. Other-symbol fallback series are loaded lazily into a bounded cache and
may be read again after eviction. Snapshot prints carry their stable zero-based download ordinal. A request
for a different symbol returns active=false and no historical quote/tape values;
chart fallback may still read that symbol's completed bars at the session cut.

Job progress is the fraction of requested event time durably covered, never an
inferred fraction of prints. `downloaded_through` is the committed cursor;
`progress_pct`, `age_seconds`, and `stale` are computed for each GET. `started`
is the current worker-run start. `eta_seconds` estimates remaining elapsed time
from this run's cursor advancement only and is null before advancement, after
pause/failure/completion, or while stale. Resume resets its timing baseline.
An empty page with cursor before end fails resumably, preserving rows, count and
cursor. Only nonempty evidence reaching the boundary proves completion.
Schema initialization uses an integer SQLite `user_version` (v1, migrating legacy
v0). Each connection checks the database's version before trusting the bounded
file-identity registry: filesystems may reuse an inode and omit birth time after
replacement. Only a matching identity at v1 skips initialization. A recreated or
legacy v0 database runs the known migration under the initialization lock, even
with a cached identity; unknown versions always refuse with an archive error.
Repeated valid connections set the connection timeout and read the schema version,
but do not repeat schema DDL or journal-mode transitions.
New download admission checks active ownership, validates retry cooldown, creates
the row, and claims it in one SQLite transaction. Simultaneous requests cannot
leave a refused request's queued orphan behind; resume uses the same active-job
invariant. The process lock also covers reservation-to-worker launch.
Capture intent registration uses the same history-to-capture lock order as
historical publication. Clearing history and registering the capture generation
are one short transition; capture file loading and scrub fan-out stay outside it.
