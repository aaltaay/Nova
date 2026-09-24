# Capture integrity and compatibility (#337, #320)

ADR 017 keeps historical replay canonical; these changes protect existing
capture files during its compatibility window. ADR 001 separates capture path
resolution, schema validation and timestamp/coalescing state from the writer.
Capture owns integer schema_version 1 on manifests and new JSONL rows. Session
rotation resets write state; changed schema versions require explicit migration.
Known unversioned sim_capture_v1 files migrate in memory after validation, while
unknown versions and malformed manifests refuse selection or append. Existing
files are not rewritten. Resume streams existing rows on the capture worker to
validate versions and recover each stream's timestamp high-water mark.

L2 uses event timestamps and keeps every book IBKR sends, up to
`CAPTURE_L2_MAX_HZ` (50, a flood bound -- it was 8 until ADR 031, which held back
most of a busy name's books). Books reach the writer in batches, like prints, so a
fast book cannot fill the worker's backlog; a book over the bound is held, never
dropped, and stop flushes the newest pending book even if the feed became quiet.
Manifest fidelity describes offered/coalesced counts -- `l2_coalesced` counts every
book held back, at the IBKR bridge or by event time -- configured maximum Hz,
invalid timestamp and regression counts, and per-stream watermarks. A backward print fails visibly before it can
enter bars. Forward Eastern date changes finalize the old directory and resume
the event's date; the recording continues across the swap, and recorder state is
read under its lock so a status poll can never observe the swap half-done and
drop Record mode. A day segment closed before its first print is marked empty.

Session Record owns its IBKR lines (`capture/feed_hold.py`, #315). Starting a
recording opens -- or joins -- the symbol's AllLast tape and a live depth line
and holds a viewer reference on each until it stops, so no panel opening,
closing or switching venue can pull its feed; stop releases through the same
linger and grace paths the panels use. A refused tape line refuses the
recording; a refused depth line records prints only, with a status warning.
Record runs on any desk venue: on a Sim desk live ticks and books still reach
the recorder and the stored book the print side is classified against, but are
not broadcast to the practice desk's panels or sensors, and a switch to Sim no
longer stops a recording (that stop guarded against SIM1 ticks, removed by
ADR 019). Daily bars stay in
memory until rollover/final flush, anchored to the shared Sim session opening
hour on the actual event calendar; pre-open events use the preceding anchor so
DST or early prints cannot produce a future timestamp.

Compatibility loading validates finite prices, timestamps, sizes, volumes and
L2 level shapes. It reports malformed_rows, invalid_timestamp_rows, invalid_rows,
legacy_schema, l2_total, l2_loaded and l2_decimated in replay_load. L2 is read on
the selection worker and capped at 30,000 snapshots, preserving first and final
states. Playback performs no L2 file reads. Selection builds one complete data/key
snapshot off-lock and publishes it with a generation fence. A newer capture,
clear or historical selection invalidates pending work; loading suppresses feed
emission. Capture locks never call historical state functions, preventing reverse
lock ordering. Each feed step pins one snapshot for prints, symbol and book. Unused daily bar files are not loaded.
Decimation remains an explicit fidelity limitation, visible in the Sim header.

## Storage compatibility

NOVA_SIM_CAPTURE_DIR is authoritative. Without it, the existing Windows
F:/Nova/sim_capture location stays preferred when that drive exists. Otherwise
Windows uses %LOCALAPPDATA%/Nova/sim_capture; Unix uses
$XDG_DATA_HOME/Nova/sim_capture or ~/.local/share/Nova/sim_capture.

Recordings formerly created by the checkout-cache fallback stay at their old
location. To keep accessing them, set NOVA_SIM_CAPTURE_DIR in the operator .env
to the absolute path of the old backend/.cache/sim_capture directory (or its
previous NOVA_CACHE_DIR/sim_capture override), then restart Nova. If historical
jobs were also under that root's historical subdirectory, leave
NOVA_SIM_HISTORY_DIR unset to follow the capture root plus /historical, or explicitly set it to the existing directory that contains
replay.sqlite3. Inspect current configured paths before selecting either value.
No migration, move, deletion or retention policy is performed by this change.

Retention, delete endpoints and storage-management controls remain an operator
decision under #320. Removing duplicate daily rows and the checkout fallback
reduces unnecessary growth but does not bound total retained recordings.


## Unknown market facts stay unknown

ADR 001 extracts market read views from the synthetic tape owner into
sim/market_views.py. Captured quote_at preserves recorded bid/ask values;
prints without quotes carry null bid/ask/sizes. Every projection carries the
loaded capture's one previous close (`sim/prior_close.py`, #542): IBKR's tick 9
recorded on its quote rows, else the leaderboard's, else a download's
regular-hours close, else null -- never a 15:59 minute or extended-hours daily
close. No spread,
100-share size, synthetic order book or synthetic daily OHLC is fabricated.
Ticker snapshots expose actual reached prints, latest_quote only when a recorded
bid or ask exists, and null minute_bar/daily_bar/prev_daily_bar when unavailable.
Before the first event, loading or failed capture selections return no quote,
an empty book and an empty ticker snapshot. An unloaded selection keeps its
existing generated behavior. Requests for another symbol do not reuse the
selected capture's quote.


Clock publication uses a notification-free mutation path under the capture lock.
Scrub tape/depth refresh runs only after release and checks the capture generation
before reseeding. This includes close-replay time preservation. Read views pin
one capture snapshot through quote and ticker projection so a source switch cannot
combine the prior symbol's quote with the new symbol's trade. A regression holds
capture alignment and historical publication concurrently to exercise the exact
lock order rather than relying on scheduling luck.
`latest_quote` uses canonical `bid_price`, `ask_price`, `bid_size`, and `ask_size` fields from recorded data, retaining `bid`/`ask` aliases for compatibility. Unknown values remain null.

## Persistence: resume, then say so (operator decision, 2026-09-21)

A Session Record is owned by the backend process -- up to three symbols at
once (`CAPTURE_MAX_CONCURRENT`: IBKR allows three depth lines, Record holds one
per symbol), each by the operator's choice, each its own recorder session with
its own IBKR lines. Nothing on the page stops one: closing the panel, the tab
or the window, reloading, switching desks. One symbol dying never touches the
others; a fourth symbol is refused before any IBKR line is touched. The frontend keeps no recording state
of its own -- `sessionRecordStore.ts` reads only fresh `/api/ibkr/status`
snapshots -- so a reload simply shows what the backend is still doing.

What *can* stop it, and the policy for each, lives in `capture/keepalive.py`:

| Event | What happens | What the operator sees |
|---|---|---|
| Nova restart | Startup finalizes the orphan (`session_state.finalize_orphaned_session`, segment `reason: "restart"`). If it is today's session and its newest stream file is younger than `CAPTURE_RESUME_RESTART_WINDOW_SEC`, the keepalive resumes it into a new segment once IBKR is ready. | Toast "GRML recording was cut by a Nova restart", then quiet once it resumed. |
| Recorder stops itself (disk, timestamp, writer backlog) | The next keepalive tick sees no recording and no operator stop: `capture_stopped` is set and a resume is scheduled with `CAPTURE_RESUME_BACKOFF_SEC`, at most `CAPTURE_RESUME_MAX_ATTEMPTS` tries; IBKR being down costs no attempt. | Toast with the reason and "Resuming on its own in 5s (attempt 1 of 5)"; "Gave up" plus a Resume now button after the last. |
| IBKR line dropped with the Gateway | The recorder never stopped. When the client is ready again the keepalive releases and re-acquires the tape and depth lines (`capture_session.reacquired`). | Nothing loud: a quiet stretch inside the segment. |
| Operator Stop / Record on another symbol | `routes.py` tells the keepalive first, so the stop is never read as a death and any pending resume is cancelled. | Nothing. |

Resume never crosses the session day and never changes symbol. Every manifest
segment carries `reason: operator | rotation | failure | restart`, so a gap can
say what made it; `/api/capture/sessions` rows summarise `segments`,
`missing_sec` and `last_reason`, and a capture loaded for replay exposes its
segments in `replay_load` for the scrubber band.

### What the operator sees (frontend/src/capture)

Steady state is quiet; a change of state is loud:

- **REC chips** in the header status cluster, one per recording symbol, none
  otherwise: red dot, symbol, elapsed time of this segment; counts, segment
  and last-write age in the tooltip; click opens that tab.
- **Hairline**: 2px red along the top window edge while recording.
- **Window title** leads with `REC GRML` (shared `electron/appTitle.mjs`), so
  the taskbar says so with Nova behind other windows.
- **Stop toast** (`RecordingSignals.tsx`): only for a stop the operator did not
  ask for; stays until resumed or dismissed; one per stop, per symbol.
- **Hold to stop** (`HoldToStopButton.tsx`): Stop in the tab menu takes a
  `CAPTURE_STOP_HOLD_MS` hold; a click or an early release keeps recording.
- **Capture band** under the Sim scrubber: recorded stretches solid, the gaps
  between them striped with why in the tooltip (`simCoverage.captureBandSegments`).
  A quiet stretch inside one recording is not a gap.
