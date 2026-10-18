"""Bulk reads of the day movers index for research (ADR 059): every stock-day that matches, no 500-row cap.

The agent endpoint (``reads.movers`` / ``/api/agent/movers``) answers at most 500 rows and refuses a search past
``AGENT_MOVERS_MAX_SCAN``; a study over ten years of small-cap runners needs all of them. This reads the store
(``backend/day_movers``, owner of the file) read-only, under one heavy-read slot.

Units -- the trap this exists to close: the store keeps ``high_pct`` / ``low_pct`` / ``close_pct`` / ``gap_pct`` as
fractions (0.10 = 10%). Every argument here is in percent points (``high_min=10`` is +10%) and every returned
``*_pct`` column is in percent points, like the endpoint. Prices filter the prior close (``prev_close``), raw
(never split-adjusted). ``*_ts`` columns are epoch seconds.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from market_reads import REPO, roots, slots  # noqa: F401  (REPO puts backend/ on sys.path)

PCT_COLUMNS = ("high_pct", "low_pct", "close_pct", "gap_pct")
# argument -> (column, operator, percent?)
FILTERS = {
    "price_min": ("prev_close", ">=", False), "price_max": ("prev_close", "<=", False),
    "high_min": ("high_pct", ">=", True), "high_max": ("high_pct", "<=", True),
    "low_min": ("low_pct", ">=", True), "low_max": ("low_pct", "<=", True),
    "close_min": ("close_pct", ">=", True), "close_max": ("close_pct", "<=", True),
    "gap_min": ("gap_pct", ">=", True), "gap_max": ("gap_pct", "<=", True),
    "volume_min": ("volume", ">=", False), "dollar_volume_min": ("dollar_volume", ">=", False),
    "date_from": ("session_date", ">=", False), "date_to": ("session_date", "<=", False),
}


def movers_scan(*, symbol: str | None = None, kinds: list[str] | None = None, columns: list[str] | None = None,
                limit: int | None = None, **filters) -> pd.DataFrame:
    """Every movers row matching ``filters`` (``FILTERS``' keys; percents in points), oldest day first."""
    unknown = set(filters) - set(FILTERS)
    if unknown:
        raise ValueError(f"unknown filter(s) {sorted(unknown)}; known: {sorted(FILTERS)}")
    where, args = [], []
    for key, value in filters.items():
        if value is None:
            continue
        column, op, pct = FILTERS[key]
        where.append(f"{column} {op} ?")
        if column == "session_date":
            args.append(str(value))
        else:
            args.append(float(value) / 100.0 if pct else float(value))
    if symbol:
        where.append("symbol = ?")
        args.append(symbol.strip().upper())
    if kinds:
        where.append(f"kind IN ({', '.join('?' for _ in kinds)})")
        args.extend(kinds)
    from day_movers.schema import MOVER_COLUMNS
    bad = [c for c in columns or [] if c not in MOVER_COLUMNS]
    if bad:
        raise ValueError(f"unknown column(s) {bad}; known: {', '.join(MOVER_COLUMNS)}")
    path = roots.movers_db()
    if not path.is_file():
        raise LookupError(f"no day movers index at {path} (research/movers/build_movers.py builds it)")
    select = ", ".join(columns) if columns else "*"
    sql = (f"SELECT {select} FROM movers" + (f" WHERE {' AND '.join(where)}" if where else "")
           + " ORDER BY session_date, symbol" + (f" LIMIT {int(limit)}" if limit else ""))
    with slots.heavy("movers scan"):
        db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=30.0)
        try:
            frame = pd.read_sql_query(sql, db, params=args)
        finally:
            db.close()
    for column in PCT_COLUMNS:
        if column in frame:
            frame[column] = frame[column] * 100.0
    frame.attrs.update(rows=len(frame), filters={k: v for k, v in filters.items() if v is not None},
                       units="*_pct in percent points; prices raw prior-close dollars; *_ts epoch seconds")
    return frame
