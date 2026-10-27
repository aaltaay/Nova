"""What was known about a stock-day beyond its prices -- news, halts, relative volume -- and the one row filter on it
(ADR 050, ADR 059).

Two readers, one rule. The desk's agent search reads the facts from the movers store's ``day_facts`` table (written
whole by ``research/movers/export_day_facts.py`` from the research stores the backend never reads); the research
front door (``research/market_reads/day_facts.py``) joins the same columns from those stores directly. Both filter
with ``Wanted`` / ``keep`` here, so a stock-day passes or fails the same filter wherever it is asked.

Columns (``DAY_FACT_COLUMNS``): ``catalyst_*`` the catalyst backfill's verdict for the day (null: never judged --
unknown, never no news); ``halts`` the halts that started that day, ``halt_codes`` their codes, ``luld_halts`` /
``news_halts`` the LULD / volatility pauses and the news halts (null: a day the halt log does not cover, never 0);
``rvol_daily`` the day's volume over its usual whole-session volume (null: too little history or not in the
relative-volume table). An unknown never passes a filter that asks about it.
Owner: this module (no state). Blocking SQLite reads -- the routes run them off the event loop.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from day_movers.schema import DAY_FACT_COLUMNS

HALT_GROUPS = ("news", "luld")       # halt_codes words naming a group of codes
FLOAT_UNKNOWN = ("exclude", "include", "only")
BOOLS = {"true": True, "yes": True, "1": True, "false": False, "no": False, "0": False}
FACT_KEYS = DAY_FACT_COLUMNS[2:]
_PARAM_CHUNK = 900


@dataclass(frozen=True)
class Wanted:
    """The row filters on day facts: shares, news, halts, relative volume. None (or empty) asks nothing."""
    float_max: float | None = None
    float_unknown: str = "exclude"
    catalyst: frozenset[str] | None = None
    categories: frozenset[str] | None = None
    words: tuple[str, ...] = ()
    halted: bool | None = None
    halt_codes: frozenset[str] | None = None
    rvol_daily_min: float | None = None

    @property
    def parts(self) -> set[str]:
        """The fact parts these filters read: shares, catalyst, halts, rvol."""
        out = set()
        if self.float_max is not None or self.float_unknown == "only":
            out.add("shares")
        if self.catalyst is not None or self.categories is not None or self.words:
            out.add("catalyst")
        if self.halted is not None or self.halt_codes:
            out.add("halts")
        if self.rvol_daily_min is not None:
            out.add("rvol")
        return out

    @property
    def asks_facts(self) -> bool:
        """Whether a news, halt or relative-volume filter is asked (shares aside)."""
        return bool(self.parts - {"shares"})


def wanted(*, float_max: float | None = None, float_unknown: str = "exclude", catalyst: Iterable[str] | None = None,
           catalyst_category: Iterable[str] | None = None, catalyst_words: Iterable[str] | None = None,
           halted: bool | None = None, halt_codes: Iterable[str] | None = None,
           rvol_daily_min: float | None = None) -> Wanted:
    """A checked ``Wanted`` from a reader's arguments (lower-cased words; codes upper-cased, ``news`` / ``luld``
    kept as group words; one bare string is a list of one, never its letters). ``ValueError`` names a bad one."""
    catalyst, catalyst_category, catalyst_words, halt_codes = (
        [v] if isinstance(v, str) else v for v in (catalyst, catalyst_category, catalyst_words, halt_codes))
    if halted is not None and halted not in (True, False):
        raise ValueError("halted is true (only days with a halt) or false (only days without one)")
    if float_unknown not in FLOAT_UNKNOWN:
        raise ValueError(f"float_unknown must be one of {', '.join(FLOAT_UNKNOWN)}")
    if rvol_daily_min is not None and not float(rvol_daily_min) > 0:
        raise ValueError("rvol_daily_min is a ratio over 0 (5 = 5x the usual daily volume)")
    codes = {str(c).strip() for c in halt_codes or () if str(c).strip()}
    return Wanted(
        float_max=None if float_max is None else float(float_max), float_unknown=float_unknown,
        catalyst=frozenset(c.strip().lower() for c in catalyst if c.strip()) or None if catalyst else None,
        categories=frozenset(c.strip().lower() for c in catalyst_category if c.strip()) or None
        if catalyst_category else None,
        words=tuple(w.strip().lower() for w in catalyst_words or () if w.strip()),
        halted=None if halted is None else bool(halted),
        halt_codes=frozenset(c.lower() if c.lower() in HALT_GROUPS else c.upper() for c in codes) or None,
        rvol_daily_min=None if rvol_daily_min is None else float(rvol_daily_min))


def asked(w: Wanted) -> dict[str, Any]:
    """The filters as an answer echoes them."""
    return {"float_max": w.float_max, "float_unknown": w.float_unknown,
            "catalyst": sorted(w.catalyst) if w.catalyst else None,
            "catalyst_category": sorted(w.categories) if w.categories else None,
            "catalyst_words": list(w.words) or None, "halted": w.halted,
            "halt_codes": sorted(w.halt_codes) if w.halt_codes else None, "rvol_daily_min": w.rvol_daily_min}


def _news_ok(row: dict[str, Any], w: Wanted) -> bool:
    if w.catalyst is not None and (row.get("catalyst_verdict") or "unknown") not in w.catalyst:
        return False
    if w.categories is not None and (row.get("catalyst_category") or "").lower() not in w.categories:
        return False
    title = (row.get("catalyst_title") or "").lower()
    return not w.words or any(word in title for word in w.words)


def _codes_ok(row: dict[str, Any], codes: frozenset[str]) -> bool:
    """A day with a halt whose code is asked (``news`` / ``luld``: any of that group)."""
    have = {c.upper() for c in (row.get("halt_codes") or "").split(",") if c}
    return bool(have & codes) or ("news" in codes and (row.get("news_halts") or 0) > 0) or \
        ("luld" in codes and (row.get("luld_halts") or 0) > 0)


def keep(row: dict[str, Any], w: Wanted, left_out: dict[str, int] | None = None) -> bool:
    """Whether a row carrying these facts passes ``w``. ``left_out`` counts the rows dropped for an unknown:
    ``catalyst_unknown`` (no verdict), ``rvol_unknown``, ``shares_unknown`` (no value under ``float_unknown``
    exclude), ``halts_unknown`` (a day the halt log does not cover). A reader that judges shares itself passes a
    ``Wanted`` with no float limit."""
    left_out = {} if left_out is None else left_out

    def unknown(name: str) -> bool:
        left_out[name] = left_out.get(name, 0) + 1
        return False

    if not _news_ok(row, w):
        return unknown("catalyst_unknown") if row.get("catalyst_verdict") is None else False
    if w.rvol_daily_min is not None:
        if row.get("rvol_daily") is None:
            return unknown("rvol_unknown")
        if row["rvol_daily"] < w.rvol_daily_min:
            return False
    if w.float_max is not None:
        shares = row.get("float_shares")
        if shares is None:
            if w.float_unknown == "exclude":
                return unknown("shares_unknown")
        elif w.float_unknown == "only" or shares > w.float_max:
            return False
    elif w.float_unknown == "only" and row.get("float_shares") is not None:
        return False
    if w.halted is None and not w.halt_codes:
        return True
    if row.get("halts") is None:                  # an uncovered day is unknown: left out
        return unknown("halts_unknown")
    if w.halted is not None and (row["halts"] > 0) != w.halted:
        return False
    return not w.halt_codes or _codes_ok(row, w.halt_codes)


def _list(raw: str | None) -> list[str] | None:
    return [part for part in (raw or "").split(",") if part.strip()] or None


def from_query(q: Any) -> Wanted:
    """The news, halt and relative-volume filters of a ``query.MoverQuery`` (comma lists in the query string;
    shares are the float proof's, not these)."""
    return wanted(catalyst=_list(q.catalyst), catalyst_category=_list(q.catalyst_category),
                  catalyst_words=_list(q.catalyst_words), halted=None if q.halted is None else BOOLS[q.halted.lower()],
                  halt_codes=_list(q.halt_codes), rvol_daily_min=q.rvol_daily_min)


def filter_rows(rows: list[dict[str, Any]], w: Wanted, day_facts: Any, excluded: dict[str, int],
                notes: list[str]) -> list[dict[str, Any]]:
    """Search rows (``query.shape``) that pass ``w``, each carrying its ``day_facts``; ``excluded`` gets the
    count left out (``day_facts``) and the unknowns among them, ``notes`` a line per unknown kind.
    ``day_facts(pairs)`` reads them (``read``); None leaves every fact unknown."""
    known = day_facts([(r["date"], r["symbol"]) for r in rows]) if day_facts else {}
    left_out: dict[str, int] = {}
    kept = []
    for row in rows:
        row["day_facts"] = known.get((row["date"], row["symbol"])) or dict.fromkeys(FACT_KEYS)
        if keep(row["day_facts"], w, left_out):
            kept.append(row)
    excluded["day_facts"] = len(rows) - len(kept)
    excluded.update(left_out)
    for name, what in (("catalyst_unknown", "news verdict"), ("rvol_unknown", "relative volume"),
                       ("halts_unknown", "halt coverage")):
        if left_out.get(name):
            notes.append(f"{left_out[name]} matched with the {what} unknown on that day (left out)")
    return kept


def exported(db: sqlite3.Connection) -> dict[str, Any]:
    """``{exported, first, last}`` of the store's ``day_facts`` (``exported`` False: not written yet)."""
    try:
        first, last = db.execute("SELECT min(session_date), max(session_date) FROM day_facts").fetchone()
    except sqlite3.OperationalError:          # an index built before day facts existed
        return {"exported": False, "first": None, "last": None}
    return {"exported": last is not None, "first": first, "last": last}


def read(db: sqlite3.Connection, pairs: Iterable[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    """``(date, symbol)`` -> its ``FACT_KEYS`` from ``day_facts``, every pair a key; a pair with no row has every
    fact None (unknown)."""
    by_day: dict[str, set[str]] = {}
    for day, symbol in pairs:
        by_day.setdefault(str(day)[:10], set()).add(str(symbol))
    out = {(d, s): dict.fromkeys(FACT_KEYS) for d, symbols in by_day.items() for s in symbols}
    if not exported(db)["exported"]:
        return out
    cols = ", ".join(DAY_FACT_COLUMNS)
    for day, symbols in by_day.items():
        names = sorted(symbols)
        for i in range(0, len(names), _PARAM_CHUNK):
            part = names[i:i + _PARAM_CHUNK]
            sql = f"SELECT {cols} FROM day_facts WHERE session_date = ? AND symbol IN ({', '.join('?' * len(part))})"
            for row in db.execute(sql, [day, *part]):
                found = dict(zip(DAY_FACT_COLUMNS, row, strict=True))
                out[(found["session_date"], found["symbol"])] = {k: found[k] for k in FACT_KEYS}
    return out
