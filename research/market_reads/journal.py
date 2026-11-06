"""The operator's own trades through the front door (ADR 059): the desk's journal, read-only.

``journal.db`` ``trades`` in the desk's cache (``roots.cache_store``: ``NOVA_CACHE_DIR``, else the main checkout's
``backend/.cache``, then ``F:\\Nova\\cache``), filtered by ``backend/journal/store.get_trades`` -- the rule
``GET /api/journal/trades`` uses -- on a read-only connection: the journal is never created, migrated or written. A
journal that is not on disk is a ``LookupError`` naming where it looked, never an empty list. Mock rows (``is_mock``,
test data) are left out unless asked.

The journal is not where the desk's fills land: the Account page reads the practice account's history
(``GET /api/practice/history``, Paper and Sim) and IBKR's closed orders. ``attrs['journal_rows']`` counts the real and
mock rows in the file, so an empty answer says whether the journal holds anything at all.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_reads import REPO, roots  # noqa: F401  (REPO puts backend/ on sys.path)

ET = ZoneInfo("America/New_York")
LIMIT_DEFAULT, LIMIT_MAX = 200, 10_000
COLUMNS = ["id", "opened_et", "closed_et", "symbol", "setup", "side", "qty", "entry_price", "exit_price", "stop_price",
           "target_price", "pnl", "commission", "adherent", "tags", "notes", "is_mock", "opened_ts", "closed_ts"]
RULE = ("newest trade first by the time it opened; symbol and setup match exactly (any case), tag is one of the "
        "trade's tags, adherent the plan flag (a trade with none matches neither), date_from / date_to the ET day the "
        "trade opened (inclusive) -- backend/journal/store.get_trades, the desk's own rule")


def _et(ts: Any) -> str | None:
    return None if ts is None else datetime.fromtimestamp(float(ts), ET).strftime("%Y-%m-%d %H:%M:%S")


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [r for r in rows if r.get("pnl") is not None]
    fees = [r["commission"] for r in rows if r.get("commission") is not None]
    return {"trades": len(rows), "closed": len(closed),
            "pnl": round(sum(r["pnl"] for r in closed), 2) if closed else None,
            "wins": sum(r["pnl"] > 0 for r in closed), "losses": sum(r["pnl"] < 0 for r in closed),
            "commission": round(sum(fees), 2) if fees else None}


def _row_counts(path) -> dict[str, int]:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
        total, mock = db.execute("SELECT count(*), coalesce(sum(is_mock), 0) FROM trades").fetchone()
    return {"real": int(total) - int(mock), "mock": int(mock)}


def trades(symbol: str | None = None, setup: str | None = None, tag: str | None = None,
           adherent: bool | None = None, date_from: str | None = None, date_to: str | None = None,
           limit: int | None = None, include_mock: bool = False) -> pd.DataFrame:
    """The newest ``limit`` journal trades matching every filter given (``RULE``), with ``opened_et`` / ``closed_et``;
    ``attrs`` hold the filters, the file read and a ``summary`` of the rows returned (``pnl`` the sum of the closed)."""
    from constants import JOURNAL_DB_FILENAME
    from journal import store
    limit = LIMIT_DEFAULT if limit is None else int(limit)
    if not 1 <= limit <= LIMIT_MAX:
        raise ValueError(f"limit must be 1-{LIMIT_MAX:,}")
    path = roots.cache_store(JOURNAL_DB_FILENAME)
    rows = store.get_trades(limit, include_mock, symbol=symbol, setup=setup, tag=tag, adherent=adherent,
                            date_from=date_from, date_to=date_to, database=path)
    for row in rows:
        row.update(opened_et=_et(row.get("opened_ts")), closed_et=_et(row.get("closed_ts")),
                   tags=", ".join(str(t) for t in row.get("tags") or []) or None,
                   adherent=None if row.get("adherent") is None else bool(row["adherent"]),
                   is_mock=bool(row.get("is_mock")))
    frame = pd.DataFrame(rows, columns=COLUMNS)
    asked = {k: v for k, v in (("symbol", symbol), ("setup", setup), ("tag", tag), ("adherent", adherent),
                               ("date_from", date_from), ("date_to", date_to)) if v is not None}
    frame.attrs.update(source=str(path), rule=RULE, filters=asked, limit=limit, includes_mock_data=include_mock,
                       summary=_summary(rows), journal_rows=_row_counts(path),
                       units="prices and pnl dollars; *_et ET; *_ts epoch seconds",
                       not_here="the desk's fills: the Account page reads GET /api/practice/history (Paper, Sim) "
                                "and IBKR's closed orders, not this journal")
    return frame
