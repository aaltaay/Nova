"""Paths and tunables for the catalyst backfill (research only; nothing in backend/ imports this).

The store lives on the operator's F: drive beside -- never inside -- the Massive flat files and
the leaderboard. ``NOVA_CATALYST_DIR`` overrides the root.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:  # the classifier is the live desk's own module (one classifier)
    sys.path.insert(0, str(BACKEND))

ROOT = Path(os.environ.get("NOVA_CATALYST_DIR") or r"F:\Nova\catalysts")
DB_PATH = ROOT / "catalysts.sqlite3"
EDGAR_DIR = ROOT / "edgar"
LABELS_DIR = ROOT / "labels"
RESULTS_DIR = ROOT / "results"

MASSIVE_ROOT = Path(os.environ.get("NOVA_MARKET_DATA_DIR") or r"F:\Nova\data\massive")
RESEARCH_DB = MASSIVE_ROOT / "store" / "orb.duckdb"
REFERENCE_DIR = MASSIVE_ROOT / "store" / "reference"
LEADERBOARD_DB = Path(os.environ.get("NOVA_LEADERBOARD_DIR") or r"F:\Nova\leaderboard") / "leaderboard.sqlite3"

ET = ZoneInfo("America/New_York")
WINDOW_OPEN_ET = dtime(16, 0)     # a catalyst counts from the prior session's close ...
RESEARCH_CUTOFF_ET = dtime(9, 30)  # ... to the open for the pillar universe (known by 09:30, pre-registered)
WINDOW_END_ET = dtime(20, 0)       # items are stored to the session's end so a later cutoff can be asked

# Leaderboard movers: the whole-market board's top 10 inside the desk's tradeable band.
LB_TOP_RANK = 10
LB_MIN_PRICE, LB_MAX_PRICE = 1.0, 20.0
LB_MIN_VOLUME = 100_000

SOURCES = ("edgar", "alpaca", "finnhub", "massive")
FINNHUB_HISTORY_DAYS = 365         # the free tier's reach; older windows are recorded out_of_range
FINNHUB_CALLS_PER_MIN = 55         # free tier: 60 / min
ALPACA_CALLS_PER_MIN = 150         # free tier: 200 / min
SEC_CALLS_PER_SEC = 8              # SEC fair access: 10 / s
SEC_USER_AGENT_DEFAULT = "NovaResearch research@example.com"  # set SEC_USER_AGENT in .env to your contact


def et_ts(d: date, t: dtime) -> float:
    return datetime.combine(d, t, ET).timestamp()


def sec_user_agent() -> str:
    return os.environ.get("SEC_USER_AGENT") or SEC_USER_AGENT_DEFAULT


def load_env() -> None:
    """The desk .env (NOVA_ENV_PATH, else the main checkout's), without overriding the process env."""
    for env in [Path(p) for p in [os.environ.get("NOVA_ENV_PATH")] if p] + [REPO / ".env", Path(r"C:\Users\aalta\github\Nova\.env")]:
        if env.is_file():
            for line in env.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip().lstrip("\ufeff"), value.strip().strip('"').strip("'"))
            return
