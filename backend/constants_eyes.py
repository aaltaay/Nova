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
EYES_BACKTEST_MAX_VARIANTS = 48             # templates a sweep may run for one backtest only (ADR 034)
EYES_VARIANT_ID_PREFIX = "var-"             # a variant's id: never a stored template's ("t-...")

# -- The flow study (ADR 034): does the tape flow score say anything about the next minutes?
EYES_FLOW_STUDY_HORIZONS_SEC = (10, 30, 60, 120, 300)
EYES_FLOW_STUDY_STEP_SEC = 1.0              # one reading a second of every recorded stretch
EYES_FLOW_STUDY_REFRACTORY_SEC = 30.0       # an onset is the first burst / flush after this long without one
EYES_FLOW_STUDY_BUCKET = 0.25               # score buckets this wide
EYES_FLOW_STUDY_CONTEXT_SEC = 60            # an onset's context: where the mid went in the minute before it
EYES_FLOW_STUDY_CONTEXT_BP = 50.0           # up or down at least this much is a rise / a fall, else flat

# -- The live journal read back at a past moment (eyes/playback.py): the Sim desk's
#    Setups board and every setup card, as Nova's eyes had them then.
EYES_JOURNAL_BEAT_SEC = 60.0                # the live engine writes a "beat" line this often, so a playback knows a gap
EYES_JOURNAL_PRICE_EVERY_SEC = 5.0          # an armed / near symbol's last price, at most this often per symbol
EYES_PLAYBACK_GAP_SEC = 180.0               # no line for this long on a day with beats: Nova's eyes were not running
EYES_PLAYBACK_REBUILD_MIN_SEC = 0.5         # a backward scrub refolds the day at most this often
EYES_PLAYBACK_ALERT_STEP_SEC = 120.0        # a proposal pops up only when the playhead played across it, never on a jump
