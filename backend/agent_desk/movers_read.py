"""The agent endpoints' reads of the day movers index (ADR 050): search, one stock-day, how far it reaches.

Blocking (SQLite and a folder walk) -- the routes run these off the event loop. The index is opened read-only for
each read: the builder may be writing it (WAL), and a read never creates or migrates it.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any

from day_movers import floats, query, store
from day_movers.schema import MOVER_COLUMNS, UnknownDayMoversSchema

logger = logging.getLogger(__name__)

NOT_BUILT = "the movers index is not built yet: py -3 research/movers/build_movers.py"


class IndexUnavailable(RuntimeError):
    """The index cannot be read; the message says why and what builds it."""


def _open() -> sqlite3.Connection:
    try:
        db = store.read_only()
    except (UnknownDayMoversSchema, sqlite3.Error) as exc:
        raise IndexUnavailable(f"the movers index at {store.path()} cannot be read: {exc}") from exc
    if db is None:
        raise IndexUnavailable(NOT_BUILT)
    return db


def massive_days() -> dict[str, dict[str, bool]] | None:
    """``{date: {trades, quotes, minute_aggs}}`` on disk, or ``None`` when the folder cannot be read."""
    from sim import massive_days as days

    listing = days.listing()
    if not listing.get("available"):
        return None
    return {row["date"]: row for row in listing["days"]}


def replayable_days() -> set[str] | None:
    on_disk = massive_days()
    return None if on_disk is None else {day for day, have in on_disk.items() if have.get("trades")}


def search(params: dict[str, Any]) -> dict[str, Any]:
    q = query.parse(params)
    db = _open()
    try:
        answer = query.search(
            db, q, replayable=replayable_days(),
            floats=lambda pairs, limit: floats.proofs(pairs, limit, db=db),
        )
    finally:
        db.close()
    answer["schema_version"] = 1
    answer["coverage"] = index_status()
    if q.float_max is not None and any((r.get("float") or {}).get("source") == "sec_shares_outstanding"
                                       for r in answer["rows"]):
        answer["notes"].append("a float passed on SEC shares outstanding is the count as of its date: shares "
                               "issued after it (an offering, warrants) are not in it")
    return answer


def row(day: str, symbol: str) -> dict[str, Any] | None:
    """One stock-day's raw index row (the planner's anchors), or ``None`` when it is not in the index."""
    db = _open()
    try:
        found = db.execute(
            f"SELECT {', '.join(MOVER_COLUMNS)} FROM movers WHERE session_date = ? AND symbol = ?",
            (day, symbol.upper()),
        ).fetchone()
    finally:
        db.close()
    return None if found is None else dict(zip(MOVER_COLUMNS, tuple(found), strict=True))


def row_or_none(day: str, symbol: str) -> dict[str, Any] | None:
    """``row``, with an unreadable index read as "not in the index" (a time-named show still works)."""
    try:
        return row(day, symbol)
    except IndexUnavailable:
        return None


def index_status() -> dict[str, Any]:
    """``{ok, error, path, sessions, first, last, files_last, behind, missing, rows}``.

    ``behind``: minute-file days newer than the newest session built; ``missing``: minute-file days not built at
    all (the builder works newest first, so a first build fills in backwards). Both null when the folder cannot
    be listed -- never "nothing missing".
    """
    out: dict[str, Any] = {"ok": False, "error": None, "path": str(store.path()), "sessions": 0, "first": None,
                           "last": None, "files_last": None, "behind": None, "missing": None, "rows": 0}
    try:
        db = _open()
    except IndexUnavailable as exc:
        out["error"] = str(exc)
        return out
    try:
        built = {r[0]: int(r[1]) for r in db.execute("SELECT session_date, rows FROM sessions")}
    except sqlite3.Error as exc:
        out["error"] = f"the movers index cannot be read: {exc}"
        return out
    finally:
        db.close()
    last = max(built) if built else None
    out.update(ok=True, sessions=len(built), first=min(built) if built else None, last=last,
               rows=sum(built.values()))
    try:
        on_disk = massive_days()
    except Exception as exc:  # the folder walk failing is stated, never "nothing behind"
        logger.warning("agent desk: the Massive days listing failed: %s", exc)
        on_disk = None
    if on_disk is not None:
        minute_days = sorted(day for day, have in on_disk.items() if have.get("minute_aggs"))
        out["files_last"] = minute_days[-1] if minute_days else None
        out["behind"] = sum(1 for day in minute_days if last is None or day > last)
        out["missing"] = sum(1 for day in minute_days if day not in built)
    return out
