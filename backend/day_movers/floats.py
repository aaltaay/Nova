"""A float limit on a past session: passed on evidence, else unknown (ADR 050 decision 6).

Operator: "proven, else unknown". Two kinds of evidence, never today's float:
- the float Nova knew that day -- its enrichment snapshot (``archive.db``, 2026-07-28 on): passes at or under
  the limit, fails over it;
- SEC shares outstanding (``sec_shares`` in the movers store): a float cannot exceed the shares outstanding, so a
  count at or under the limit passes. Only a count filed by that day and reported as of no more than
  ``DAY_MOVERS_SEC_SHARES_MAX_AGE_DAYS`` before it counts, put on the session's share basis through the splits
  listed in between. A count over the limit proves nothing (the float may still be under it): unknown. A ticker
  two companies used reads only the count of the one that held it that day (``ticker_holders``).
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
_NO_HOLDERS_LOGGED: list[bool] = []     # the missing-table warning is said once per process


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


def _holder_runs(db: sqlite3.Connection, symbols: list[str]) -> dict[str, list[tuple]] | None:
    """``symbol -> [(cik, held_from, held_to)]`` for the reused tickers among ``symbols``; None for a store exported
    before ``ticker_holders`` existed (no reused ticker can be told apart: logged)."""
    out: dict[str, list[tuple]] = {}
    try:
        for chunk in _chunks(sorted(set(symbols))):
            for symbol, cik, held_from, held_to in db.execute(
                    "SELECT symbol, cik, held_from, held_to FROM ticker_holders"
                    f" WHERE symbol IN ({', '.join('?' for _ in chunk)})", chunk):
                out.setdefault(symbol, []).append((cik, held_from, held_to))
    except sqlite3.OperationalError:
        if not _NO_HOLDERS_LOGGED:
            _NO_HOLDERS_LOGGED.append(True)
            logger.warning("day movers: no ticker_holders table -- a reused ticker may read its other company's "
                           "share count until research/movers/export_sec_shares.py runs again")
        return None
    return out


def _holder(runs: list[tuple], day: str) -> str | None:
    return next((cik for cik, start, end in runs if (start is None or start <= day) and (end is None or day <= end)),
                None)


def sec_shares(db: sqlite3.Connection, pairs: list[Pair], *, before: bool = False) -> dict[Pair, dict[str, Any]]:
    """The newest SEC share count usable on each (date, symbol): ``{shares, as_of, filed, age_days, cik}``.

    ``before``: only a count filed by the calendar day before the session -- what was on file at its open, never a
    filing made during it -- still put on the session's share basis, a split executing that day included.
    A reused ticker (``ticker_holders``) reads only the count of the company that held it that day; a day no company
    can be named for has no count (unknown, never another company's).
    """
    out: dict[Pair, dict[str, Any]] = {}
    holders = _holder_runs(db, [symbol for _day, symbol in pairs]) or {}
    for day, symbol in pairs:
        session = date.fromisoformat(day)
        known = (session - timedelta(days=1)).isoformat() if before else day
        oldest = (session - timedelta(days=DAY_MOVERS_SEC_SHARES_MAX_AGE_DAYS)).isoformat()
        where, args = "symbol = ? AND filed <= ? AND as_of <= ? AND as_of >= ?", [symbol, known, known, oldest]
        if symbol in holders:
            held = _holder(holders[symbol], day)
            if held is None:
                continue
            where, args = where + " AND cik = ?", [*args, held]
        try:
            row = db.execute(f"SELECT as_of, filed, shares, cik FROM sec_shares WHERE {where}"
                             " ORDER BY as_of DESC, filed DESC LIMIT 1", args).fetchone()
        except sqlite3.OperationalError:  # maintainer: allow-swallow a store with no counts: every float unknown
            return {}
        if row is None:
            continue
        as_of, filed, shares = row[0], row[1], float(row[2])
        shares *= _split_factor(db, symbol, as_of, day)
        out[(day, symbol)] = {"shares": round(shares), "as_of": as_of, "filed": filed,
                              "age_days": (session - date.fromisoformat(as_of)).days, "cik": row[3]}
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
