"""Constants for the day movers index (ADR 050): one row per stock per session that moved."""
from __future__ import annotations

# ── Store ───────────────────────────────────────────────────────────────────
# Beside the Massive files it is built from (ADR 046's rule: what comes from Massive stays on that drive).
DAY_MOVERS_SUBDIR = "movers"
DAY_MOVERS_DB_FILENAME = "day_movers.sqlite3"
DAY_MOVERS_SCHEMA_VERSION = 1
DAY_MOVERS_SQLITE_TIMEOUT_SEC = 30.0
# The builder that wrote a session; a newer builder rebuilds the sessions an older one wrote.
DAY_MOVERS_BUILDER_VERSION = 1

# ── What a row means ────────────────────────────────────────────────────────
# The minute grid, ET minutes after midnight: premarket 04:00-09:30, regular 09:30-16:00, after hours 16:00-20:00.
DAY_MOVERS_SESSION_START_MIN_ET = 4 * 60
DAY_MOVERS_REGULAR_OPEN_MIN_ET = 9 * 60 + 30
DAY_MOVERS_REGULAR_CLOSE_MIN_ET = 16 * 60
DAY_MOVERS_SESSION_END_MIN_ET = 20 * 60
# First minute whose high reached +N% / whose low reached -N% over the prior close (column name -> multiple).
DAY_MOVERS_UP_MARKS = {"up10_ts": 1.10, "up20_ts": 1.20, "up50_ts": 1.50, "up100_ts": 2.00, "up300_ts": 4.00}
DAY_MOVERS_DOWN_MARKS = {"down10_ts": 0.90, "down20_ts": 0.80, "down50_ts": 0.50}
# An overnight open this far from the prior close with no split listed is a split suspect (#772's thresholds).
DAY_MOVERS_SPLIT_SUSPECT_UP = 1.8
DAY_MOVERS_SPLIT_SUSPECT_DOWN = 0.7
# A suspect that traded no more shares than the session before is a likely split: a reverse split shrinks the
# share count, while the real overnight jumps in #772 traded 10-1,000x more. One that traded this many times the
# session before is a real jump (no label); between the two it stays a suspect.
DAY_MOVERS_LIKELY_SPLIT_MAX_VOLUME_RATIO = 1.0
DAY_MOVERS_REAL_JUMP_MIN_VOLUME_RATIO = 3.0

# ── Which rows are kept (a stock that moved) ────────────────────────────────
DAY_MOVERS_KEEP_HIGH_PCT = 0.10       # the day's high +10% over the prior close
DAY_MOVERS_KEEP_LOW_PCT = -0.10       # or its low -10%
DAY_MOVERS_KEEP_CLOSE_ABS = 0.05      # or the close 5% either way
DAY_MOVERS_KEEP_GAP_ABS = 0.05        # or the gap 5% either way
DAY_MOVERS_KEEP_NO_PRIOR_RANGE = 0.20  # no prior close (a new listing): the day's high 20% over its low

# ── Float (operator: proven, else unknown) ──────────────────────────────────
# SEC shares outstanding count for a session when filed by then and reported as of a day no more than this
# before it: about one quarter and its filing lag. Shares issued after the report (an offering, warrants) are
# not in it, so an older count says less; the answer always carries the count's own date.
DAY_MOVERS_SEC_SHARES_MAX_AGE_DAYS = 120
