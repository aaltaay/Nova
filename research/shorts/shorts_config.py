"""The five-year test's fixed numbers and paths (ADR 049 section 12 and its step 4 section).

Every number here is pre-registered in ADR 049 ("The five-year test"); a change is a new harness version and
every result written before it reads as a different test. Paths follow research/orb/common.py: the store is
``<NOVA_MARKET_DATA_DIR>/store/orb.duckdb`` beside the Massive files, and the result files are the backend's
own folder (``setup_scanner.short_tests.folder``), so the card reads exactly what the harness wrote.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
ORB_DIR = REPO_ROOT / "research" / "orb"

for folder in (BACKEND_DIR, ORB_DIR):          # the scanner's own detectors and scoring; the ORB store helpers
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

HARNESS_VERSION = 1

# -- The store (research/orb/common.py's DuckDB file). --------------------------------------------------
SELECTION_TABLE = "shorts_selection"
MINUTES_TABLE = "minutes_shorts"
MINUTES_START = "04:00"                       # the extraction keeps 04:00-16:00

# -- The universe (ADR 049 step 4: "The universe"), from the day movers index (ADR 050). --------------------
YEARS = 5                                     # the newest five years of built sessions
FOLLOW_UP_PCT = 0.10                          # followed from the first minute the high reached +10% (up10_ts)
PRICE_MIN, PRICE_MAX = 1.0, 20.0              # at that price: 110% of the prior close
FOLLOW_MIN_VOLUME = 100_000                   # ... and only once today's volume reached this many shares
SSR_DROP = 0.10                               # Rule 201: a trade at or under 90% of the prior close

# -- Gate 1's account (research/orb/backtest_orb.py, Bot-Trading-Plan section L3). ---------------------
START_EQUITY = 25_000.0
RISK_PCT = 0.01
MAX_POSITION_PCT = 0.25
MIN_NOTIONAL = 500.0
SLIPPAGE = 0.01                               # $ a share on every fill, against the trade
COMMISSION_PER_SHARE = 0.005                  # IBKR fixed
COMMISSION_MIN = 1.0
COMMISSION_MAX_PCT = 0.01
COSTS_2X = {"slippage": 0.02, "commission_per_share": 0.01}

# -- The kill criteria (unchanged from gate 1). --------------------------------------------------------
MIN_TRADES = 300
SHUFFLES = 1000
SHUFFLE_SEED = 49                             # ADR 049
MAX_P = 0.05

# -- Each strategy's named neighbourhood (ADR 049 step 4: the risk cap, the target R, the window, the
# setup's own key numbers and the MACD rule). Values are the template's units (percent as 6, not 0.06).
COMMON_NEIGHBOURS: tuple[tuple[str, dict], ...] = (
    ("risk cap -25%", {"stop_cap": "x0.75"}),
    ("risk cap +50%", {"stop_cap": "x1.5"}),
    ("target 1.5R", {"target_r": 1.5}),
    ("target 2.5R", {"target_r": 2.5}),
    ("window 30 min shorter", {"entry_cutoff": "-30"}),
)
NEIGHBOURS: dict[str, tuple[tuple[str, dict], ...]] = {
    "backside_lower_high": (("fade 6%", {"fade_pct": 6.0}), ("fade 10%", {"fade_pct": 10.0}),
                            ("retrace 40%", {"max_retrace": 40.0}), ("bounce up to 4", {"max_bounce_bars": 4}),
                            ("no MACD rule", {"macd_negative": False})),
    "bear_flag": (("pole 4%", {"pole_min_pct": 4.0}), ("pole 7%", {"pole_min_pct": 7.0}),
                  ("flag up to 4", {"max_flag_bars": 4}), ("retrace 40%", {"max_retrace": 40.0}),
                  ("no MACD rule", {"macd_negative": False})),
    "failed_breakout": (("touch 0.3%", {"touch_pct": 0.3}), ("touch 0.8%", {"touch_pct": 0.8}),
                        ("3 touches", {"min_touches": 3}), ("breaks down within 5", {"trigger_bars": 5}),
                        ("MACD under zero", {"macd_negative": True})),
    "lost_vwap": (("retest 0.1%", {"retest_pct": 0.1}), ("retest 0.5%", {"retest_pct": 0.5}),
                  ("MACD under zero", {"macd_negative": True})),
    "ssr_bounce": (("drop 5%", {"drop_pct": 5.0}), ("drop 8%", {"drop_pct": 8.0}), ("rests within 1%", {"arm_pct": 1.0}),
                   ("rests within 3%", {"arm_pct": 3.0}), ("cancelled after 20 min", {"cancel_min": 20})),
}

ASSUMPTIONS = (
    "Minute bars stand in for the tape: inside each minute the open is the first live price and its low (the high "
    "for the SSR bounce) the second; the order of the high and low inside a minute is unknown.",
    "SSR today comes from the minute lows against the prior close; yesterday's from the movers index (a row whose "
    "whole-day low was 10% or more under its prior close; a built session without the stock reads off).",
    "Nothing in the files reads the tape gate, the grade's news and borrow pillars, liquidity or the float: the "
    "template's stock filter is judged on price and change only, its unknowns by its 'unknown passes'.",
    "One trade at a time on a stock: a trigger while that stock's trade is on is not taken.",
    "Breakdown shorts are judged on their triggers with SSR off; the triggers under SSR (on or unknown) are "
    "reported apart, because minute bars cannot say whether a short above the bid would have filled.",
    "Costs are gate 1's: $25,000 compounding daily, 1% risk a trade, at most 25% of equity a trade, IBKR's fixed "
    "commission and one cent of slippage on every fill.",
)
