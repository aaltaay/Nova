"""Performance recorder (ADR 026). Domain constants.

The recorder measures and never acts: nothing here throttles, sheds or
restarts anything. Thresholds below are first guesses until the burst rig
(ADR 026 phase 2) measures real limits.
"""
from __future__ import annotations

PERF_SCHEMA_VERSION = 1

# ``NOVA_PERF=0`` turns the recorder off entirely.
PERF_ENV_SWITCH = "NOVA_PERF"

# One sample per second, kept in memory this long.
PERF_SAMPLE_INTERVAL_SEC = 1.0
PERF_RING_SEC = 1800
# The day file takes one aggregate per this many samples.
PERF_PERSIST_EVERY_SEC = 5

# Stall watcher: a no-op callback posted on each loop this often; a callback
# that waits longer than PERF_STALL_MS means the loop is stalled, and the
# watcher samples that thread's stack every PERF_STALL_SAMPLE_SEC until it runs.
PERF_WATCH_PING_SEC = 0.05
PERF_STALL_MS = 200.0
PERF_STALL_SAMPLE_SEC = 0.01
PERF_STALL_MAX_SAMPLES = 3000
PERF_STALL_MAX_FRAMES = 16
PERF_STALL_TOP_STACKS = 12
# Samples kept either side of a stall in its report.
PERF_STALL_CONTEXT_SEC = 30
PERF_STALL_RECENT = 50
PERF_STALL_FILES_PER_HOUR = 60

# Storage under <cache_dir>/perf/ (owner perf/store.py).
PERF_DIR_NAME = "perf"
PERF_STALLS_DIR_NAME = "stalls"
PERF_RETENTION_DAYS = 7
PERF_DAY_FILE_MAX_MB = 50
PERF_WRITE_QUEUE_MAX = 2000

# Window reports (POST /api/perf/client). Mirror: frontend constantGroups/perf.ts.
PERF_CLIENT_MAX_BODY_BYTES = 16384
PERF_CLIENT_MAX_KEYS = 60
PERF_CLIENT_MAX_PROCESSES = 40
PERF_CLIENT_TOP_SCRIPTS = 3
PERF_CLIENT_STALE_SEC = 20.0
PERF_SLOW_FRAME_MS = 33.0
PERF_CLIENT_ROLES = ("main", "popout", "browser", "electron")

# /api/perf/live default window.
PERF_LIVE_DEFAULT_SEC = 300

# Diagnostics thresholds (percent of one core / share of frames).
PERF_DIAG_WINDOW_SEC = 60
PERF_DIAG_CPU_WARN_PCT = 60.0
PERF_DIAG_CPU_FAIL_PCT = 85.0
PERF_DIAG_STALL_RECENT_SEC = 1800
PERF_DIAG_DROP_RECENT_SEC = 600
PERF_DIAG_SLOW_FRAMES_WARN = 0.05
PERF_DIAG_SLOW_FRAMES_FAIL = 0.20
PERF_DIAG_TOP_HANDLERS = 5
PERF_DIAG_RANK_ALL = 1_000     # rank every timed operation, then split work from waits

# Heap census (#619): what every full collection walks. Taking one walks the heap too
# (about as long as one full collection), so it runs rarely.
PERF_HEAP_TOP = 30                       # types and holders listed
PERF_HEAP_FIRST_AFTER_SEC = 600          # the first census, this long after the recorder starts
PERF_HEAP_EVERY_SEC = 3600               # then once an hour
PERF_HEAP_MIN_GAP_SEC = 60               # GET /api/perf/heap answers the last census while it is this young
PERF_HEAP_QUIET_ET = ("09:25", "09:45")  # no scheduled census in the opening minutes (weekdays)
PERF_HEAP_SCAN_CAP = 200_000             # values read per holder when counting one level down

# GC policy (#619, ``gc_policy``): freeze the long-lived heap once, this long after start, so full
# collections stop walking the code and module state that live as long as the process.
GC_FREEZE_AFTER_SEC = 300
GC_FREEZE_ENV = "NOVA_GC_FREEZE"
