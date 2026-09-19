# Historical replay (ADR 012 archive extension, D-052)

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
resumable progress. Only a successful end-of-range response marks coverage
complete. Completion describes the IBKR response range, not a claim of
consolidated market completeness. Downloaded candles are kept in the archive
with their job identity and are also upserted into the shared bars store.
Coarser derived bars exclude incomplete window-edge buckets.

One worker and a durable send timestamp serialize downloads and enforce a
conservative 11-second request interval (16 seconds before retrying a failed
request). Requests have timeouts and a bounded page count. A separate read-only
Gateway connection (its own client id and event loop, no account/order fetches)
tries the live port first and the paper port when live is dark (AGENTS.md §5).
The IBKR adapter only fetches; the SIM downloader owns persistence. Tunables
live in `backend/constants_sim.py`. This budget does not account for other
applications; IBKR pacing rejections are surfaced as resumable failures rather
than retried in a loop.

Playback loads an immutable in-memory snapshot of reached download coverage
(very large windows load more slowly). Trade-derived bars take precedence only
within completed download coverage; outside it archived OHLCV remains the
fallback. Partial bars use reached trades; all same-second prints arrive
together, in returned order. Candles, last price and volume use only prints
IBKR reports as tape-eligible (`unreported` false); Time & Sales lists every
reached print and marks unreported ones (IMCC: odd-lot/Form T `TI`/`FTI`
prints would otherwise invent highs such as 2.00 against a 1.88 bar). With that
rule replay OHLCV equals IBKR's own 1-minute bars. Past coverage the quote card
says trades end at the coverage time. Historical replay exposes no invented bid, ask, quotes or
depth.

**Rail parity.** The Stock Quote rail keeps the live structure in historical
replay: quote head (last, change, Float/Vol/Gap/High/Low) over **Level 2 |
Time & Sales** side by side. Time & Sales is the live `TimeSalesView` (same
columns, row height, virtualized window, min-size filter) fed from the
snapshot instead of the tape WebSocket; its status badge reads REPLAY and
unreported prints are dimmed rows, not a separate column. Level 2 keeps its
pane and column headers with empty rows; it never mounts the live depth feed
during replay. Its header shows a "Replay · No L2 recorded" chip in place of
the live halt and shortability chips, which describe today, not the replayed
session (the rail hides `.ibkr-depth-fallback-badge`, so the note lives in the
header). The quote head reads the snapshot: `last`, `volume`, session
`open`/`high`/`low` from reached reported prints (or reached candles when
trades are not downloaded) and `prev_close` = the prior trading day's 15:59 ET
minute close (proxy for the official close the live head uses), else that
day's stored daily close (extended hours, `useRTH=False`), else none -- never
an older session. RVOL, halt and shortability are blank in replay. Rows carry
no bid/ask aggressor tint because historical quotes are not downloaded. A seek or selection change clears UI snapshots and rebuilds
deterministically. Pause freezes event time. Synthetic and capture feeds must
not inject into historical playback, so SIM1 practice fills also wait until
historical replay is closed (SIM orders accept only SIM1). Loading new
downloaded data is explicit: loading the same window again keeps the playhead
and pause; a different window starts at its open. **Return to SIM1** clears the
selection and window, keeps pause, and keeps the playhead's Eastern time of day
on the SIM1 session date.

Acceptance: IMCC 2026-09-18 04:00–09:30 ET; prove pagination with identical
prints, atomic resume, timezone and range boundaries, no lookahead, rewind,
symbol switches, and sum of reached reported sizes equal candle volume. Compare
IBKR bars per minute: the raw archive keeps every print unaltered, and
differences are reported rather than hidden.
