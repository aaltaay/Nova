"""Search the day movers index (ADR 050): plain numbers in, matches and their percentages out.

Nothing here knows a shape word: "ascending", "fader" or "small cap" are an agent's to turn into these numbers
(and the operator's to confirm into the dictionary). Percent arguments and answers are percent points.
Blocking (SQLite) -- the route runs it off the event loop.
"""
from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass, fields
from datetime import datetime
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from constants_agent_desk import (
    AGENT_MOVERS_COMMON_KINDS,
    AGENT_MOVERS_LIMIT_DEFAULT,
    AGENT_MOVERS_LIMIT_MAX,
    AGENT_MOVERS_MAX_SCAN,
)
from constants_day_movers import (
    DAY_MOVERS_DOWN_MARKS,
    DAY_MOVERS_LIKELY_SPLIT_MAX_VOLUME_RATIO,
    DAY_MOVERS_REAL_JUMP_MIN_VOLUME_RATIO,
    DAY_MOVERS_UP_MARKS,
)
from day_movers.schema import MOVER_COLUMNS

ET = ZoneInfo("America/New_York")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_SYMBOL = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")

SORTS = {
    "newest": ("session_date", True), "oldest": ("session_date", False),
    "high": ("high_pct", True), "low": ("low_pct", False), "close": ("close_pct", True),
    "gap": ("gap_pct", True), "volume": ("volume", True), "dollar_volume": ("dollar_volume", True),
}
FLOAT_UNKNOWN = ("exclude", "include", "only")
SPLITS = ("exclude_likely", "include", "only_suspects")
# Percent filters: (argument, column) -- compared as fractions.
_PCT_FILTERS = (
    ("high_min", "high_pct", ">="), ("high_max", "high_pct", "<="),
    ("low_min", "low_pct", ">="), ("low_max", "low_pct", "<="),
    ("close_min", "close_pct", ">="), ("close_max", "close_pct", "<="),
    ("gap_min", "gap_pct", ">="), ("gap_max", "gap_pct", "<="),
)
_CLOSE_POS_SQL = "((close - day_low) / NULLIF(day_high - day_low, 0))"
_GIVEBACK_SQL = "(CASE WHEN day_high > prev_close THEN (day_high - close) / (day_high - prev_close) END)"
_LIKELY_SPLIT_SQL = (f"(split_suspect = 1 AND prev_volume > 0 AND volume <= prev_volume * "
                     f"{DAY_MOVERS_LIKELY_SPLIT_MAX_VOLUME_RATIO!r})")


class QueryError(ValueError):
    """A search argument Nova cannot use; ``field`` names it."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class MoverQuery:
    date_from: str | None = None
    date_to: str | None = None
    symbol: str | None = None
    kinds: str = "common"
    price_min: float | None = None
    price_max: float | None = None
    high_min: float | None = None
    high_max: float | None = None
    low_min: float | None = None
    low_max: float | None = None
    close_min: float | None = None
    close_max: float | None = None
    gap_min: float | None = None
    gap_max: float | None = None
    close_pos_min: float | None = None
    close_pos_max: float | None = None
    giveback_min: float | None = None
    giveback_max: float | None = None
    high_after: str | None = None
    high_before: str | None = None
    volume_min: float | None = None
    dollar_volume_min: float | None = None
    float_max: float | None = None
    float_unknown: str = "exclude"
    replayable: bool = False
    splits: str = "exclude_likely"
    sort: str = "newest"
    limit: int = AGENT_MOVERS_LIMIT_DEFAULT

    def asked(self) -> dict[str, Any]:
        """The arguments that differ from the defaults (what the search was, in the answer)."""
        default = MoverQuery()
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) != getattr(default, f.name)}


_ALIASES = {"from": "date_from", "to": "date_to"}
_FLOATS = {f.name for f in fields(MoverQuery) if f.type in ("float | None",)}


def _number(name: str, raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise QueryError(name, f"{name} must be a number, not {raw!r}") from None
    if not math.isfinite(value):
        raise QueryError(name, f"{name} must be a finite number")
    return value


def parse(params: dict[str, Any]) -> MoverQuery:
    """A ``MoverQuery`` from query-string arguments; ``QueryError`` names the first bad one."""
    known = {f.name for f in fields(MoverQuery)}
    values: dict[str, Any] = {}
    for raw_key, raw in params.items():
        key = _ALIASES.get(raw_key, raw_key)
        if key not in known:
            raise QueryError(raw_key, f"unknown search argument {raw_key!r}")
        if raw is None or raw == "":
            continue
        if key in _FLOATS:
            values[key] = _number(raw_key, raw)
        elif key == "limit":
            limit = int(_number("limit", raw))
            if not 1 <= limit <= AGENT_MOVERS_LIMIT_MAX:
                raise QueryError("limit", f"limit must be 1-{AGENT_MOVERS_LIMIT_MAX}")
            values[key] = limit
        elif key == "replayable":
            values[key] = str(raw).strip().lower() in ("1", "true", "yes")
        else:
            values[key] = str(raw).strip()
    q = MoverQuery(**values)
    for name in ("date_from", "date_to"):
        value = getattr(q, name)
        if value is not None and not _DATE.match(value):
            raise QueryError(name, f"{name} must be YYYY-MM-DD")
    for name in ("high_after", "high_before"):
        value = getattr(q, name)
        if value is not None and not _HHMM.match(value):
            raise QueryError(name, f"{name} must be HH:MM (ET)")
    if q.symbol is not None and not _SYMBOL.match(q.symbol):
        raise QueryError("symbol", "symbol must be a ticker")
    if q.sort not in SORTS:
        raise QueryError("sort", f"sort must be one of {', '.join(SORTS)}")
    if q.float_unknown not in FLOAT_UNKNOWN:
        raise QueryError("float_unknown", f"float_unknown must be one of {', '.join(FLOAT_UNKNOWN)}")
    if q.splits not in SPLITS:
        raise QueryError("splits", f"splits must be one of {', '.join(SPLITS)}")
    for name in ("close_pos_min", "close_pos_max", "giveback_min", "giveback_max"):
        value = getattr(q, name)
        if value is not None and not -1.0 <= value <= 2.0:
            raise QueryError(name, f"{name} is a share of the day's range (0-1)")
    return q


def _kinds_sql(kinds: str) -> tuple[str, list[Any]]:
    if kinds == "all":
        return "", []
    if kinds == "common":
        marks = ", ".join("?" for _ in AGENT_MOVERS_COMMON_KINDS)
        return (f"(kind IN ({marks}) OR (kind IS NULL AND length(symbol) <= 4 AND symbol NOT GLOB '*[^A-Z]*'))",
                list(AGENT_MOVERS_COMMON_KINDS))
    wanted = [k.strip().upper() for k in kinds.split(",") if k.strip()]
    if not wanted:
        raise QueryError("kinds", "kinds must be common, all, or a list of types (CS,ADRC,WARRANT,...)")
    return f"kind IN ({', '.join('?' for _ in wanted)})", wanted


def where(q: MoverQuery) -> tuple[str, list[Any]]:
    """Every filter SQLite can apply; the rest (time of the high, float, replayable) run after."""
    clauses: list[str] = []
    args: list[Any] = []
    if q.date_from:
        clauses.append("session_date >= ?")
        args.append(q.date_from)
    if q.date_to:
        clauses.append("session_date <= ?")
        args.append(q.date_to)
    if q.symbol:
        clauses.append("symbol = ?")
        args.append(q.symbol.upper())
    kinds, kind_args = _kinds_sql(q.kinds)
    if kinds:
        clauses.append(kinds)
        args.extend(kind_args)
    if q.price_min is not None:
        clauses.append("COALESCE(prev_close, open) >= ?")
        args.append(q.price_min)
    if q.price_max is not None:
        clauses.append("COALESCE(prev_close, open) <= ?")
        args.append(q.price_max)
    for name, column, op in _PCT_FILTERS:
        value = getattr(q, name)
        if value is not None:
            clauses.append(f"{column} {op} ?")
            args.append(value / 100.0)
    for name, expr, op in (("close_pos_min", _CLOSE_POS_SQL, ">="), ("close_pos_max", _CLOSE_POS_SQL, "<="),
                           ("giveback_min", _GIVEBACK_SQL, ">="), ("giveback_max", _GIVEBACK_SQL, "<=")):
        value = getattr(q, name)
        if value is not None:
            clauses.append(f"{expr} {op} ?")
            args.append(value)
    if q.volume_min is not None:
        clauses.append("volume >= ?")
        args.append(q.volume_min)
    if q.dollar_volume_min is not None:
        clauses.append("dollar_volume >= ?")
        args.append(q.dollar_volume_min)
    if q.splits == "exclude_likely":
        clauses.append(f"NOT {_LIKELY_SPLIT_SQL}")
    elif q.splits == "only_suspects":
        clauses.append("split_suspect = 1")
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", args


def et_hhmm(ts: Any) -> str | None:
    return None if ts is None else datetime.fromtimestamp(int(ts), ET).strftime("%H:%M")


def _pct(value: Any) -> float | None:
    return None if value is None else round(float(value) * 100.0, 2)


def _share(n: int, total: int) -> float | None:
    return None if not total else round(100.0 * n / total, 1)


def split_label(row: dict[str, Any]) -> str | None:
    """``listed`` | ``likely_split`` | ``suspect`` | None. An overnight jump that traded several times the shares
    of the session before is a real move (#772), not a split: no label."""
    if row.get("split_listed"):
        return "listed"
    if not row.get("split_suspect"):
        return None
    pv, v = row.get("prev_volume"), row.get("volume")
    if not pv or pv <= 0 or v is None:
        return "suspect"
    if v <= pv * DAY_MOVERS_LIKELY_SPLIT_MAX_VOLUME_RATIO:
        return "likely_split"
    return None if v >= pv * DAY_MOVERS_REAL_JUMP_MIN_VOLUME_RATIO else "suspect"


def shape(row: dict[str, Any], replayable: set[str] | None) -> dict[str, Any]:
    """One stock-day on the wire (AGENTS.md section 3): percent points, ET times, the derived reads."""
    hi, lo, close, pc = row["day_high"], row["day_low"], row["close"], row["prev_close"]
    close_pos = (close - lo) / (hi - lo) if hi is not None and lo is not None and hi > lo else None
    giveback = (hi - close) / (hi - pc) if pc and hi is not None and hi > pc else None
    marks = {**DAY_MOVERS_UP_MARKS, **DAY_MOVERS_DOWN_MARKS}
    return {
        "date": row["session_date"], "symbol": row["symbol"], "kind": row["kind"],
        "prev_close": pc, "open": row["open"], "high": row["high"], "low": row["low"], "close": close,
        "volume": row["volume"], "dollar_volume": row["dollar_volume"],
        "day_high": hi, "day_high_et": et_hhmm(row["day_high_ts"]), "day_low": lo, "day_low_et": et_hhmm(row["day_low_ts"]),
        "pm_high": row["pm_high"], "ah_high": row["ah_high"],
        "high_pct": _pct(row["high_pct"]), "low_pct": _pct(row["low_pct"]),
        "close_pct": _pct(row["close_pct"]), "gap_pct": _pct(row["gap_pct"]),
        "close_pos": None if close_pos is None else round(close_pos, 3),
        "giveback": None if giveback is None else round(giveback, 3),
        "first_et": {name.removesuffix("_ts"): et_hhmm(row[name]) for name in marks},
        "replayable": None if replayable is None else row["session_date"] in replayable,
        "split": split_label(row),
    }


def _in_time(row: dict[str, Any], after: str | None, before: str | None) -> bool:
    at = et_hhmm(row["day_high_ts"])
    if at is None:
        return False
    hh, mm = (int(x) for x in at.split(":"))
    minute = hh * 60 + mm
    if after is not None:
        a_h, a_m = (int(x) for x in after.split(":"))
        if minute < a_h * 60 + a_m:
            return False
    if before is not None:
        b_h, b_m = (int(x) for x in before.split(":"))
        if minute > b_h * 60 + b_m:
            return False
    return True


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The percentages over every match (shares of ``matched``, in percent)."""
    n = len(rows)
    above_prior = sum(1 for r in rows if r["close_pct"] is not None and r["close_pct"] > 0)
    above_open = sum(1 for r in rows if r["close"] is not None and r["open"] and r["close"] > r["open"])
    positions = [r["close_pos"] for r in rows if r["close_pos"] is not None]
    highs = [r["high_pct"] for r in rows if r["high_pct"] is not None]
    closes = [r["close_pct"] for r in rows if r["close_pct"] is not None]
    givebacks = [r["giveback"] for r in rows if r["giveback"] is not None]
    return {
        "matched": n,
        "closed_above_prior_close": _share(above_prior, n),
        "closed_above_open": _share(above_open, n),
        "closed_top_third": _share(sum(1 for p in positions if p >= 2 / 3), n),
        "closed_bottom_third": _share(sum(1 for p in positions if p <= 1 / 3), n),
        "median_high_pct": round(median(highs), 2) if highs else None,
        "median_close_pct": round(median(closes), 2) if closes else None,
        "median_giveback": round(median(givebacks), 3) if givebacks else None,
    }


def search(
    db: sqlite3.Connection, q: MoverQuery, *, replayable: set[str] | None = None,
    floats: Any = None,
) -> dict[str, Any]:
    """The matches for ``q``. ``replayable``: the days whose trades file is on disk (``None``: unknown).

    ``floats(pairs, limit) -> {(date, symbol): proof}`` answers a float limit (``day_movers.floats``).
    """
    clause, args = where(q)
    count = db.execute(f"SELECT count(*) FROM movers{clause}", args).fetchone()[0]
    answer: dict[str, Any] = {"query": q.asked(), "units": "percent", "notes": []}
    if count > AGENT_MOVERS_MAX_SCAN:
        answer.update(count=count, rows=[], summary=None, excluded={}, too_broad=True)
        answer["notes"].append(f"{count:,} stock-days match: narrow the search (at most {AGENT_MOVERS_MAX_SCAN:,})")
        return answer
    cursor = db.execute(f"SELECT {', '.join(MOVER_COLUMNS)} FROM movers{clause}", args)
    raw = [dict(zip(MOVER_COLUMNS, r, strict=True)) for r in cursor.fetchall()]
    excluded: dict[str, int] = {}
    if q.high_after or q.high_before:
        kept = [r for r in raw if _in_time(r, q.high_after, q.high_before)]
        excluded["high_time"] = len(raw) - len(kept)
        raw = kept
    if q.replayable:
        if replayable is None:
            answer["notes"].append("which days are on disk is unknown: replayable not applied")
        else:
            kept = [r for r in raw if r["session_date"] in replayable]
            excluded["not_replayable"] = len(raw) - len(kept)
            raw = kept
    rows = [shape(r, replayable) for r in raw]
    if q.float_max is not None:
        proofs = floats([(r["date"], r["symbol"]) for r in rows], q.float_max) if floats else {}
        for row in rows:
            row["float"] = proofs.get((row["date"], row["symbol"])) or {
                "shares": None, "source": None, "as_of": None, "proof": "unknown"}
        failed = [r for r in rows if r["float"]["proof"] == "fail"]
        unknown = [r for r in rows if r["float"]["proof"] == "unknown"]
        passed = [r for r in rows if r["float"]["proof"] == "pass"]
        excluded["float_over_limit"] = len(failed)
        excluded["float_unknown"] = len(unknown) if q.float_unknown == "exclude" else 0
        rows = {"exclude": passed, "include": passed + unknown, "only": unknown}[q.float_unknown]
        if unknown:
            answer["notes"].append(
                f"{len(unknown)} matched with the float unknown on that day "
                f"({'left out' if q.float_unknown == 'exclude' else 'listed'}): float_unknown=include to list them")
    rows = sort_rows(rows, q.sort)
    answer.update(count=len(rows), rows=rows[: q.limit], summary=summary(rows), excluded=excluded)
    return answer


_SORT_FIELD = {"session_date": "date", "high_pct": "high_pct", "low_pct": "low_pct", "close_pct": "close_pct",
               "gap_pct": "gap_pct", "volume": "volume", "dollar_volume": "dollar_volume"}


def sort_rows(rows: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    """Ordered by ``sort``; a row without the figure goes last; ties newest first, then by symbol."""
    column, descending = SORTS[sort]
    field = _SORT_FIELD[column]
    present = [r for r in rows if r[field] is not None]
    missing = [r for r in rows if r[field] is None]
    present.sort(key=lambda r: r["symbol"])
    present.sort(key=lambda r: r["date"], reverse=True)
    present.sort(key=lambda r: r[field], reverse=descending)
    return present + missing
