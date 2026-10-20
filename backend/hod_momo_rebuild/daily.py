"""Each watched stock's facts as of a rebuilt day: what live enrichment would have put on its HOD Momo snapshot.

* **Average volume** -- live reads Yahoo's ``averageVolume``, a 3-month average of daily volume. Here: the mean
  volume of the stock's day bars over the ``HOD_MOMO_REBUILD_AVG_VOLUME_SESSIONS`` sessions before the day, from
  Massive's ``day_aggs`` files (whole-session volume, as those files carry it), split-adjusted.
* **52-week high** -- live reads Yahoo's ``fiftyTwoWeekHigh``. Here: the highest day-bar high over the
  ``HOD_MOMO_REBUILD_52WK_SESSIONS`` sessions before the day, split-adjusted. Never the day's own high: that is
  the future.
* **The day's open** -- live reads IBKR's open tick, which exists only from 09:30; here the day's own day bar.
* **Float** -- live reads Yahoo's float, which is only ever today's: on a past day it is the future. Here: SEC
  shares outstanding filed by the calendar day before (``day_movers.floats.sec_shares`` with ``before``), on the
  day's share basis, as the snapshot's float and its shares outstanding (``HOD_MOMO_REBUILD_FLOAT_BASIS``). A float
  cannot exceed shares outstanding, so it is an upper bound: under a max-float line it proves the float is, over
  it the gate refuses, as an unknown float is refused live (``engine`` sits out the min-float strategies, which an
  upper bound can never prove). A stock with no count on file has an unknown float.

Splits are Massive's list plus the SEC-confirmed ones (``leaderboard.seconds.inputs.splits``): a split executing
after a session and by the day scales that session's price by ``split_from / split_to`` and its volume by the
inverse, onto the day's share basis.
"""
from __future__ import annotations

import csv
import gzip
import logging
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date as date_cls, timedelta
from pathlib import Path

from constants_hod_momo import (
    HOD_MOMO_REBUILD_52WK_SESSIONS,
    HOD_MOMO_REBUILD_AVG_VOLUME_SESSIONS,
    HOD_MOMO_REBUILD_DAILY_LOOKBACK_DAYS,
)
from constants_sim import SIM_MASSIVE_DAYS
from leaderboard.seconds import inputs
from sim import massive_files

logger = logging.getLogger(__name__)


@dataclass
class Facts:
    avg_volume: float | None = None
    fifty_two_week_high: float | None = None
    day_open: float | None = None
    float_shares: float | None = None
    float_contradicted: bool | None = None
    shares_outstanding: float | None = None


def prior_sessions(day: str, count: int) -> list[str]:
    """The ``count`` latest dates before ``day`` with a Massive day-bar file, newest first."""
    d = date_cls.fromisoformat(day)
    out: list[str] = []
    for back in range(1, HOD_MOMO_REBUILD_DAILY_LOOKBACK_DAYS + 1):
        prior = (d - timedelta(days=back)).isoformat()
        if massive_files.day_file(SIM_MASSIVE_DAYS, prior) is not None:
            out.append(prior)
            if len(out) >= count:
                break
    return out


def _day_bars(day: str, wanted: set[str]) -> dict[str, tuple[float, float, float]]:
    """``{ticker: (open, high, volume)}`` of ``day``'s day bars for ``wanted``."""
    path = massive_files.day_file(SIM_MASSIVE_DAYS, day)
    if path is None:
        return {}
    out: dict[str, tuple[float, float, float]] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        t, o, h, v = (header.index(name) for name in ("ticker", "open", "high", "volume"))
        for row in reader:
            if row[t] not in wanted:
                continue
            try:
                values = (float(row[o]), float(row[h]), float(row[v] or 0.0))
            except ValueError:
                continue
            if all(math.isfinite(x) for x in values):
                out[row[t]] = values
    return out


def _split_factors(day: str, symbols: set[str], sessions: list[str]) -> Callable[[str, str], float]:
    """``factor(symbol, session)``: what that session's price is multiplied by to read on ``day``'s share basis."""
    oldest = sessions[-1] if sessions else day
    events = [(t, executed, f / to) for t, executed, f, to in inputs.splits()
              if t in symbols and oldest < executed <= day]

    def factor(symbol: str, session: str) -> float:
        out = 1.0
        for ticker, executed, ratio in events:
            if ticker == symbol and session < executed:
                out *= ratio
        return out

    return factor


def history(day: str, symbols: Iterable[str]) -> dict[str, Facts]:
    """Average volume, 52-week high and the day's open for each symbol (no float). A stock with no day bar in a
    window has that fact unknown, never zero."""
    wanted = set(symbols)
    sessions = prior_sessions(day, max(HOD_MOMO_REBUILD_52WK_SESSIONS, HOD_MOMO_REBUILD_AVG_VOLUME_SESSIONS))
    factor = _split_factors(day, wanted, sessions)
    volumes: dict[str, list[float]] = {s: [] for s in wanted}
    highs: dict[str, float] = {}
    for index, session in enumerate(sessions):
        for symbol, (_open, high, volume) in _day_bars(session, wanted).items():
            ratio = factor(symbol, session)
            if index < HOD_MOMO_REBUILD_52WK_SESSIONS and high > 0:
                highs[symbol] = max(highs.get(symbol, 0.0), high * ratio)
            if index < HOD_MOMO_REBUILD_AVG_VOLUME_SESSIONS:
                volumes[symbol].append(volume / ratio)
    today = _day_bars(day, wanted)
    out: dict[str, Facts] = {}
    for symbol in wanted:
        vols = volumes[symbol]
        avg = sum(vols) / len(vols) if vols else None
        opened = today.get(symbol, (None,))[0]
        out[symbol] = Facts(avg_volume=avg if avg and avg > 0 else None,
                            fifty_two_week_high=highs.get(symbol),
                            day_open=opened if opened and opened > 0 else None)
    return out


def floats(day: str, symbols: Iterable[str], database: Path | None = None) -> dict[str, dict]:
    """Each symbol's float as known before ``day`` opened: ``{symbol: {float_shares, float_contradicted,
    shares_outstanding, as_of, filed}}`` -- the SEC count filed by the day before, as both the float and shares
    outstanding; every value ``None`` where none is on file (or the movers store is not built)."""
    from day_movers import floats as mover_floats, store as movers

    wanted = sorted(set(symbols))
    out = {s: {"float_shares": None, "float_contradicted": None, "shares_outstanding": None, "as_of": None,
               "filed": None} for s in wanted}
    db = movers.read_only(database)
    if db is None:
        logger.warning("HOD rebuild: no day movers store; every float on %s is unknown", day)
        return out
    try:
        counts = mover_floats.sec_shares(db, [(day, s) for s in wanted], before=True)
    finally:
        db.close()
    for (_day, symbol), count in counts.items():
        shares = float(count["shares"])
        if shares > 0:
            out[symbol].update(float_shares=shares, shares_outstanding=shares, as_of=count["as_of"],
                               filed=count["filed"])
    return out
