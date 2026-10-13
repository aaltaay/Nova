"""Split events from three lists, merged. Pure.

  massive         the operator's Massive reference archive (``splits.json``): ``execution_date``,
                  ``split_from`` (old shares), ``split_to`` (new shares); a 1-for-50 reverse split is 50 -> 1
  sec_confirmed   the splits SEC filings proved that Massive's list misses (#772), in the same shape
  yahoo           Yahoo's history: the day it took effect and one ratio, new shares over old (0.02)

One split is one event on the day it took effect, naming every list that has it. Lists within
``CHART_EVENTS_SPLIT_MATCH_DAYS`` of each other with the same ratio (``CHART_EVENTS_SPLIT_RATIO_TOLERANCE``)
are one split, on Massive's day; a list that gives the same day another ratio is named in ``disagreement``,
never dropped. Whole shares are named when the ratio is one ("1 for 50", "3 for 2"); a stock dividend's
1.0369 is left a ratio. A ratio that is not a split (1, zero, negative, not a number) is left out.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from fractions import Fraction
from typing import Any, Iterable, Mapping

from chart_events.constants_chart_events import (
    CHART_EVENTS_SOURCE_MASSIVE,
    CHART_EVENTS_SOURCE_SEC_CONFIRMED,
    CHART_EVENTS_SOURCE_YAHOO,
    CHART_EVENTS_SPLIT_MATCH_DAYS,
    CHART_EVENTS_SPLIT_RATIO_TOLERANCE,
)

# How close a ratio must come to whole shares to be named in them (Yahoo writes 1-for-6 as 0.166667).
_WHOLE_TOLERANCE = 1e-4
_MAX_SHARES = 100


def shares(ratio: Any) -> dict[str, Any] | None:
    """A ratio of new shares over old as the split it is: ``ratio``, ``new_shares`` / ``old_shares`` (None when
    no small whole numbers make it) and ``reverse``; None when it is not a split."""
    try:
        r = float(ratio)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(r) or r <= 0 or abs(r - 1.0) < 1e-9:
        return None
    new = old = None
    for whole, flipped in ((r, False), (1.0 / r, True)):
        n = round(whole)
        if n >= 2 and abs(whole - n) <= whole * _WHOLE_TOLERANCE:
            new, old = (1, n) if flipped else (n, 1)
            break
    if new is None:
        frac = Fraction(r).limit_denominator(_MAX_SHARES)
        if frac.numerator != frac.denominator and abs(float(frac) - r) <= r * _WHOLE_TOLERANCE:
            new, old = frac.numerator, frac.denominator
    return {"ratio": r, "new_shares": new, "old_shares": old, "reverse": r < 1}


def _day(when: Any) -> date | None:
    if isinstance(when, datetime):
        return when.date()
    if isinstance(when, date):
        return when
    try:
        return date.fromisoformat(str(when)[:10])
    except ValueError:
        return None


def _listed(rows: Iterable[Mapping[str, Any]], source: str) -> list[tuple[date, dict, str]]:
    out = []
    for row in rows:
        day = _day(row.get("execution_date"))
        try:
            split = shares(float(row.get("split_to")) / float(row.get("split_from")))
        except (TypeError, ValueError, ZeroDivisionError):
            split = None
        if day and split:
            out.append((day, split, source))
    return out


def _same(a: dict, b: dict) -> bool:
    return abs(a["ratio"] - b["ratio"]) <= CHART_EVENTS_SPLIT_RATIO_TOLERANCE * max(a["ratio"], b["ratio"])


def _words(split: dict) -> str:
    if split["new_shares"]:
        return f"{split['new_shares']} for {split['old_shares']}"
    return f"{split['ratio']:.4g} for 1"


def events(*, massive: Iterable[Mapping[str, Any]] = (), confirmed: Iterable[Mapping[str, Any]] = (),
           yahoo: Iterable[tuple[Any, Any]] = (), since: date | None = None) -> list[dict[str, Any]]:
    """The merged split events, oldest first (from ``since`` on, when given)."""
    merged: list[dict[str, Any]] = []
    listed = _listed(massive, CHART_EVENTS_SOURCE_MASSIVE)
    taken = {day for day, _split, _src in listed}
    listed += [x for x in _listed(confirmed, CHART_EVENTS_SOURCE_SEC_CONFIRMED) if x[0] not in taken]
    for day, split, source in sorted(listed, key=lambda x: x[0]):
        merged.append({"day": day, **split, "sources": [source], "disagreement": None})
    for when, ratio in yahoo:
        day, split = _day(when), shares(ratio)
        if day is None or split is None:
            continue
        near = [e for e in merged if abs((e["day"] - day).days) <= CHART_EVENTS_SPLIT_MATCH_DAYS]
        match = next((e for e in near if _same(e, split)), None)
        if match is not None:
            match["sources"].append(CHART_EVENTS_SOURCE_YAHOO)
            if match["day"] != day:
                match["disagreement"] = f"Yahoo lists it on {day.isoformat()}"
            continue
        clash = next((e for e in near if e["day"] == day), None)
        if clash is not None:
            clash["sources"].append(CHART_EVENTS_SOURCE_YAHOO)
            clash["disagreement"] = f"Yahoo lists {_words(split)}"
            continue
        merged.append({"day": day, **split, "sources": [CHART_EVENTS_SOURCE_YAHOO], "disagreement": None})
    out: list[dict[str, Any]] = []
    for e in sorted(merged, key=lambda e: e["day"]):
        if since is not None and e["day"] < since:
            continue
        same_day = sum(1 for o in out if o["day"] == e["day"].isoformat())
        suffix = f":{same_day + 1}" if same_day else ""     # two stock dividends on one day are two events
        out.append({"id": f"split:{e['day'].isoformat()}{suffix}", "kind": "split", "day": e["day"].isoformat(),
                    "ratio": e["ratio"], "new_shares": e["new_shares"], "old_shares": e["old_shares"],
                    "reverse": e["reverse"], "sources": e["sources"], "disagreement": e["disagreement"]})
    return out
