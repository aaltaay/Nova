"""Find stock-days for momentum research in one call (ADR 059): the movers index joined with what was known that day.

Each row is one stock-day of the day movers index (``scan.movers_scan``: percents in points, raw prior-close prices,
likely reverse splits left out by the capped search's own rule) with what was known that day -- shares, catalyst,
halts and relative volume, joined by ``day_facts`` (the one join every stock-day search uses; its docstring says what
each column means) -- and the marks: premarket high / volume, after-hours high / volume and the first ET minute each
+N% / -N% line printed.

``float_max`` filters SEC shares OUTSTANDING by default (``float_basis='sec_outstanding'``): outstanding is not free
float (insiders and locked-up shares are inside it), so a pass means "at most this many shares exist". Other bases:
``enrichment`` (the desk's own float that day) and ``best`` (enrichment when the desk had it, else outstanding).
A row with no value on the basis is unknown: ``float_unknown`` = exclude (default) | include | only.

News and volume filters: ``catalyst`` keeps verdicts, ``catalyst_category`` the verdict's category
(``fda_regulatory``, ``clinical_data`` ...), ``catalyst_words`` a headline containing any of the words (case is
ignored; a text match, not a judgment). ``rvol_daily_min`` keeps ``rvol_daily`` at or over the ratio (5 = 5x); a
stock-day with ``rvol_daily`` unknown is left out and counted in ``attrs['left_out']``, never read as low volume.
``halt_codes`` keeps a day with a halt of any code asked (``T1``, ``LUDP`` ...; ``news`` and ``luld`` name their
groups); ``halted`` true / false any halt. A day the halt log does not cover is unknown: left out.

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

from collections import Counter
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_reads import REPO, day_facts, rvol_days, scan  # noqa: F401  (REPO puts backend/ on sys.path)

ET = ZoneInfo("America/New_York")
PAGE_DEFAULT, PAGE_MAX, PAGE_MAX_FILE = 200, 5_000, 100_000
DEFAULT_KINDS = ["common"]          # as the movers search; a named symbol is its own filter: ["all"]
CHUNK = 2_000
MAX_EXAMINED = 200_000
FLOAT_BASES, FLOAT_UNKNOWN = day_facts.FLOAT_BASES, day_facts.FLOAT_UNKNOWN
MARKS = ("up10", "up20", "up50", "up100", "up300", "down10", "down20", "down50")
BASE = ("date", "symbol", "kind", "prev_close", "open", "high", "low", "close", "volume", "dollar_volume",
        "high_pct", "low_pct", "close_pct", "gap_pct", "day_high", "day_high_et", "day_low", "day_low_et",
        "pm_high", "pm_low", "pm_volume", "ah_high", "ah_volume", "split")
RVOL = day_facts.RVOL


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


def enrich(frame: pd.DataFrame, float_basis: str = "sec_outstanding") -> list[dict[str, Any]]:
    """Movers rows (``scan.movers_scan`` records) as find rows: the ET marks and every ``day_facts`` column."""
    rows = [_base_row(r) for r in frame.to_dict("records")]
    facts = day_facts.for_pairs([(r["date"], r["symbol"]) for r in rows], float_basis)
    for row in rows:
        row.update(facts[(row["date"], row["symbol"])])
    return rows


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
                    to_file: bool = False, catalyst_category: list[str] | None = None,
                    catalyst_words: list[str] | None = None, rvol_daily_min: float | None = None,
                    halt_codes: list[str] | None = None) -> pd.DataFrame:
    """One page of stock-days (see the module docstring); ``attrs`` has ``next_cursor``, ``examined`` and the rules.
    ``catalyst``: verdicts to keep (``unknown`` matches a day with none); ``halted``: only days with / without one.
    ``catalyst_category`` / ``catalyst_words`` / ``rvol_daily_min`` / ``halt_codes``: the news, volume and halt
    filters (module docstring).
    ``kinds``: types, ``["common"]`` (default) or ``["all"]``; ``sort``: a movers search sort, default oldest day."""
    filters = {k: v for k, v in (filters or {}).items() if v is not None}
    if not (symbol or filters.get("date_from") or filters.get("date_to")):
        raise ValueError("find_stock_days names date_from / date_to or a symbol (the movers store is 3.0M rows)")
    if float_basis not in FLOAT_BASES:
        raise ValueError(f"float_basis must be one of {', '.join(FLOAT_BASES)}")
    share_limit = _share_limit(float_max, outstanding_max, float_basis)
    page_size = _page_of(page_size, limit)
    wanted_kinds = [kinds] if isinstance(kinds, str) else list(kinds or (["all"] if symbol else DEFAULT_KINDS))
    ceiling = PAGE_MAX_FILE if to_file else PAGE_MAX
    if not 1 <= page_size <= ceiling:
        raise ValueError(f"page_size / limit must be 1-{ceiling:,}" + ("" if to_file else " (output_name allows more)"))
    rows_wanted = day_facts.wanted(float_max=share_limit, float_unknown=float_unknown, catalyst=catalyst,
                                   catalyst_category=catalyst_category, catalyst_words=catalyst_words,
                                   halted=halted, halt_codes=halt_codes, rvol_daily_min=rvol_daily_min)
    left_out: Counter[str] = Counter()
    step = min(CHUNK, max(200, int(page_size) * 2))
    after, page, examined, more, full = parse_cursor(cursor), [], 0, True, False
    while more and not full and examined < MAX_EXAMINED:
        chunk = scan.movers_scan(symbol=symbol, kinds=wanted_kinds, splits=splits, after=after, limit=step, sort=sort,
                                 **filters)
        examined += len(chunk)
        more = len(chunk) == step
        for row in enrich(chunk, float_basis):
            after = (row["date"], row["symbol"])
            if day_facts.keep(row, rows_wanted, left_out):
                page.append(row)
                if len(page) == page_size:
                    full = True
                    break
    next_cursor = f"{after[0]}|{after[1]}" if after and (full or more) else None
    frame = pd.DataFrame(page)
    frame.attrs.update(
        next_cursor=next_cursor, examined=examined, rows=len(page),
        filters={**filters, "kinds": _kinds_echo(wanted_kinds), "splits": splits, **day_facts.asked(rows_wanted),
                 "float_max": float_max, "outstanding_max": outstanding_max, "float_basis": float_basis,
                 "sort": sort or "oldest"},
        left_out=dict(left_out),
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
        catalyst_rule=day_facts.CATALYST_RULE, halt_rule=day_facts.HALT_RULE,
        rvol_rule=rvol_days.RULE,
    )
    if left_out.get("rvol_unknown"):
        frame.attrs["note_rvol"] = (f"{left_out['rvol_unknown']:,} stock-days examined had rvol_daily unknown and were "
                                    "left out by rvol_daily_min")
    if examined >= MAX_EXAMINED and len(page) < page_size:
        frame.attrs["note"] = f"examined {examined:,} movers rows: continue with next_cursor or narrow the filters"
    return frame
