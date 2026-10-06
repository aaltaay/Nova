"""Which days the operator's Massive flat files cover, for the Sim Day calendar and the tab prompt (ADR 046).

Read off the folder tree, no file opened: a day counts when its file is whole (a
``.csv.gz``, never a ``.part`` still arriving). The listing is polled with the
replay listing, so the tree is walked at most once per ``SIM_MASSIVE_DAYS_TTL_SEC``.
"""
from __future__ import annotations

import os
import re
import threading
import time
from datetime import date as date_cls

from constants_sim import SIM_MASSIVE_DAYS_TTL_SEC, SIM_MASSIVE_MINUTES, SIM_MASSIVE_QUOTES, SIM_MASSIVE_TRADES
from sim import massive_files, massive_store

SCHEMA_VERSION = 1
_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.csv\.gz$")
_lock = threading.Lock()
_cache: dict = {"at": 0.0, "root": None, "days": None}


def iso_date(day: str) -> str:
    """``day`` when it is a real ISO date, else ``ValueError`` (the route answers 422)."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day or ""):
        raise ValueError("Dates are YYYY-MM-DD")
    date_cls.fromisoformat(day)
    return day


def _walk(dataset: str) -> set[str]:
    found: set[str] = set()
    base = massive_files.root() / dataset
    try:
        years = [entry for entry in os.scandir(base) if entry.is_dir()]
    except OSError:
        return found
    for year in years:
        try:
            months = [entry for entry in os.scandir(year.path) if entry.is_dir()]
        except OSError:
            continue
        for month in months:
            try:
                found.update(m.group(1) for entry in os.scandir(month.path) if (m := _NAME.match(entry.name)))
            except OSError:
                continue
    return found


def _days() -> dict[str, dict[str, bool]]:
    """``{date: {trades, quotes, minute_aggs}}`` for every day any of the three files is whole, cached."""
    root = str(massive_files.root())
    with _lock:
        if _cache["days"] is not None and _cache["root"] == root and time.monotonic() - _cache["at"] < SIM_MASSIVE_DAYS_TTL_SEC:
            return _cache["days"]
    if massive_files.unavailable_reason() is not None:
        days: dict[str, dict[str, bool]] = {}
    else:
        trades, quotes, minutes = _walk(SIM_MASSIVE_TRADES), _walk(SIM_MASSIVE_QUOTES), _walk(SIM_MASSIVE_MINUTES)
        days = {day: dict(trades=day in trades, quotes=day in quotes, minute_aggs=day in minutes)
                for day in trades | quotes | minutes}
    with _lock:
        _cache.update(at=time.monotonic(), root=root, days=days)
    return days


def reset_for_tests() -> None:
    with _lock:
        _cache.update(at=0.0, root=None, days=None)


def summary() -> dict:
    """The replay listing's ``massive`` block: is the folder there, and how much of it can replay."""
    reason = massive_files.unavailable_reason()
    days = _days()
    tape = sorted(day for day, have in days.items() if have["trades"])
    return dict(available=reason is None, reason=reason, root=str(massive_files.root()), store=str(massive_store.path()),
                trade_days=len(tape), quote_days=sum(1 for have in days.values() if have["quotes"] and have["trades"]),
                first=tape[0] if tape else None, last=tape[-1] if tape else None)


def listing() -> dict:
    """Every day on disk, newest first: ``{schema_version, available, reason, root, days: [{date, trades, quotes, minute_aggs}]}``."""
    reason = massive_files.unavailable_reason()
    days = _days()
    return dict(schema_version=SCHEMA_VERSION, available=reason is None, reason=reason, root=str(massive_files.root()),
                days=[dict(date=day, **days[day]) for day in sorted(days, reverse=True)])
