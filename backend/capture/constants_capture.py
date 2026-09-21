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
# Prints are the one stream that outruns the writer, so they are batched before
# they reach it: the bound above counts BATCHES, and one job per print turned a
# fast tape into hundreds of jobs a second (GRML, 2026-09-21: 2439 prints in 52s,
# then "backlog full" and a failed session). A batch is submitted when it fills
# or when the interval has passed, so a lone print on a quiet tape still goes
# straight through and a burst costs a handful of jobs instead of hundreds.
CAPTURE_PRINT_BATCH_MAX = 200
CAPTURE_PRINT_BATCH_SEC = 0.2

# Capture owns v1 manifests/rows; session rollover resets writer state.
CAPTURE_SCHEMA_VERSION = 1
CAPTURE_BAR_STEPS = (("10s", 10), ("1m", 60), ("5m", 300))
CAPTURE_L2_LOAD_LIMIT = 30_000
CAPTURE_CHART_DEFAULT_LIMIT = 300
CAPTURE_CHART_MAX_LIMIT = 2000
CAPTURE_FEED_EMIT_LIMIT = 20

# --- Persistence: resume, then say so (operator decision, 2026-09-21) --------
# The market only happens once. A recording knocked down by a restart, a recorder
# failure or a lost IBKR line gets back up on its own into a new segment; the
# operator is told, never asked. Bounded so a dead disk cannot loop forever.
CAPTURE_KEEPALIVE_INTERVAL_SEC = 5.0
CAPTURE_RESUME_BACKOFF_SEC = (2.0, 5.0, 10.0, 30.0, 60.0)
CAPTURE_RESUME_MAX_ATTEMPTS = len(CAPTURE_RESUME_BACKOFF_SEC)
# A restart resumes only a recording from today that died recently -- not one the
# operator forgot about three hours ago.
CAPTURE_RESUME_RESTART_WINDOW_SEC = 15 * 60
# Why a segment ended (manifest segments[].reason).
CAPTURE_STOP_OPERATOR = "operator"
CAPTURE_STOP_ROTATION = "rotation"
CAPTURE_STOP_FAILURE = "failure"
CAPTURE_STOP_RESTART = "restart"
