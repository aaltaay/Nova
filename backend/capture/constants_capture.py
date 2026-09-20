"""Capture mode — IBKR session record, not for placing."""
from __future__ import annotations

CAPTURE_MODE_LABEL = "capture"
CAPTURE_SPEND_STATUS = "capture_armed"
CAPTURE_BANNER = (
    "CAPTURE MODE -- recording IBKR tape/L2/quotes/bars for Sim replay. "
    "Not for placing. Keep Trader/scanner light."
)
CAPTURE_NO_PLACE_REASON = "CAPTURE mode cannot place orders"
CAPTURE_NO_PLACE_CODE = "CAPTURE_NO_PLACE"
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
