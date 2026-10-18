"""Where the operator's data lives, read from the environment on every call so a test (or another PC) can move it.

``NOVA_MARKET_DATA_DIR`` -- the Massive files and their reference dump (default ``E:\\Nova\\massive``);
``NOVA_CATALYST_DIR`` -- the catalyst store and SEC's bulk EDGAR files under ``edgar/`` (default
``F:\\Nova\\catalysts``). The same variables ``research/leaderboard/lb_config.py`` and
``research/catalysts/cat_config.py`` read.
"""
from __future__ import annotations

import os
from pathlib import Path

MASSIVE_DEFAULT = r"E:\Nova\massive"
CATALYST_DEFAULT = r"F:\Nova\catalysts"


def massive() -> Path:
    return Path(os.environ.get("NOVA_MARKET_DATA_DIR") or MASSIVE_DEFAULT)


def reference() -> Path:
    """Massive's reference dump: financials, float, IPOs, ticker details, splits, short interest."""
    return massive() / "store" / "reference"


def movers_db() -> Path:
    from constants_day_movers import DAY_MOVERS_DB_FILENAME, DAY_MOVERS_SUBDIR
    return massive() / DAY_MOVERS_SUBDIR / DAY_MOVERS_DB_FILENAME


def edgar() -> Path:
    """SEC's bulk files: ``companyfacts.zip`` (every XBRL fact) and ``submissions.zip`` (every filing's form/date)."""
    return Path(os.environ.get("NOVA_CATALYST_DIR") or CATALYST_DEFAULT) / "edgar"
