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
# The Electron report's logical CPU count (its process cpu_pct is % of one core).
PERF_CLIENT_MAX_LOGICAL_CPUS = 1024
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

# Freezes (ADR 045, ``perf/freeze_watch.py``): a C-level watchdog (``faulthandler``), re-armed this
# often by a thread that needs the GIL, dumps every thread's stack when it was not re-armed for
# PERF_FREEZE_DUMP_SEC -- the whole process stopped. 2026-10-05 08:31: an 8.8 s freeze left no stack.
PERF_FREEZE_DUMP_SEC = 2.0
PERF_FREEZE_REARM_SEC = 0.5
PERF_FREEZES_DIR_NAME = "freezes"
PERF_FREEZE_LOG_NAME = "freezes.jsonl"
PERF_FREEZE_SCHEMA_VERSION = 1
PERF_DIAG_FREEZE_RECENT_SEC = 1800  # a freeze this recent makes the checklist row fail

# L1 timestamp provenance (#667): same perf opt-out, independent day cap so
# evidence cannot crowd the ordinary samples out of their file.
PERF_L1_TIMESTAMP_SCHEMA_VERSION = 1
PERF_L1_TIMESTAMP_DIR = "l1_timestamps"
PERF_L1_TIMESTAMP_DAY_MAX_MB = 100
PERF_L1_TIMESTAMP_FLUSH_SEC = 1.0
PERF_L1_TIMESTAMP_WAIT_SEC = 2.0
PERF_L1_TIMESTAMP_MATCH_SEC = 2.0
PERF_L1_TIMESTAMP_RECEIPT_MAX_AGE_SEC = 2.0
PERF_L1_TIMESTAMP_PRICE_QUEUE = 4096
PERF_L1_TIMESTAMP_TAPE_QUEUE = 8192
PERF_L1_TIMESTAMP_PRICES_PER_SEC = 500
PERF_L1_TIMESTAMP_PRINTS_PER_SEC = 2000
PERF_L1_TIMESTAMP_SYMBOLS = 256
PERF_L1_TIMESTAMP_PRINTS_PER_SYMBOL = 64
PERF_L1_TIMESTAMP_CANDIDATES = 4

# The memory watch (``perf/memory_watch.py``; operator report 2026-10-11, "nova keeps driving the ram higher"):
# once a minute, off the loops, the PC's memory and every process's private bytes -- Nova's share by pid, the
# biggest other programs by name -- written to the day file (``kind: "memory"``) and the ``pc_memory`` row.
PERF_MEMORY_SCHEMA_VERSION = 1
PERF_MEMORY_EVERY_SEC = 60
PERF_MEMORY_FIRST_AFTER_SEC = 20
PERF_MEMORY_TOP = 5                     # the biggest other programs named
PERF_MEMORY_PRESSURE_PCT = 90           # the PC's RAM in use, or its commit charge, at or above this: warn
PERF_MEMORY_CRITICAL_PCT = 97           # RAM or commit this full: paging stalls the PC, allocations start failing
PERF_MEMORY_REARM_PCT = 85              # an episode ends under this; the API log warns once per episode
PERF_MEMORY_STALE_SEC = 300             # a reading older than this is not shown as the PC now
PERF_MEMORY_CLIENT_FRESH_SEC = 30       # a desk window's process list counts while it is this young
# Nova's leak lines, above the most each part held in the week to 2026-10-11 (the API 3,433 MB private, the
# desk's processes 2,763 MB together): past one, that part holds memory it should not, and the row fails.
PERF_MEMORY_API_LEAK_MB = 5000
PERF_MEMORY_DESK_LEAK_MB = 4500
# The low-memory notice (``perf/memory_notice.py``; operator ask 2026-10-15): the strip under the desk's header
# while the PC is past PERF_MEMORY_PRESSURE_PCT in the trading session, naming the process holding the most.
PERF_MEMORY_NOTICE_SCHEMA_VERSION = 1
PERF_MEMORY_NOTICE_HOLD_SEC = 300       # under the line, the episode stays open this long while the same process leads
PERF_MEMORY_GROUP_OUTWEIGHS = 2         # one program's processes together this many times the biggest: named too

# The port watch (``perf/port_watch.py``; operator report 2026-10-14: the PC ran out of network ports and the
# backend restarted 19 times): once a minute, off the loops, the TCP connections in Windows' dynamic port range
# and those still held under process ids that no longer exist -- written to the day file (``kind: "ports"``)
# and the ``pc_ports`` row. On 2026-10-14 the leak stood at ~1,600 a day after the boot and 15,300 four days on.
PERF_PORTS_SCHEMA_VERSION = 1
PERF_PORTS_EVERY_SEC = 60
PERF_PORTS_FIRST_AFTER_SEC = 20
PERF_PORTS_TOP = 3                      # the living programs holding the most connections, named in the fix
PERF_PORTS_PRESSURE_PCT = 70            # dynamic ports in use at or above this: warn
PERF_PORTS_CRITICAL_PCT = 90            # this close to none left: new connections start failing, in any program
PERF_PORTS_REARM_PCT = 60               # an episode ends under this; the API log warns once per episode
PERF_PORTS_CLOSED_WARN = 500            # connections held under exited process ids: a leak that only a restart frees
PERF_PORTS_STALE_SEC = 300              # a reading older than this is not shown as the PC now
