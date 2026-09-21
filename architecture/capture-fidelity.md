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

L2 uses event timestamps and coalesces intermediate books; stop flushes the
newest pending book even if the feed became quiet. Manifest fidelity describes
offered/coalesced counts, configured maximum Hz, invalid timestamp and regression
counts, and per-stream watermarks. A backward print fails visibly before it can
enter bars. Forward Eastern date changes finalize the old directory and resume
the event's date. Daily bars stay in
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
sim/market_views.py. Captured quote_at preserves recorded bid/ask/prior-close
values; prints without quotes carry null bid/ask/sizes/prior close. No spread,
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
