"""Claude's shares, orders and day on Paper, read from Paper's own ledger (ADR 068 decision 6).

Claude's rows are the ones stamped ``order_origin: "claude"``; its position is what its own fills add up to, never
the account's position in the stock. Reads go straight to ``practice.broker.for_venue("paper")`` whatever the desk
shows; a read that fails raises ``ReadError`` -- unknown is never "flat".
"""
from __future__ import annotations

import logging
from typing import Any

from agent_trader.constants_agent_trader import AGENT_ORIGIN, AGENT_VENUE

logger = logging.getLogger(__name__)
_EPS = 1e-9


class ReadError(Exception):
    """Paper's ledger could not be read; the caller must not guess."""


def paper() -> Any:
    from practice.broker import for_venue

    return for_venue(AGENT_VENUE)


def _mine(row: dict[str, Any]) -> bool:
    return row.get("order_origin") == AGENT_ORIGIN


def _rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    try:
        ledger = paper().ledger
        return ledger.working_orders(), ledger.closed_orders(), float(ledger.day_started_ts)
    except Exception as exc:
        raise ReadError(f"Paper's orders could not be read: {exc}") from exc


def working() -> list[dict[str, Any]]:
    """Claude's working orders (a bracket's waiting exits too)."""
    live, _, _ = _rows()
    return [r for r in live if _mine(r)]


def fills_today() -> list[dict[str, Any]]:
    """Claude's filled orders since Paper's day began, oldest first."""
    _, closed, day_start = _rows()
    rows = [r for r in closed if _mine(r) and str(r.get("status")) == "Filled"
            and float(r.get("fill_ts") or 0.0) >= day_start - _EPS]
    return sorted(rows, key=lambda r: float(r.get("fill_ts") or 0.0))


def position(symbol: str, fills: list[dict[str, Any]] | None = None) -> float:
    """Claude's own shares in ``symbol`` (long only): its buys less its sells today."""
    sym = (symbol or "").upper()
    qty = 0.0
    for row in fills if fills is not None else fills_today():
        if str(row.get("symbol") or "").upper() != sym:
            continue
        n = float(row.get("filled_qty") or 0.0)
        qty += n if str(row.get("side") or "").upper() == "BUY" else -n
    return max(0.0, qty)


def positions(fills: list[dict[str, Any]] | None = None) -> dict[str, float]:
    rows = fills if fills is not None else fills_today()
    out: dict[str, float] = {}
    for sym in {str(r.get("symbol") or "").upper() for r in rows}:
        qty = position(sym, rows)
        if qty > _EPS:
            out[sym] = qty
    return out


def entries_today(fills: list[dict[str, Any]] | None = None, live: list[dict[str, Any]] | None = None) -> int:
    """Trades opened today: Claude's filled entries plus its entries still working (a buy is an entry)."""
    rows = fills if fills is not None else fills_today()
    filled = sum(1 for r in rows if str(r.get("side") or "").upper() == "BUY" and r.get("order_source") == "bot")
    working_rows = live if live is not None else working()
    resting = sum(1 for r in working_rows if str(r.get("side") or "").upper() == "BUY"
                  and r.get("leg_role") in (None, "parent"))
    return filled + resting


def day_pnl(fills: list[dict[str, Any]] | None = None) -> float:
    """Claude's P&L today, fees included: cash from its fills plus its open shares at Paper's mark."""
    rows = fills if fills is not None else fills_today()
    cash, ledger = 0.0, paper().ledger
    for row in rows:
        n, px = float(row.get("filled_qty") or 0.0), float(row.get("avg_fill_price") or 0.0)
        fees = float(((row.get("fees") or {}).get("total")) or 0.0)
        cash += (-n * px if str(row.get("side") or "").upper() == "BUY" else n * px) - fees
    for sym, qty in positions(rows).items():
        mark = ledger.mark_of(sym)
        if mark is None:
            raise ReadError(f"Paper has no mark for {sym}")
        cash += qty * float(mark)
    return cash


def others_in(symbol: str) -> str | None:
    """Why ``symbol`` is not Claude's to trade -- someone else's shares or orders there -- or None."""
    sym = (symbol or "").upper()
    live, _, _ = _rows()
    try:
        held = float(paper().ledger.held_qty(sym))
    except Exception as exc:
        raise ReadError(f"Paper's position in {sym} could not be read: {exc}") from exc
    mine = position(sym)
    if abs(held - mine) > _EPS:
        return f"Paper holds {held - mine:+g} shares of {sym} that are not Claude's (yours or a bot's)"
    theirs = [r for r in live if str(r.get("symbol") or "").upper() == sym and not _mine(r)]
    if theirs:
        return f"{len(theirs)} working order(s) on {sym} are not Claude's (yours or a bot's)"
    return None
