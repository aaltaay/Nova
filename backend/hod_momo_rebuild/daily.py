"""Each watched stock's facts as of a rebuilt day: what live enrichment would have put on its HOD Momo snapshot.

* **Average volume** -- live reads Yahoo's ``averageVolume``, a 3-month average of daily volume. Here: the mean
  volume of the stock's day bars over the ``HOD_MOMO_REBUILD_AVG_VOLUME_SESSIONS`` sessions before the day, from
  Massive's ``day_aggs`` files (whole-session volume, as those files carry it), split-adjusted.
* **52-week high** -- live reads Yahoo's ``fiftyTwoWeekHigh``. Here: the highest day-bar high over the
  ``HOD_MOMO_REBUILD_52WK_SESSIONS`` sessions before the day, split-adjusted. Never the day's own high: that is
  the future.
* **The day's open** -- live reads IBKR's open tick, which exists only from 09:30; here the day's own day bar.
* **Float** -- live reads Yahoo's float now, and there is no float as of a past day on file, so the build asks
  Yahoo the same way (``fundamentals.fetch_fundamentals``) and every rebuilt alert says so
  (``HOD_MOMO_REBUILD_FLOAT_BASIS``). A stock Yahoo does not know has an unknown float, as it would live.

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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date as date_cls, timedelta

from constants_hod_momo import (
    HOD_MOMO_REBUILD_52WK_SESSIONS,
    HOD_MOMO_REBUILD_AVG_VOLUME_SESSIONS,
    HOD_MOMO_REBUILD_DAILY_LOOKBACK_DAYS,
    HOD_MOMO_REBUILD_FLOAT_WORKERS,
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


def floats(symbols: Iterable[str], fetch: Callable[[str], dict] | None = None) -> dict[str, dict]:
    """Yahoo's float now for each symbol, as live enrichment reads it: ``{symbol: {float_shares,
    float_contradicted, shares_outstanding}}``, values ``None`` where Yahoo has none."""
    if fetch is None:
        from fundamentals import fetch_fundamentals as fetch

    def one(symbol: str) -> tuple[str, dict]:
        try:
            fund = fetch(symbol) or {}
        except Exception:  # noqa: BLE001 -- an unknown float, as live reads a failed lookup
            logger.warning("HOD rebuild: Yahoo lookup for %s failed; its float is unknown", symbol, exc_info=True)
            fund = {}
        return symbol, {key: fund.get(key) for key in ("float_shares", "float_contradicted", "shares_outstanding")}

    with ThreadPoolExecutor(max_workers=HOD_MOMO_REBUILD_FLOAT_WORKERS, thread_name_prefix="hod-rebuild-float") as pool:
        return dict(pool.map(one, sorted(set(symbols))))
