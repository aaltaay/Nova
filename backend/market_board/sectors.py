"""The sector and industry boards and the top-stocks cards (ADR 053), composed from what the refreshers hold.

An ETF's move: 1 D its IBKR snapshot against its prior close; 7 D / 30 D its price (else its last regular-hours
close) against the regular-hours close 5 / 21 sessions back. A sector's members are its State Street holdings
file; its 1 D leader is its best member among IBKR's large-cap gainers scan and its top ``MARKET_LEADER_POOL``
holdings, its 7 D / 30 D leader the best of those holdings by daily closes. Every sector gets a top-stocks card,
ranked from the same stocks (ADR 053 amendment 2026-10-13 evening: a sector with no stock in the gainers scan had an
empty card). Pure over the inputs given.
"""
from __future__ import annotations

from typing import Any, Callable

from constants_market_board import (
    MARKET_DEFENSE,
    MARKET_INDUSTRIES,
    MARKET_LEADER_POOL,
    MARKET_NO_MEMBER_FILE_WHY,
    MARKET_OFFENSE,
    MARKET_PERIOD_SESSIONS,
    MARKET_SECTORS,
    MARKET_TOP_CARDS,
    MARKET_TOP_ROWS,
)

Quotes = dict[str, dict[str, Any]]
Closes = Callable[[str], list | None]      # symbol -> [[date, close]] oldest first, or None (not read yet)
Holdings = Callable[[str], dict | None]    # ETF -> {as_of, rows}


def _pct(now: float | None, base: float | None) -> float | None:
    if now is None or not base:
        return None
    return round(100.0 * (now / base - 1.0), 2)


def change(sym: str, period: str, quotes: Quotes, closes: Closes, today: str) -> float | None:
    """``sym``'s move over ``period`` in percent points, ``None`` when IBKR has not given what it needs."""
    q = quotes.get(sym) or {}
    if period == "1D":
        return _pct(q.get("price"), q.get("prev_close"))
    rows = closes(sym) or []
    prior = [c for d, c in rows if d < today]
    n = MARKET_PERIOD_SESSIONS[period]
    if len(prior) < n:
        return None
    last = q.get("price") or next((c for d, c in reversed(rows) if d == today), None) or prior[-1]
    return _pct(last, prior[-n])


def spark(sym: str, period: str, closes: Closes, today: str) -> list[float] | None:
    if period == "1D":
        return None
    rows = closes(sym) or []
    n = MARKET_PERIOD_SESSIONS[period]
    prior = [c for d, c in rows if d < today]
    tail = prior[-n:] + [c for d, c in rows if d == today]
    return tail if len(tail) >= 2 else None


def members(etf: str, holdings: Holdings) -> list[str]:
    return [r["symbol"] for r in (holdings(etf) or {}).get("rows") or []]


def candidates(syms: list[str], period: str, ctx: dict[str, Any]) -> tuple[list[str], Quotes]:
    """The stocks a sector's leader and top-stocks card rank, and the quotes that price them.

    1 D: its members in the large-cap gainers scan, then its top ``MARKET_LEADER_POOL`` holdings; 7 D / 30 D: those
    holdings, whose daily closes are read.
    """
    if period != "1D":
        return syms[:MARKET_LEADER_POOL], ctx["pool_quotes"]
    movers = ctx["movers"]
    picked = [s for s in syms if s in movers] + syms[:MARKET_LEADER_POOL]
    return list(dict.fromkeys(picked)), {**ctx["pool_quotes"], **movers}


def _leader(etf: str, period: str, ctx: dict[str, Any]) -> tuple[dict | None, str | None]:
    h = ctx["holdings"](etf)
    if h is None:
        return None, "State Street's holdings file has not been read"
    pool, quotes = candidates([r["symbol"] for r in h.get("rows") or []], period, ctx)
    moved = [(s, change(s, period, quotes, ctx["closes"], ctx["today"])) for s in pool]
    moved = [(s, c) for s, c in moved if c is not None]
    if not moved:
        return None, "IBKR has not priced its stocks yet" if period == "1D" else "no member's closes yet"
    sym, pct = max(moved, key=lambda x: x[1])
    return {"symbol": sym, "change_pct": pct}, None


def board(kind: str, period: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """The wire's ``sectors`` (``kind="sectors"``) or ``industries`` block."""
    rows = []
    entries = [(n, e, True) for n, e in MARKET_SECTORS] if kind == "sectors" else list(MARKET_INDUSTRIES)
    context_period = "7D" if period == "1D" else "1D"
    for name, etf, has_file in entries:
        leader, why = _leader(etf, period, ctx) if has_file else (None, MARKET_NO_MEMBER_FILE_WHY)
        rows.append({
            "name": name, "etf": etf,
            "change_pct": change(etf, period, ctx["etf_quotes"], ctx["closes"], ctx["today"]),
            "context_pct": change(etf, context_period, ctx["etf_quotes"], ctx["closes"], ctx["today"]),
            "context_period": context_period, "leader": leader, "leader_why": why,
        })
    rows.sort(key=lambda r: (r["change_pct"] is None, -(r["change_pct"] or 0.0)))
    out: dict[str, Any] = {"period": period, "from": ctx["period_from"][period], "to": ctx["today"], "rows": rows}
    if kind == "sectors":
        by_etf = {r["etf"]: r["change_pct"] for r in rows}

        def mean(group: tuple[str, ...]) -> float | None:
            vals = [by_etf[e] for e in group if by_etf.get(e) is not None]
            return round(sum(vals) / len(vals), 2) if len(vals) == len(group) else None

        out["offense_pct"], out["defense_pct"] = mean(MARKET_OFFENSE), mean(MARKET_DEFENSE)
    return out


def _cards_order(sectors_rows: list[dict]) -> list[dict]:
    """Strength order (an unquoted sector last); past ``MARKET_TOP_CARDS``, the strongest and the weakest."""
    if len(sectors_rows) <= MARKET_TOP_CARDS:
        return sectors_rows
    known = [r for r in sectors_rows if r["change_pct"] is not None]
    return known[:MARKET_TOP_CARDS - 1] + known[-1:]


def top(kind: str, period: str, ctx: dict[str, Any], runners: list[tuple[str, list[dict]]] | None) -> dict[str, Any]:
    """The wire's ``top`` block."""
    if kind == "runners":
        cards = [{"name": theme, "etf": None, "change_pct": None, "rows": [
            {"symbol": r["symbol"], "last": r["last"], "change_pct": r["change_pct"], "spark": None}
            for r in rows[:MARKET_TOP_ROWS]]} for theme, rows in (runners or [])[:MARKET_TOP_CARDS]]
        why = None if cards else "no small-cap runners recorded in this period"
        return {"kind": kind, "period": period, "cards": cards, "why": why}
    sector_rows = board("sectors", period, ctx)["rows"]
    quotes = ctx["pool_quotes"]
    cards = []
    for row in _cards_order(sector_rows):
        etf = row["etf"]
        items = []
        for sym in members(etf, ctx["holdings"])[:MARKET_TOP_ROWS]:
            q = quotes.get(sym) or {}
            items.append({"symbol": sym, "last": q.get("price"),
                          "change_pct": change(sym, period, quotes, ctx["closes"], ctx["today"]),
                          "spark": spark(sym, period, ctx["closes"], ctx["today"])})
        cards.append({"name": row["name"], "etf": etf, "change_pct": row["change_pct"], "rows": items[:MARKET_TOP_ROWS]})
    priced = any(r["last"] is not None or r["change_pct"] is not None for c in cards for r in c["rows"])
    why = None if priced else (
        "State Street's holdings files have not been read" if not any(members(r["etf"], ctx["holdings"])
                                                                      for r in sector_rows)
        else "IBKR has not priced the sectors' stocks yet")
    return {"kind": kind, "period": period, "cards": cards, "why": why}
