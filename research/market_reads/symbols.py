"""Symbol search through the front door (ADR 059): Massive's ticker list, by ticker or company name, and everything
it knows about one ticker -- every company that used it, which one held it on a day, and each company's other
tickers (a rename, a share class, a warrant).

The list is ``<NOVA_MARKET_DATA_DIR>/store/reference/tickers.json``, read and cached by ``tickers.py`` (never here):
Massive's dump as of its ``last_updated_utc``, active and delisted tickers alike. It is the LATEST dump only: a row
is a ticker's last state, not its history. A ticker gives at most two companies (today's holder and a former one
with ``delisted_utc``); which held it on a day is ``tickers.resolve``'s rule (former holder until its delisting
day; today's holder from its Massive ticker-details ``list_date``, else the day after the former left).
A CIK's other tickers are the rows of the same list naming that CIK: only tickers Massive still lists.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from market_reads import roots, tickers

COLUMNS = ["ticker", "name", "cik", "active", "delisted", "type", "exchange", "composite_figi", "ticker_reused"]
RULE = ("Massive's latest ticker list; a ticker's holder on a day by tickers.resolve (former holder until its "
        "delisting day, today's holder from its list_date)")
COVERAGE = "every ticker in Massive's dump, active and delisted, as of the dump's last_updated_utc (latest only)"
_cache: tuple[Any, dict[str, list[dict[str, Any]]], str | None] | None = None


def _path():
    return roots.reference() / "tickers.json"


def _cik(value: Any) -> str | None:
    return str(value or "").strip().lstrip("0") or None


def _row(row: dict[str, Any], reused: bool) -> dict[str, Any]:
    return {"ticker": str(row.get("ticker") or "").upper(), "name": row.get("name"), "cik": _cik(row.get("cik")),
            "active": bool(row.get("active")), "delisted": (row.get("delisted_utc") or "")[:10] or None,
            "type": row.get("type"), "exchange": row.get("primary_exchange"),
            "composite_figi": row.get("composite_figi"), "ticker_reused": reused}


def _reused(rows: list[dict[str, Any]]) -> bool:
    return len({_cik(r.get("cik")) for r in rows if _cik(r.get("cik"))}) > 1


def _as_of(rows) -> str | None:
    stamps = [str(r.get("last_updated_utc")) for r in rows if r.get("last_updated_utc")]
    return max(stamps) if stamps else None


def _built() -> tuple[Any, dict[str, list[dict[str, Any]]], str | None]:
    """Every listing row by CIK and the dump's newest ``last_updated_utc``, rebuilt when ``tickers`` reloads."""
    global _cache
    listed = tickers.listings()
    if _cache is None or _cache[0] is not listed:
        index: dict[str, list[dict[str, Any]]] = {}
        for rows in listed.values():
            for row in rows:
                if cik := _cik(row.get("cik")):
                    index.setdefault(cik, []).append(row)
        _cache = (listed, index, _as_of(r for rows in listed.values() for r in rows))
    return _cache


def _cik_index() -> dict[str, list[dict[str, Any]]]:
    return _built()[1]


def dump_as_of() -> str | None:
    """The newest ``last_updated_utc`` in the list: when Massive's dump was taken, at the latest."""
    return _built()[2]


def search(query: str | None = None, *, ticker: str | None = None, active: bool | None = None,
           types: list[str] | None = None, exchange: str | None = None, cik: str | None = None,
           limit: int = 50) -> pd.DataFrame:
    """Listing rows (``COLUMNS``) whose ticker starts with ``query`` or whose name contains it (any case), narrowed
    by ``ticker`` (exact), ``active``, ``types`` (Massive's: CS, ADRC, PFD, WARRANT, ETF ...), ``exchange``
    (``primary_exchange``, e.g. XNAS) and ``cik``. Ranked: exact ticker, then ticker prefix, then name matches;
    within each, active before delisted, then shortest ticker. A reused ticker has a row per company."""
    if not any(v is not None for v in (query, ticker, cik, exchange, types)):
        raise ValueError("a symbol search needs a query, a ticker, a CIK, an exchange or types")
    listed = tickers.listings()
    q = (query or "").strip()
    q_upper, q_lower = q.upper(), q.lower()
    wanted_types = {t.upper() for t in types} if types else None
    wanted_cik = _cik(cik)
    if ticker:
        pool = {ticker.strip().upper(): listed.get(ticker.strip().upper(), [])}
    elif wanted_cik and not q:
        pool = {}
        for row in _cik_index().get(wanted_cik, []):
            pool.setdefault(str(row.get("ticker") or "").upper(), []).append(row)
    else:
        pool = listed
    found: list[tuple[tuple, dict[str, Any]]] = []
    for symbol, rows in pool.items():
        reused = _reused(listed.get(symbol, rows))
        for row in rows:
            name = str(row.get("name") or "")
            if q and symbol == q_upper:
                rank = (0, 0)
            elif q and symbol.startswith(q_upper):
                rank = (1, len(symbol))
            elif q and q_lower in name.lower():
                rank = (2, len(symbol))
            elif q:
                continue
            else:
                rank = (0, len(symbol))
            if active is not None and bool(row.get("active")) != active:
                continue
            if wanted_types and str(row.get("type") or "").upper() not in wanted_types:
                continue
            if exchange and str(row.get("primary_exchange") or "").upper() != exchange.strip().upper():
                continue
            if wanted_cik and _cik(row.get("cik")) != wanted_cik:
                continue
            found.append(((rank[0], not row.get("active"), rank[1], symbol, name), _row(row, reused)))
    found.sort(key=lambda pair: pair[0])
    picked = [r for _, r in found[: limit if limit and limit > 0 else None]]
    frame = pd.DataFrame(picked, columns=COLUMNS)
    frame.attrs.update(query=query, matched=len(found), returned=len(picked), rule=RULE, coverage=COVERAGE,
                       source=str(_path()), as_of=dump_as_of(), common_stock_types=sorted(tickers.COMMON_TYPES))
    return frame


def symbol(ticker: str, day: str | None = None) -> dict[str, Any]:
    """Everything the list knows about one ticker: ``companies`` (every company that used it, with ``held_from`` /
    ``held_to``), ``on_day`` (who held it on ``day`` -- today without one -- and by which rule), ``ticker_reused``,
    ``warning``, ``cik_history`` (per company: every ticker row naming its CIK) and ``as_of``."""
    sym = ticker.strip().upper()
    rows = tickers.listings().get(sym, [])
    held = tickers.resolve(sym, day)
    by_cik = _cik_index()
    extra = {_cik(r.get("cik")): r for r in rows}
    companies = [{**c, "composite_figi": (extra.get(c["cik"]) or {}).get("composite_figi"),
                  "last_updated_utc": (extra.get(c["cik"]) or {}).get("last_updated_utc")} for c in held["candidates"]]
    history = {c["cik"]: sorted((_row(r, False) | {"last_updated_utc": r.get("last_updated_utc")}
                                 for r in by_cik.get(c["cik"], [])),
                                key=lambda r: (not r["active"], r["delisted"] or "", r["ticker"]))
               for c in companies}
    notes = [COVERAGE, "held_from for today's holder comes from Massive ticker details' list_date (latest only)"]
    if not rows:
        notes.append(f"{sym} is not in Massive's ticker list")
    return {"symbol": sym, "day": day, "listed": bool(rows), "ticker_reused": held["ticker_reused"],
            "companies": companies,
            "on_day": {"cik": held["cik"], "name": held["name"], "rule": held["rule"], "warning": held["warning"]},
            "warning": held["warning"], "cik_history": history, "as_of": _as_of(rows), "rule": RULE,
            "source": str(_path()), "dump_as_of": dump_as_of(), "notes": notes}
