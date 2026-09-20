"""Capture mode — IBKR session record, not for placing."""
from __future__ import annotations

CAPTURE_L2_MAX_HZ = 8.0
# Outside-repo capture root (Windows trading bench). Override with NOVA_SIM_CAPTURE_DIR.
DEFAULT_SIM_CAPTURE_ROOT_WIN = r"F:\Nova\sim_capture"

# --- Durability / failure handling (D-067, D-068) -----------------------------
# One jsonl stream per name is opened for the life of a recording session.
CAPTURE_STREAM_NAMES = (
    "prints",
    "quotes",
    "l2",
    "bars_10s",
    "bars_1m",
    "bars_5m",
    "bars_1d",
)
CAPTURE_MANIFEST_NAME = "manifest.json"
# Marker naming the in-flight session so a restart can finalize an orphan.
CAPTURE_ACTIVE_STATE_NAME = ".active_session.json"
# fsync cadence while recording; stop always fsyncs regardless.
CAPTURE_FSYNC_INTERVAL_SEC = 5.0
# Consecutive failed writes before the recorder gives up and reports failed.
CAPTURE_MAX_WRITE_FAILURES = 3
CAPTURE_SCHEMA = "sim_capture_v1"
CAPTURE_STATUS_RECORDING = "recording"
CAPTURE_STATUS_STOPPED = "stopped_partial_ok"
CAPTURE_STATUS_INTERRUPTED = "interrupted"
CAPTURE_STATUS_FAILED = "failed"
# Bound pending complete tick/bar batches, including the currently writing batch.
CAPTURE_PENDING_BATCHES = 256

# Capture owns v1 manifests/rows; session rollover resets writer state.
CAPTURE_SCHEMA_VERSION = 1
CAPTURE_BAR_STEPS = (("10s", 10), ("1m", 60), ("5m", 300))
CAPTURE_L2_LOAD_LIMIT = 30_000
CAPTURE_CHART_DEFAULT_LIMIT = 300
CAPTURE_CHART_MAX_LIMIT = 2000
CAPTURE_FEED_EMIT_LIMIT = 20
