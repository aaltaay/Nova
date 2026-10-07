"""A float limit on a past session: passed on evidence, else unknown (ADR 050 decision 6).

Operator: "proven, else unknown". Two kinds of evidence, never today's float:
- the float Nova knew that day -- its enrichment snapshot (``archive.db``, 2026-07-28 on): passes at or under
  the limit, fails over it;
- SEC shares outstanding (``sec_shares`` in the movers store): a float cannot exceed the shares outstanding, so a
  count at or under the limit passes. Only a count filed by that day and reported as of no more than
  ``DAY_MOVERS_SEC_SHARES_MAX_AGE_DAYS`` before it counts, put on the session's share basis through the splits
  listed in between. A count over the limit proves nothing (the float may still be under it): unknown.
Blocking (SQLite) -- the route runs it off the event loop.
"""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from constants_day_movers import DAY_MOVERS_SEC_SHARES_MAX_AGE_DAYS

logger = logging.getLogger(__name__)

Pair = tuple[str, str]


def _chunks(items: list[Any], size: int = 400) -> Iterable[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def enrichment_floats(pairs: list[Pair], database=None) -> dict[Pair, float]:
    """The float the desk's enrichment snapshot held for each (date, symbol), read-only; none without the file."""
    if database is None:
        from constants_archive_news import ARCHIVE_DB_FILENAME
        from paths import cache_root

        database = cache_root() / ARCHIVE_DB_FILENAME
    if not pairs or not database.is_file():
        return {}
    wanted = set(pairs)
    out: dict[Pair, float] = {}
    db = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True, timeout=5.0)
    try:
        for dates in _chunks(sorted({d for d, _ in pairs})):
            rows = db.execute(
                "SELECT session_date, symbol, float_shares FROM enrichment_snapshots"
                f" WHERE session_date IN ({', '.join('?' for _ in dates)}) AND float_shares > 0", dates,
            ).fetchall()
            for day, symbol, shares in rows:
                key = (str(day), str(symbol).upper())
                if key in wanted:
                    out[key] = float(shares)
    except sqlite3.Error as exc:  # maintainer: allow-swallow an unreadable snapshot leaves the float unknown (logged)
        logger.warning("day movers: enrichment snapshots unreadable: %s", exc)
        return {}
    finally:
        db.close()
    return out


def _split_factor(db: sqlite3.Connection, symbol: str, after: str, through: str) -> float:
    """Shares on the ``after`` basis -> the ``through`` basis (a 1-for-10 reverse split divides by 10)."""
    try:
        rows = db.execute(
            "SELECT split_from, split_to FROM splits WHERE symbol = ? AND execution_date > ? AND execution_date <= ?",
            (symbol, after, through),
        ).fetchall()
    except sqlite3.OperationalError:   # a store built before the splits table: nothing listed
        return 1.0
    factor = 1.0
    for split_from, split_to in rows:
        if split_from and split_to:
            factor *= float(split_to) / float(split_from)
    return factor


def sec_shares(db: sqlite3.Connection, pairs: list[Pair]) -> dict[Pair, dict[str, Any]]:
    """The newest SEC share count usable on each (date, symbol): ``{shares, as_of, filed, age_days}``."""
    out: dict[Pair, dict[str, Any]] = {}
    for day, symbol in pairs:
        oldest = (date.fromisoformat(day) - timedelta(days=DAY_MOVERS_SEC_SHARES_MAX_AGE_DAYS)).isoformat()
        try:
            row = db.execute(
                "SELECT as_of, filed, shares FROM sec_shares WHERE symbol = ? AND filed <= ? AND as_of <= ?"
                " AND as_of >= ? ORDER BY as_of DESC, filed DESC LIMIT 1", (symbol, day, day, oldest),
            ).fetchone()
        except sqlite3.OperationalError:  # maintainer: allow-swallow a store with no counts: every float unknown
            return {}
        if row is None:
            continue
        as_of, filed, shares = row[0], row[1], float(row[2])
        shares *= _split_factor(db, symbol, as_of, day)
        out[(day, symbol)] = {"shares": round(shares), "as_of": as_of, "filed": filed,
                              "age_days": (date.fromisoformat(day) - date.fromisoformat(as_of)).days}
    return out


def proofs(pairs: list[Pair], limit: float, *, db: sqlite3.Connection, archive=None) -> dict[Pair, dict[str, Any]]:
    """``{(date, symbol): {shares, source, as_of, proof}}`` for a float limit of ``limit`` shares."""
    snapshots = enrichment_floats(pairs, archive)
    sec = sec_shares(db, [p for p in pairs if p not in snapshots])
    out: dict[Pair, dict[str, Any]] = {}
    for pair in pairs:
        if pair in snapshots:
            shares = snapshots[pair]
            out[pair] = {"shares": round(shares), "source": "enrichment", "as_of": pair[0],
                         "proof": "pass" if shares <= limit else "fail"}
        elif pair in sec:
            count = sec[pair]
            out[pair] = {"shares": count["shares"], "source": "sec_shares_outstanding", "as_of": count["as_of"],
                         "filed": count["filed"], "age_days": count["age_days"],
                         "proof": "pass" if count["shares"] <= limit else "unknown"}
        else:
            out[pair] = {"shares": None, "source": None, "as_of": None, "proof": "unknown"}
    return out
