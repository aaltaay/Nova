"""The eyes' journal and the replayed eyes (ADR 029).

Owner: backend/eyes/. Re-exported from the constants barrel.
"""
from __future__ import annotations

EYES_SCHEMA_VERSION = 1                     # every journal line and backtest file
EYES_DIR_ENV = "NOVA_EYES_DIR"              # else F:\Nova\eyes when F: is mounted, else <cache>/eyes
EYES_DEFAULT_ROOT_WIN = "F:/Nova/eyes"
EYES_JOURNAL_DIRNAME = "journal"            # <eyes dir>/journal/YYYY-MM-DD.jsonl (Eastern date, wall clock)
EYES_BACKTESTS_DIRNAME = "backtests"        # <eyes dir>/backtests/<run_id>/
EYES_JOURNAL_ENV = "NOVA_EYES_JOURNAL"      # "0" turns the journal off
EYES_JOURNAL_QUEUE_MAX = 20_000             # lines waiting for the writer; past it a line is dropped and counted
EYES_JOURNAL_FLUSH_SEC = 1.0                # the writer drains the queue at least this often

# -- Replayed eyes (a Session Record run through the lanes).
EYES_REPLAY_SOURCE_SIM = "sim"              # following the Sim playhead
EYES_REPLAY_SOURCE_BACKTEST = "backtest"    # a batch run over recordings
EYES_REPLAY_PRICE_STEP_SEC = 1.0            # at most one price a second reaches the detectors (the last print in it)
EYES_REPLAY_BOOK_SAMPLE_SEC = 0.5           # the recorded book is sampled like the live tape feed samples it
EYES_SIM_REBUILD_MIN_SEC = 2.0              # a backward scrub rebuilds at most this often
EYES_BACKTEST_MAX_SESSIONS = 400            # Session Records one run may cover
EYES_BACKTEST_RUNS_LISTED = 50              # GET /api/eyes/backtests lists this many, newest first
