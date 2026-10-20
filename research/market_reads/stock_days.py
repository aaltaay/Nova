"""Find stock-days for momentum research in one call (ADR 059): the movers index joined with what was known that day.

Each row is one stock-day of the day movers index (``scan.movers_scan``: percents in points, raw prior-close prices,
likely reverse splits left out by the capped search's own rule) with:
  shares    ``outstanding_*``: SEC shares outstanding filed by the day, reported as of at most
            ``DAY_MOVERS_SEC_SHARES_MAX_AGE_DAYS`` (120) before it and put on the day's share basis -- the movers
            store's ``sec_shares`` table, read by ``day_movers.floats`` (the endpoint's own rules). A reused ticker's
            count is dropped when its CIK is not the company that held the ticker that day (``tickers.py``).
            ``enrichment_float``: the float the desk's enrichment snapshot held that day (``archive.db``,
            2026-07-28 on). ``float_shares`` / ``float_source`` is the value ``float_max`` filtered on.
  catalyst  the catalyst backfill's verdict for the day (``catalysts.for_pairs``); null is unknown, never no news.
  halts     the day's halts (``halts.for_pairs``): count, first halt ET, codes, LULD pauses; null on a day the halt
            log does not cover (before 2021-09-21), never 0.
  marks     premarket high / volume, after-hours high / volume and the first ET minute each +N% / -N% line printed.

``float_max`` filters SEC shares OUTSTANDING by default (``float_basis='sec_outstanding'``): outstanding is not free
float (insiders and locked-up shares are inside it), so a pass means "at most this many shares exist". Other bases:
``enrichment`` (the desk's own float that day) and ``best`` (enrichment when the desk had it, else outstanding).
A row with no value on the basis is unknown: ``float_unknown`` = exclude (default) | include | only.

``outstanding_max`` is ``float_max`` under the name of what it filters (SEC shares outstanding): it needs the
``sec_outstanding`` basis and is refused beside ``float_max``.

Kinds: common stock (``CS``, ``ADRC``) unless ``kinds`` says otherwise -- the capped search's own default, so warrants,
rights, units and ETFs are not in the rows unless asked for (``kinds=["all"]`` keeps every kind). A call that names a
``symbol`` and no ``kinds`` keeps every kind: the ticker is the filter (the desk's own symbol lookup does the same).

Pages: rows come oldest day first, then by symbol, or ranked by ``sort`` (the capped search's choices, ``SORTS``): the
movers store orders them, then each chunk is enriched and filtered in that order, so the float / catalyst / halt filters
pick from the ranking. ``limit`` is ``page_size`` under the capped search's name. ``next_cursor``
(``"YYYY-MM-DD|SYMBOL"``) continues strictly past the last row examined in the same order; None when every row was
read. One call examines at most ``MAX_EXAMINED`` movers rows.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_reads import REPO, scan, tickers  # noqa: F401  (REPO puts backend/ on sys.path)

ET = ZoneInfo("America/New_York")
PAGE_DEFAULT, PAGE_MAX, PAGE_MAX_FILE = 200, 5_000, 100_000
DEFAULT_KINDS = ["common"]          # as the movers search; a named symbol is its own filter: ["all"]
CHUNK = 2_000
MAX_EXAMINED = 200_000
FLOAT_BASES = ("sec_outstanding", "enrichment", "best")
FLOAT_UNKNOWN = ("exclude", "include", "only")
MARKS = ("up10", "up20", "up50", "up100", "up300", "down10", "down20", "down50")
BASE = ("date", "symbol", "kind", "prev_close", "open", "high", "low", "close", "volume", "dollar_volume",
        "high_pct", "low_pct", "close_pct", "gap_pct", "day_high", "day_high_et", "day_low", "day_low_et",
        "pm_high", "pm_low", "pm_volume", "ah_high", "ah_volume", "split")


def _et(ts: Any) -> str | None:
    if ts is None or pd.isna(ts):
        return None
    return datetime.fromtimestamp(int(ts), ET).strftime("%H:%M")


def cursor_of(row: dict[str, Any]) -> str:
    return f"{row['date']}|{row['symbol']}"


def parse_cursor(cursor: str | None) -> tuple[str, str] | None:
    if not cursor:
        return None
    day, _, symbol = str(cursor).partition("|")
    if len(day) != 10 or not symbol:
        raise ValueError("cursor is the next_cursor a previous page returned (YYYY-MM-DD|SYMBOL)")
    return day, symbol.upper()


def _value(raw: Any) -> Any:
    return None if raw is None or (isinstance(raw, float) and pd.isna(raw)) else raw


def _base_row(r: dict[str, Any]) -> dict[str, Any]:
    out = {"date": r["session_date"], "symbol": r["symbol"]}
    for key in BASE[2:]:
        if key in ("day_high_et", "day_low_et"):
            out[key] = _et(r.get(key.replace("_et", "_ts")))
        else:
            out[key] = _value(r.get(key))
    for mark in MARKS:
        out[f"{mark}_et"] = _et(r.get(f"{mark}_ts"))
    return out


def _outstanding(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    """The endpoint's SEC count per pair (``day_movers.floats.sec_shares``), minus a reused ticker's other company."""
    from day_movers import floats, store
    db = store.read_only()
    if db is None:
        return {}
    try:
        counts = floats.sec_shares(db, pairs)
        reused = {s for s, rows in tickers.listings().items()
                  if len({tickers._cik(r.get("cik")) for r in rows if r.get("cik")}) > 1}
        for (day, symbol), count in list(counts.items()):
            if symbol not in reused:
                continue
            row = db.execute("SELECT cik FROM sec_shares WHERE symbol = ? AND as_of = ? AND filed = ?",
                             (symbol, count["as_of"], count["filed"])).fetchone()
            held = tickers.resolve(symbol, day)["cik"]
            if not row or not held or tickers._cik(row[0]) != held:
                counts.pop((day, symbol))
    finally:
        db.close()
    return counts


def enrich(frame: pd.DataFrame, float_basis: str = "sec_outstanding") -> list[dict[str, Any]]:
    """Movers rows (``scan.movers_scan`` records) as find rows: shares, catalyst, halts, ET marks."""
    from day_movers import floats

    from market_reads import catalysts, halts
    rows = [_base_row(r) for r in frame.to_dict("records")]
    pairs = [(r["date"], r["symbol"]) for r in rows]
    if not pairs:
        return []
    snapshots = floats.enrichment_floats(pairs)
    sec = _outstanding(pairs)
    verdicts = catalysts.for_pairs(pairs)
    stops = halts.for_pairs(pairs)
    for row, pair in zip(rows, pairs, strict=True):
        count = sec.get(pair) or {}
        row.update(outstanding_shares=count.get("shares"), outstanding_as_of=count.get("as_of"),
                   outstanding_filed=count.get("filed"), outstanding_age_days=count.get("age_days"),
                   enrichment_float=round(snapshots[pair]) if pair in snapshots else None)
        use_snapshot = float_basis == "enrichment" or (float_basis == "best" and pair in snapshots)
        if use_snapshot:
            row["float_shares"] = row["enrichment_float"]
            row["float_source"] = "enrichment_snapshot" if pair in snapshots else None
        else:
            row["float_shares"] = row["outstanding_shares"]
            row["float_source"] = "sec_shares_outstanding" if count else None
        verdict = verdicts.get(pair) or {}
        row.update(catalyst_verdict=verdict.get("verdict"), catalyst_category=verdict.get("category"),
                   catalyst_strength=verdict.get("strength"), catalyst_title=verdict.get("title"),
                   catalyst_cutoff=verdict.get("cutoff_kind"))
        stop = stops.get(pair) or {}
        row.update(halts=stop.get("halts"), first_halt_et=stop.get("first_halt_et"),
                   halt_codes=",".join(stop.get("codes") or []) or None, luld_halts=stop.get("luld"))
    return rows


def _keep(row: dict[str, Any], float_max: float | None, float_unknown: str, catalyst: set[str] | None,
          halted: bool | None) -> bool:
    if float_max is not None:
        shares = row["float_shares"]
        if shares is None:
            if float_unknown == "exclude":
                return False
        elif float_unknown == "only" or shares > float_max:
            return False
    elif float_unknown == "only" and row["float_shares"] is not None:
        return False
    if catalyst is not None and (row["catalyst_verdict"] or "unknown") not in catalyst:
        return False
    if halted is None:
        return True
    return row["halts"] is not None and (row["halts"] > 0) == halted     # an uncovered day is unknown: left out


def _kinds_echo(kinds: list[str]) -> str | list[str]:
    return kinds[0].lower() if len(kinds) == 1 and kinds[0].lower() in scan.KIND_WORDS else [k.upper() for k in kinds]


def _share_limit(float_max: float | None, outstanding_max: float | None, float_basis: str) -> float | None:
    """The one limit on shares: ``float_max`` (on ``float_basis``) or ``outstanding_max`` (SEC shares outstanding)."""
    if outstanding_max is None:
        return float_max
    if float_max is not None:
        raise ValueError("pass float_max or outstanding_max, not both: they are one limit on shares outstanding")
    if float_basis != "sec_outstanding":
        raise ValueError("outstanding_max limits SEC shares outstanding, so float_basis must be sec_outstanding "
                         f"(not {float_basis!r}); use float_max for the other bases")
    return outstanding_max


def _page_of(page_size: int | None, limit: int | None) -> int:
    if page_size is not None and limit is not None and int(page_size) != int(limit):
        raise ValueError("limit is page_size under the movers search's name: pass one, or the same number")
    return int(limit if limit is not None else PAGE_DEFAULT if page_size is None else page_size)


def find_stock_days(*, filters: dict[str, Any] | None = None, symbol: str | None = None,
                    kinds: list[str] | str | None = None, splits: str = "exclude_likely",
                    float_max: float | None = None, outstanding_max: float | None = None,
                    float_basis: str = "sec_outstanding", float_unknown: str = "exclude",
                    catalyst: list[str] | None = None, halted: bool | None = None, sort: str | None = None,
                    limit: int | None = None, cursor: str | None = None, page_size: int | None = None,
                    to_file: bool = False) -> pd.DataFrame:
    """One page of stock-days (see the module docstring); ``attrs`` has ``next_cursor``, ``examined`` and the rules.
    ``catalyst``: verdicts to keep (``unknown`` matches a day with none); ``halted``: only days with / without one.
    ``kinds``: types, ``["common"]`` (default) or ``["all"]``; ``sort``: a movers search sort, default oldest day."""
    filters = {k: v for k, v in (filters or {}).items() if v is not None}
    if not (symbol or filters.get("date_from") or filters.get("date_to")):
        raise ValueError("find_stock_days names date_from / date_to or a symbol (the movers store is 3.0M rows)")
    if float_basis not in FLOAT_BASES:
        raise ValueError(f"float_basis must be one of {', '.join(FLOAT_BASES)}")
    if float_unknown not in FLOAT_UNKNOWN:
        raise ValueError(f"float_unknown must be one of {', '.join(FLOAT_UNKNOWN)}")
    share_limit = _share_limit(float_max, outstanding_max, float_basis)
    page_size = _page_of(page_size, limit)
    wanted_kinds = [kinds] if isinstance(kinds, str) else list(kinds or (["all"] if symbol else DEFAULT_KINDS))
    ceiling = PAGE_MAX_FILE if to_file else PAGE_MAX
    if not 1 <= page_size <= ceiling:
        raise ValueError(f"page_size / limit must be 1-{ceiling:,}" + ("" if to_file else " (output_name allows more)"))
    wanted = {c.lower() for c in catalyst} if catalyst else None
    step = min(CHUNK, max(200, int(page_size) * 2))
    after, page, examined, more, full = parse_cursor(cursor), [], 0, True, False
    while more and not full and examined < MAX_EXAMINED:
        chunk = scan.movers_scan(symbol=symbol, kinds=wanted_kinds, splits=splits, after=after, limit=step, sort=sort,
                                 **filters)
        examined += len(chunk)
        more = len(chunk) == step
        for row in enrich(chunk, float_basis):
            after = (row["date"], row["symbol"])
            if _keep(row, share_limit, float_unknown, wanted, halted):
                page.append(row)
                if len(page) == page_size:
                    full = True
                    break
    next_cursor = f"{after[0]}|{after[1]}" if after and (full or more) else None
    frame = pd.DataFrame(page)
    frame.attrs.update(
        next_cursor=next_cursor, examined=examined, rows=len(page),
        filters={**filters, "kinds": _kinds_echo(wanted_kinds), "splits": splits, "float_max": float_max,
                 "outstanding_max": outstanding_max, "float_basis": float_basis, "float_unknown": float_unknown,
                 "catalyst": sorted(wanted) if wanted else None, "halted": halted, "sort": sort or "oldest"},
        order_rule=("oldest day first, then symbol" if sort in (None, "oldest") else
                    f"sort={sort}: the movers search's order (a row without the figure last; ties newest day first, "
                    "then symbol); float / catalyst / halt filters pick from this ranking"),
        kinds_rule=("common stock (CS, ADRC) as the movers search: pass kinds=['all'] for warrants, rights, units, ETFs"
                    if wanted_kinds == DEFAULT_KINDS else "every kind (a named symbol is not filtered by kind)"
                    if wanted_kinds == ["all"] and not kinds else "the kinds asked for"),
        units="*_pct percent points; prices raw prior-close dollars (never split-adjusted); *_et ET HH:MM",
        float_rule=("float_shares is the float_basis value: sec_outstanding = SEC shares outstanding filed by the day "
                    "(as of <= 120 days before it, split-adjusted to the day) -- not free float; enrichment = the "
                    "desk's own float that day (2026-07-28 on); best = enrichment, else outstanding"),
        catalyst_rule="the catalyst backfill's verdict for the day; null = unknown (not covered), never no news",
    )
    if examined >= MAX_EXAMINED and len(page) < page_size:
        frame.attrs["note"] = f"examined {examined:,} movers rows: continue with next_cursor or narrow the filters"
    return frame
