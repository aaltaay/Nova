"""Which company held a ticker on a day, for every read keyed by ticker (SEC facts and filings, financials, splits).

Massive's ticker list (``<NOVA_MARKET_DATA_DIR>/store/reference/tickers.json``, delisted tickers included) can give
a ticker two companies: today's holder (``active``, no listing date) and a former one (``delisted_utc``). Tickers
are matched exactly as Massive writes them: a lowercase letter names another security (``AAp`` is Alcoa's $3.75
preferred, delisted 2016-11-01; ``AAP`` is Advance Auto Parts). Folding case once made 84 such pairs look like
one ticker two companies shared (#1236 follow-up); the 2026-10 dump has no ticker two companies share exactly.

The rule, per company (``held_from`` .. ``held_to``):
  former holder  until its delisting day;
  today's holder from its ``list_date`` (Massive ticker details), else the day after the former holder left.
A day inside exactly one window reads that company. Windows that overlap (the data says both were listed) are
settled by whose SEC filings span the day (``submissions.zip``), then by the only common stock among them (the
warning stays); still more than one, the answer has no CIK and
``require`` refuses, naming the candidates -- pass ``cik=``. A ticker with one company is that company on any day
(``warning`` says when the day is outside its window). Without a day the answer is today's holder, and
``ticker_reused`` / ``warning`` say the ticker had another.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from market_reads import roots

COMMON_TYPES = {"CS", "ADRC"}   # Massive ticker types that are a company's common stock (or its ADR)


def _path() -> Path:
    return roots.reference() / "tickers.json"


@lru_cache(maxsize=2)
def _index(path: str, mtime_ns: int) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in json.loads(Path(path).read_text(encoding="utf-8")):
        ticker = str(row.get("ticker") or "").strip()      # case kept: Massive's AAp (a preferred) is not AAP
        if ticker:
            out.setdefault(ticker, []).append(row)
    return out


def listings() -> dict[str, list[dict[str, Any]]]:
    """Every row of the ticker list, by ticker exactly as Massive writes it: a lowercase letter names another
    security of the company (``AAp`` Alcoa's preferred, ``ACIw`` a warrant), never the upper-case ticker."""
    path = _path()
    if not path.is_file():
        return {}
    return _index(str(path), path.stat().st_mtime_ns)


def clear() -> None:
    _index.cache_clear()
    _filing_span_cached.cache_clear()


def _cik(value: Any) -> str | None:
    return str(value or "").strip().lstrip("0") or None


def _day(value: Any) -> str | None:
    return str(value)[:10] if value else None


def _list_date(symbol: str, cik: str) -> str | None:
    """Today's holder's listing date from Massive ticker details (latest only), when it names the same CIK."""
    try:
        from market_reads import reference
        frame = reference.ticker_details(symbol)
    except Exception:  # maintainer: allow-swallow no ticker details leaves the window open, never fails the read
        return None
    if frame.empty or "list_date" not in frame:
        return None
    rows = frame[frame["cik"].map(_cik) == cik] if "cik" in frame else frame
    return _day(rows.iloc[0]["list_date"]) if len(rows) else None


@lru_cache(maxsize=4096)
def _filing_span_cached(cik: str) -> tuple[str, str] | None:
    from market_reads import sec
    try:
        frame = sec.filings_by_cik(cik)
    except LookupError:
        return None
    filed = frame["filed"].dropna() if len(frame) else []
    return (min(filed), max(filed)) if len(filed) else None


def _filing_span(cik: str) -> tuple[str, str] | None:
    return _filing_span_cached(cik)


def key(symbol: str) -> str:
    """The list's ticker for ``symbol``: as given when the list has it so, else upper-case (``aap`` is ``AAP``)."""
    symbol = str(symbol).strip()
    return symbol if symbol in listings() else symbol.upper()


def _candidates(symbol: str) -> list[dict[str, Any]]:
    """One entry per company that held ``symbol``, with the window it held it."""
    seen: dict[str, dict[str, Any]] = {}
    symbol = key(symbol)
    for row in listings().get(symbol, []):
        cik = _cik(row.get("cik"))
        if not cik or cik in seen:
            continue
        seen[cik] = {"cik": cik, "name": row.get("name"), "active": bool(row.get("active")),
                     "delisted": _day(row.get("delisted_utc")), "type": row.get("type"),
                     "exchange": row.get("primary_exchange")}
    out = list(seen.values())
    if len(out) > 1:
        left = [c["delisted"] for c in out if c["delisted"]]
        for c in out:
            listed = None if c["delisted"] and not c["active"] else _list_date(symbol, c["cik"])
            after = [d for d in left if d != c["delisted"] and (not c["delisted"] or d < c["delisted"])]
            if listed is None and after and (c["active"] or not c["delisted"]):
                listed = (date.fromisoformat(max(after)) + timedelta(days=1)).isoformat()
            c["held_from"], c["held_to"] = listed, c["delisted"]
    else:
        for c in out:
            c["held_from"], c["held_to"] = None, c["delisted"]
    return out


def holds(c: dict[str, Any], day: str) -> bool:
    return (c["held_from"] is None or c["held_from"] <= day) and (c["held_to"] is None or day <= c["held_to"])


def _named(c: dict[str, Any]) -> str:
    start, end = c["held_from"], c["held_to"]
    held = (f"{start} to {end or 'today'}" if start else f"until {end}" if end else "no dates")
    return f"{c['name']} (CIK {c['cik']}, {c['type'] or 'type unknown'}, {held})"


def resolve(symbol: str, day: str | None = None, cik: str | None = None) -> dict[str, Any]:
    """``{symbol, day, cik, name, ticker_reused, candidates, rule, warning}``; ``cik`` None when no company can be
    named (unknown ticker, or still ambiguous on ``day``)."""
    symbol = key(symbol)
    found = _candidates(symbol)
    out: dict[str, Any] = {"symbol": symbol, "day": day, "cik": None, "name": None, "ticker_reused": len(found) > 1,
                           "candidates": found, "rule": None, "warning": None}
    pick: dict[str, Any] | None = None
    if cik:
        out["cik"], out["rule"] = _cik(cik), "asked"
        pick = next((c for c in found if c["cik"] == out["cik"]), None)
    elif not found:
        out["rule"] = "not in the ticker list"
    elif len(found) == 1:
        pick, out["rule"] = found[0], "the only company"
        if day and not holds(pick, day):
            out["warning"] = f"{symbol} was delisted {pick['held_to']}, before {day}"
    elif day is None:
        pick = next((c for c in found if c["active"]), None) or max(found, key=lambda c: c["delisted"] or "")
        out["rule"] = "today's holder"
        others = "; ".join(_named(c) for c in found if c is not pick)
        out["warning"] = f"{symbol} was also used by {others}: this is today's company"
    else:
        alive = [c for c in found if holds(c, day)]
        out["rule"] = "held the ticker that day"
        if len(alive) > 1:
            spanning = [c for c in alive if (s := _filing_span(c["cik"])) and s[0] <= day <= s[1]]
            alive, out["rule"] = (spanning, "SEC filings span the day") if len(spanning) == 1 else (alive, None)
        if len(alive) > 1:
            common = [c for c in alive if c["type"] in COMMON_TYPES]
            if len(common) == 1:
                alive, out["rule"] = common, "the only common stock of overlapping listings"
                out["warning"] = (f"{symbol} on {day}: Massive lists " + " and ".join(_named(c) for c in found)
                                  + f"; read the common stock (CIK {common[0]['cik']}) -- pass cik= for the other")
        if len(alive) == 1:
            pick = alive[0]
        else:
            out["warning"] = (f"{symbol} on {day} could be " + " or ".join(_named(c) for c in (alive or found))
                              + ": pass cik=")
    if pick is not None:
        out["cik"], out["name"] = pick["cik"], pick["name"]
    return out


def _next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def holder_runs(symbol: str) -> list[dict[str, Any]]:
    """``resolve``'s answer for every day, as runs ``{cik, held_from, held_to}`` (None = open-ended), for a reused
    ticker; ``[]`` for a ticker one company used. Days ``resolve`` cannot settle are in no run: no holder, unknown.
    The answer can only change where a window or a candidate's SEC filing span starts or ends, so one ``resolve``
    per stretch between those dates gives every day's."""
    found = _candidates(symbol)
    if len(found) < 2:
        return []
    edges: set[str] = set()
    for c in found:
        edges.update(d for d in (c["held_from"], c["held_to"] and _next_day(c["held_to"])) if d)
        span = _filing_span(c["cik"])
        if span:
            edges.update((span[0], _next_day(span[1])))
    cuts = sorted(edges)
    if not cuts:
        return []
    stretches = [(None, (date.fromisoformat(cuts[0]) - timedelta(days=1)).isoformat())]
    stretches += [(start, (date.fromisoformat(end) - timedelta(days=1)).isoformat()) for start, end in zip(cuts, cuts[1:])]
    stretches.append((cuts[-1], None))
    runs: list[dict[str, Any]] = []
    for start, end in stretches:
        cik = resolve(symbol, start or end)["cik"]
        if cik and runs and runs[-1]["cik"] == cik and runs[-1]["held_to"] == (
                None if start is None else (date.fromisoformat(start) - timedelta(days=1)).isoformat()):
            runs[-1]["held_to"] = end
        elif cik:
            runs.append({"cik": cik, "held_from": start, "held_to": end})
    return runs


def require(symbol: str, day: str | None = None, cik: str | None = None) -> dict[str, Any]:
    """``resolve``, raising ``LookupError`` when no company can be named."""
    answer = resolve(symbol, day, cik)
    if answer["cik"]:
        return answer
    if answer["candidates"]:
        raise LookupError(answer["warning"])
    raise LookupError(f"{answer['symbol']} has no SEC CIK in {_path()}")


def summary(answer: dict[str, Any]) -> dict[str, Any]:
    """The part of a resolution a read puts in its answer."""
    return {k: answer[k] for k in ("cik", "name", "ticker_reused", "rule", "warning")} | {
        "candidates": [{k: c[k] for k in ("cik", "name", "held_from", "held_to")} for c in answer["candidates"]]
        if answer["ticker_reused"] else []}
