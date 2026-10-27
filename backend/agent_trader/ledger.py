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
# What the wire and the desk say when Paper could not be read; the exception's detail goes to the log only.
UNREAD_TEXT = "Paper's orders could not be read just now, so nothing was sent; Nova's log has the detail"


class ReadError(Exception):
    """Paper's ledger could not be read; the caller must not guess (and says ``UNREAD_TEXT``, never the detail)."""


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


def _own(symbol: str, rows: list[dict[str, Any]]) -> float:
    """What Claude's own fills in ``symbol`` add up to today (long only)."""
    sym = (symbol or "").upper()
    qty = 0.0
    for row in rows:
        if str(row.get("symbol") or "").upper() != sym:
            continue
        n = float(row.get("filled_qty") or 0.0)
        qty += n if str(row.get("side") or "").upper() == "BUY" else -n
    return max(0.0, qty)


def _held(symbol: str) -> float:
    try:
        return max(0.0, float(paper().ledger.held_qty((symbol or "").upper())))
    except Exception as exc:
        raise ReadError(f"Paper's position in {symbol} could not be read: {exc}") from exc


def position(symbol: str, fills: list[dict[str, Any]] | None = None) -> float:
    """Claude's shares in ``symbol``: its own fills, never more than Paper holds.

    Nova's own closes sell Claude's shares under their own origin -- the loss limit's Auto sell (``loss_limit`` /
    ``loss_limit_bots``), KILL, a margin call -- so Claude's fills alone would still count shares Paper no longer
    holds (Codex review, PR #1239). Claude opens only where nobody else holds shares (``others_in``), so the account's
    shares cap its own.
    """
    rows = fills if fills is not None else fills_today()
    return min(_own(symbol, rows), _held(symbol))


def positions(fills: list[dict[str, Any]] | None = None) -> dict[str, float]:
    rows = fills if fills is not None else fills_today()
    out: dict[str, float] = {}
    for sym in {str(r.get("symbol") or "").upper() for r in rows}:
        qty = position(sym, rows)
        if qty > _EPS:
            out[sym] = qty
    return out


def _closed_for_claude(symbol: str, since_ts: float) -> float | None:
    """The average price of today's SELL fills in ``symbol`` that were not Claude's since ``since_ts`` -- the closes
    Nova made on Claude's shares -- or None when there are none."""
    _, closed, day_start = _rows()
    sym = (symbol or "").upper()
    qty = notional = 0.0
    for row in closed:
        if (str(row.get("symbol") or "").upper() == sym and not _mine(row) and str(row.get("status")) == "Filled"
                and str(row.get("side") or "").upper() == "SELL"
                and float(row.get("fill_ts") or 0.0) >= max(since_ts, day_start) - _EPS):
            n = float(row.get("filled_qty") or 0.0)
            qty += n
            notional += n * float(row.get("avg_fill_price") or 0.0)
    return notional / qty if qty > _EPS else None


def entries_today(fills: list[dict[str, Any]] | None = None, live: list[dict[str, Any]] | None = None) -> int:
    """Trades opened today: Claude's filled entries plus its entries still working (a buy is an entry)."""
    rows = fills if fills is not None else fills_today()
    filled = sum(1 for r in rows if str(r.get("side") or "").upper() == "BUY" and r.get("order_source") == "bot")
    working_rows = live if live is not None else working()
    resting = sum(1 for r in working_rows if str(r.get("side") or "").upper() == "BUY"
                  and r.get("leg_role") in (None, "parent"))
    return filled + resting


def day_pnl(fills: list[dict[str, Any]] | None = None) -> float:
    """Claude's P&L today, fees included: cash from its fills, its open shares at Paper's mark, and shares Nova
    sold for it under another origin at the price those closes got (their fees are not Claude's here)."""
    rows = fills if fills is not None else fills_today()
    cash, ledger = 0.0, paper().ledger
    for row in rows:
        n, px = float(row.get("filled_qty") or 0.0), float(row.get("avg_fill_price") or 0.0)
        fees = float(((row.get("fees") or {}).get("total")) or 0.0)
        cash += (-n * px if str(row.get("side") or "").upper() == "BUY" else n * px) - fees
    for sym in {str(r.get("symbol") or "").upper() for r in rows}:
        own, held = _own(sym, rows), position(sym, rows)
        mark = ledger.mark_of(sym)
        if (own > _EPS or held > _EPS) and mark is None:
            raise ReadError(f"Paper has no mark for {sym}")
        cash += held * float(mark or 0.0)
        if own - held > _EPS:     # shares Nova sold for Claude under another origin: at the price those closes got
            first_buy = min((float(r.get("fill_ts") or 0.0) for r in rows
                             if str(r.get("symbol") or "").upper() == sym and str(r.get("side") or "").upper() == "BUY"),
                            default=0.0)
            sold_at = _closed_for_claude(sym, first_buy)
            cash += (own - held) * float(sold_at if sold_at is not None else mark or 0.0)
    return cash


def others_in(symbol: str) -> str | None:
    """Why ``symbol`` is not Claude's to trade -- someone else's shares or orders there -- or None."""
    sym = (symbol or "").upper()
    live, _, _ = _rows()
    held = _held(sym)
    mine = position(sym)
    if abs(held - mine) > _EPS:
        return f"Paper holds {held - mine:+g} shares of {sym} that are not Claude's (yours or a bot's)"
    theirs = [r for r in live if str(r.get("symbol") or "").upper() == sym and not _mine(r)]
    if theirs:
        return f"{len(theirs)} working order(s) on {sym} are not Claude's (yours or a bot's)"
    return None
