"""Tunables for the offline leaderboard rebuild (ADR 023) -- research only.

Nothing here is imported by backend/. The row vocabulary, the ranking presets and
the store live in ``backend/leaderboard`` and ``backend/constants_leaderboard.py``;
this file holds only what the rebuild itself decides.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

# ── Inputs ──────────────────────────────────────────────────────────────────
# Massive flat files (same env override as research/orb/common.py).
DATA_ROOT = Path(os.environ.get("NOVA_MARKET_DATA_DIR") or r"F:\Nova\data\massive")
MINUTE_SUBDIR = "minute_aggs_v1"
DAY_SUBDIR = "day_aggs_v1"
REFERENCE_SUBDIR = Path("store") / "reference"
RESEARCH_DB = DATA_ROOT / "store" / "orb.duckdb"
# Nova's own enrichment snapshots (float as known that day, 2026-07-28 onward).
# Opened read-only; the main checkout's archive, not a worktree's.
ARCHIVE_DB = Path(os.environ.get("NOVA_ARCHIVE_DB") or r"C:\Users\aalta\github\Nova\backend\.cache\archive.db")

TZ_NAME = "America/New_York"
# One row per ticker per minute; volume is fractional from 2026 on, so DOUBLE.
CSV_COLUMNS = (
    "{'ticker': 'VARCHAR', 'volume': 'DOUBLE', 'open': 'DOUBLE', 'close': 'DOUBLE',"
    " 'high': 'DOUBLE', 'low': 'DOUBLE', 'window_start': 'BIGINT', 'transactions': 'BIGINT'}"
)
DUCKDB_THREADS = 8
DUCKDB_MEMORY_LIMIT = "3GB"

# ── The session grid ────────────────────────────────────────────────────────
SESSION_START_MIN_ET = 4 * 60          # 04:00 ET, the first bar's window
SESSION_MINUTES = 16 * 60              # 04:00-20:00 ET: bar windows j = 0..959
# Board boundaries k = 1..960 -> minute_ts 04:01..20:00 ET; bar j is used at k iff j + 1 <= k.
REGULAR_OPEN_J = 9 * 60 + 30 - SESSION_START_MIN_ET   # the 09:30 bar
PRIOR_CLOSE_HOUR_ET = 16               # news counts from the prior session's 16:00 ET close

# ── Universe ────────────────────────────────────────────────────────────────
# Reference ``type``: common stock and ADR common. A ticker missing from the
# reference, or with no type there, is left out (counted in the build log).
UNIVERSE_TYPES = ("CS", "ADRC")
# Reference MIC -> the desk's exchange vocabulary (backend/exchanges.py _KNOWN_EXCHANGES).
MIC_TO_EXCHANGE = {"XNAS": "NASDAQ", "XNYS": "NYSE", "XASE": "AMEX", "ARCX": "ARCA", "BATS": "BATS"}

# ── Time-of-day RVOL (rvol_basis "time_of_day_20") ──────────────────────────
RVOL_LOOKBACK_SESSIONS = 20
# Fewer prior sessions in which the symbol printed than this -> rvol unknown.
RVOL_MIN_PRIOR_SESSIONS = 10

# ── Output ──────────────────────────────────────────────────────────────────
TOP_N_DEFAULT = 100
WRITE_CHUNK_MINUTES = 60

# --- Unattended five-year rebuild (build_leaderboard.py --all) ---
# A complete rebuilt session covers every minute boundary 04:01-20:00 ET.
EXPECTED_MINUTES = 960
# Sessions per reference / news load: bounds memory over five years.
CHUNK_DAYS_DEFAULT = 20
# --avoid-session: never build 03:45-20:05 ET on a weekday -- the live recorder
# writes the same store 04:00-20:00 and the desk needs the machine.
AVOID_FROM_MIN_ET = 3 * 60 + 45
AVOID_UNTIL_MIN_ET = 20 * 60 + 5
