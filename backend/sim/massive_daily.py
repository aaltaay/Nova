"""The prior session's close from the operator's Massive day bars (``day_aggs_v1``).

Massive's day bar closes on the official close -- checked against IBKR's tick-9
close: GRML 2026-09-18 2.85 and WHLR 2026-09-22 1.87, the two cases ``prior_close``
names -- never the last after-hours trade. One small file per day holds every
ticker, so a close is one file read, held for the next ticker of that day.

The files are as traded, not split-adjusted: across a split the prior close is the
pre-split price. ``prior_close`` therefore asks the leaderboard (split-checked) and
an IBKR download (adjusted) first, and only then these files.
"""
from __future__ import annotations

import csv
import gzip
import logging
import math
import threading
from collections import OrderedDict
from datetime import date as date_cls, timedelta

from constants_sim import SIM_MASSIVE_DAY_CLOSE_CACHE, SIM_MASSIVE_DAYS
from sim import massive_files

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_closes: OrderedDict[tuple[str, str], dict[str, float]] = OrderedDict()


def _read(day: str) -> dict[str, float]:
    """``{ticker: close}`` of ``day``'s day bars; empty when the file is not on disk."""
    path = massive_files.root() / SIM_MASSIVE_DAYS / day[:4] / day[5:7] / f"{day}.csv.gz"
    if not path.is_file():
        return {}
    closes: dict[str, float] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                value = float(row.get("close") or "nan")
            except ValueError:
                continue
            if math.isfinite(value) and value > 0 and row.get("ticker"):
                closes[row["ticker"]] = value
    return closes


def closes(day: str) -> dict[str, float]:
    """Every ticker's close on ``day``, cached by the files' root."""
    key = (str(massive_files.root()), day)
    with _lock:
        if key in _closes:
            _closes.move_to_end(key)
            return _closes[key]
    found = _read(day)
    with _lock:
        _closes[key] = found
        while len(_closes) > SIM_MASSIVE_DAY_CLOSE_CACHE:
            _closes.popitem(last=False)
    return found


def prior_close(symbol: str, day: str) -> float | None:
    """The close of the exchange session before ``day``, from its day bar; None when that day's file or row is
    absent -- never an older session's close standing in for it."""
    from sim.trading_day import last_open_day

    prior = last_open_day(date_cls.fromisoformat(day) - timedelta(days=1)).isoformat()
    try:
        return closes(prior).get(symbol.strip().upper())
    except (OSError, EOFError, csv.Error, UnicodeDecodeError):
        logger.warning("Massive day bars for %s unreadable; no prior close from them", prior, exc_info=True)
        return None


def reset_for_tests() -> None:
    with _lock:
        _closes.clear()
