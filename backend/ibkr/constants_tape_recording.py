"""Bounded recording defaults, independent of live viewer queue capacity."""

# Prints the L2 archive writer holds before it sheds. Sized to ride out a
# SQLite write lock (a connection waits up to 30 s) on a busy premarket name:
# at 256 one stall on 2026-09-24 overflowed it, and the latch that followed
# kept every Paper resting order blind for the rest of the morning.
TAPE_RECORD_PENDING = 8192
# Prints the writer takes off the queue per transaction.
TAPE_RECORD_BATCH_MAX = 512
TAPE_RECORD_STALE_SEC = 60.0
TAPE_RECORD_SHUTDOWN_SEC = 5.0
TAPE_RECORD_POLL_SEC = 0.25
# A loss (prints shed or a failed write) keeps the writer's `error` set this
# long after it ended, so a glance at health catches it; `losses` keeps it.
TAPE_RECORD_LOSS_RECENT_SEC = 300.0
# Loss episodes kept per process, newest last.
TAPE_RECORD_LOSS_KEEP = 20
# Symbols named per loss episode.
TAPE_RECORD_LOSS_SYMBOLS = 8
