"""Bulk reads of the day movers index for research (ADR 059): every stock-day that matches, past the 500-row cap.

The agent endpoint (``reads.movers`` / ``/api/agent/movers``) answers at most 500 rows and refuses a search past
``AGENT_MOVERS_MAX_SCAN``; a study over ten years of small-cap runners needs all of them. This reads the store
(``backend/day_movers``, owner of the file) read-only, under one heavy-read slot.

Units -- the trap this exists to close: the store keeps ``high_pct`` / ``low_pct`` / ``close_pct`` / ``gap_pct`` as
fractions (0.10 = 10%). Every argument here is in percent points (``high_min=10`` is +10%) and every returned
``*_pct`` column is in percent points, like the endpoint. Prices filter the prior close (``prev_close``), raw
(never split-adjusted). ``*_ts`` columns are epoch seconds.

Same rules as the capped search, never a fork of them: likely reverse splits are left out by default
(``day_movers.query.splits_sql``: ``exclude_likely`` | ``include`` | ``only_suspects``), percent lines are widened
by the same tolerance (``query.pct_bound``), and every row says ``split`` (``query.split_label``).

Guard (the store is 3.0M rows and the desk reads the same drive): a scan names a date range, a symbol or a
``limit``; without a ``limit`` at most ``ROW_CAP`` rows come back and ``attrs['capped']`` says when more matched.

Order: oldest day first, then symbol -- or ``sort=`` one of the capped search's choices (``day_movers.query.SORTS``;
a row without the figure last, ties newest day first, then symbol). ``after`` = ``(date, symbol)`` continues strictly
past that row in the same order, so ordered pages add up to the whole answer.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from market_reads import REPO, roots, slots  # noqa: F401  (REPO puts backend/ on sys.path)

PCT_COLUMNS = ("high_pct", "low_pct", "close_pct", "gap_pct")
ROW_CAP = 100_000          # rows a scan without a limit returns
LIMIT_MAX = 1_000_000      # the most a limit may ask for (the whole small-cap runner universe is ~375k rows)
KIND_WORDS = ("common", "all")
SPLIT_LABEL_COLUMNS = ("split_listed", "split_suspect", "prev_volume", "volume")
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
BROAD = ("a scan names date_from / date_to, a symbol or a limit (the movers store is 3.0M rows and the desk reads "
         "the same drive)")


def _kinds_clause(kinds: list[str] | str | None) -> tuple[str, list]:
    """The capped search's kind rule (``day_movers.query``): ``None`` = every kind; ``["common"]`` / ``["all"]`` the
    words it knows; else the listed types, case-insensitive. A word stands alone."""
    items = [part.strip() for k in ([kinds] if isinstance(kinds, str) else kinds or []) for part in str(k).split(",")
             if part.strip()]
    if not items:
        return "", []
    from day_movers import query
    words = [k.lower() for k in items if k.lower() in KIND_WORDS]
    if words and len(items) > 1:
        raise ValueError(f"kinds: {words[0]!r} stands alone (a list of types, or one of {', '.join(KIND_WORDS)})")
    try:
        return query._kinds_sql(words[0] if words else ",".join(items))
    except query.QueryError as exc:
        raise ValueError(str(exc)) from None


def _order(sort: str | None) -> tuple[str, str | None, bool]:
    """``(ORDER BY, sort column, descending)``: the capped search's ``sort_rows`` as SQL. A day sort has no column."""
    from day_movers.query import SORTS
    if sort is None:
        sort = "oldest"
    if sort not in SORTS:
        raise ValueError(f"sort must be one of {', '.join(SORTS)}")
    column, descending = SORTS[sort]
    if column == "session_date":
        return f"session_date {'DESC' if descending else 'ASC'}, symbol", None, descending
    return (f"({column} IS NULL), {column} {'DESC' if descending else 'ASC'}, session_date DESC, symbol", column,
            descending)


def _after(db: sqlite3.Connection, column: str | None, descending: bool, after: tuple[str, str]) -> tuple[str, list]:
    """The rows strictly past ``after`` in ``_order``'s order. A figure sort reads the cursor row's figure (the pair is
    the primary key), so a cursor outside the store is refused rather than guessed."""
    day, symbol = after
    if column is None:
        return (f"(session_date {'<' if descending else '>'} ? OR (session_date = ? AND symbol > ?))",
                [day, day, symbol])
    row = db.execute(f"SELECT {column} FROM movers WHERE session_date = ? AND symbol = ?", (day, symbol)).fetchone()
    if row is None:
        raise ValueError(f"cursor {day}|{symbol} is not a row of the movers index")
    tie = "(session_date < ? OR (session_date = ? AND symbol > ?))"
    if row[0] is None:
        return f"({column} IS NULL AND {tie})", [day, day, symbol]
    op = "<" if descending else ">"
    return (f"(({column} IS NOT NULL AND ({column} {op} ? OR ({column} = ? AND {tie}))) OR {column} IS NULL)",
            [row[0], row[0], day, day, symbol])


def _where(symbol: str | None, kinds: list[str] | str | None, splits: str, filters: dict) -> tuple[list[str], list]:
    from day_movers import query
    where, args = [], []
    for key, value in filters.items():
        if value is None:
            continue
        column, op, pct = FILTERS[key]
        where.append(f"{column} {op} ?")
        if column == "session_date":
            args.append(str(value))
        else:
            args.append(query.pct_bound(float(value), op) if pct else float(value))
    if symbol:
        where.append("symbol = ?")
        args.append(symbol.strip().upper())
    clause, kind_args = _kinds_clause(kinds)
    if clause:
        where.append(clause)
        args.extend(kind_args)
    try:
        split = query.splits_sql(splits)
    except query.QueryError as exc:
        raise ValueError(str(exc)) from None
    if split:
        where.append(split)
    return where, args


def movers_scan(*, symbol: str | None = None, kinds: list[str] | str | None = None, columns: list[str] | None = None,
                limit: int | None = None, splits: str = "exclude_likely", after: tuple[str, str] | None = None,
                sort: str | None = None, **filters) -> pd.DataFrame:
    """Every movers row matching ``filters`` (``FILTERS``' keys; percents in points), oldest day first or by ``sort``;
    ``after`` = ``(date, symbol)`` starts past that row in that order (a page's cursor). ``kinds``: types, or
    ``["common"]`` / ``["all"]``; omitted, every kind."""
    unknown = set(filters) - set(FILTERS)
    if unknown:
        raise ValueError(f"unknown filter(s) {sorted(unknown)}; known: {sorted(FILTERS)}")
    if limit is not None and not 1 <= int(limit) <= LIMIT_MAX:
        raise ValueError(f"limit must be 1-{LIMIT_MAX:,}")
    if not (symbol or limit or filters.get("date_from") or filters.get("date_to")):
        raise ValueError(BROAD)
    from day_movers import query
    from day_movers.schema import MOVER_COLUMNS
    bad = [c for c in columns or [] if c not in MOVER_COLUMNS]
    if bad:
        raise ValueError(f"unknown column(s) {bad}; known: {', '.join(MOVER_COLUMNS)}")
    where, args = _where(symbol, kinds, splits, filters)
    order, sort_column, descending = _order(sort)
    path = roots.movers_db()
    if not path.is_file():
        raise LookupError(f"no day movers index at {path} (research/movers/build_movers.py builds it)")
    select = list(columns) if columns else list(MOVER_COLUMNS)
    labelled = all(c in select for c in SPLIT_LABEL_COLUMNS)
    take = int(limit) if limit else ROW_CAP + 1
    with slots.heavy("movers scan"):
        db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=30.0)
        try:
            if after:
                clause, past = _after(db, sort_column, descending, after)
                where, args = [*where, clause], [*args, *past]
            sql = (f"SELECT {', '.join(select)} FROM movers" + (f" WHERE {' AND '.join(where)}" if where else "")
                   + f" ORDER BY {order} LIMIT {take}")
            frame = pd.read_sql_query(sql, db, params=args)
        finally:
            db.close()
    capped = not limit and len(frame) > ROW_CAP
    if capped:
        frame = frame.head(ROW_CAP)
    if labelled:
        labels = [query.split_label(r) for r in frame[list(SPLIT_LABEL_COLUMNS)].to_dict("records")]
        frame["split"] = pd.Series(labels, index=frame.index, dtype=object)
    for column in PCT_COLUMNS:
        if column in frame:
            frame[column] = frame[column] * 100.0
    asked = {k: v for k, v in filters.items() if v is not None}
    frame.attrs.update(rows=len(frame), filters={**asked, "splits": splits, **({"sort": sort} if sort else {})},
                       capped=bool(capped),
                       units="*_pct in percent points; prices raw prior-close dollars; *_ts epoch seconds",
                       split_rule="day_movers.query: likely_split = split_suspect and volume <= prev_volume x "
                                  "DAY_MOVERS_LIKELY_SPLIT_MAX_VOLUME_RATIO; splits=include keeps them")
    if capped:
        frame.attrs["note"] = (f"more than {ROW_CAP:,} rows matched: the first {ROW_CAP:,} in the {sort or 'day'} order came back; narrow "
                               f"the dates or pass limit= (at most {LIMIT_MAX:,}) with an output file")
    return frame
