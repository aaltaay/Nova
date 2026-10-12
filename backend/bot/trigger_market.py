"""Where each ticker of the squares stands now (operator ask, 2026-10-12): its price and change on the day.

The same row the quote panel and "Why it's moving" read: the ticker's scanner row when a board holds it
(``strategy.symbol_pillars.BOARD_ORDER``), its price and change taken from the live L1 line's last trade
(``move_reason.facts.with_live_trade``), else the L1 line alone. Lines already held only: nothing here
subscribes. A price that is IBKR's prior close before the first trade (``close_fallback``, #541) is no
change, and a ticker no board and no line holds has none; each says why. On a Sim replay desk the boards
are live and the quotes the replay's, so no change is said there.

``{price, change_pct, change_abs, source, why}`` per symbol: ``change_pct`` a fraction (0.25 = +25%) as the
boards send it, ``source`` the board's name or ``quote``, ``why`` set when ``change_pct`` is ``None``.
Owner: this module (no state; it reads, never writes).
"""
from __future__ import annotations

import logging
from typing import Any

from constants_ibkr import IBKR_QUOTE_QUALITY_CLOSE_FALLBACK

logger = logging.getLogger(__name__)


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if v == v else None


def _none(why: str, source: str | None = None) -> dict[str, Any]:
    return {"price": None, "change_pct": None, "change_abs": None, "source": source, "why": why}


def _traded(quote: dict[str, Any] | None) -> bool:
    """The L1 line has seen a trade today (``with_live_trade``'s test): IBKR's prior close is not one."""
    q = quote or {}
    price = _num(q.get("price"))
    return (price is not None and price > 0 and q.get("quote_quality") != IBKR_QUOTE_QUALITY_CLOSE_FALLBACK
            and q.get("last_trade_ts") is not None)


def one(symbol: str, row: dict[str, Any] | None, board: str | None, quote: dict[str, Any] | None) -> dict[str, Any]:
    """The move from what was read (pure): ``row`` the board's row on ``board``, ``quote`` the L1 line's."""
    from move_reason.facts import with_live_trade
    from strategy.symbol_pillars import SOURCE_QUOTE, quote_row

    traded = _traded(quote)
    if row is not None:
        if row.get("quote_quality") == IBKR_QUOTE_QUALITY_CLOSE_FALLBACK and not traded:
            return _none(f"no trade on {symbol} yet today: the board's price is IBKR's prior close", board)
        live, source = with_live_trade(row, quote), board
    elif quote is not None:
        if not traded:
            return _none(f"no trade on {symbol} yet on its Level 1 line", SOURCE_QUOTE)
        live, source = quote_row(symbol, quote), SOURCE_QUOTE
    else:
        return _none(f"no scanner board holds {symbol} and Nova holds no Level 1 line on it")
    price, change = _num(live.get("price")), _num(live.get("change_pct"))
    if price is None or change is None or change <= -1:
        return _none(f"the {'board' if row is not None else 'Level 1 line'} has no change for {symbol}", source)
    prev = _num(live.get("prev_close")) or _num((quote or {}).get("prev_close"))
    return {"price": price, "change_pct": change, "change_abs": round(price - prev, 4) if prev else None,
            "source": source, "why": None}


def moves(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Each symbol's move now; a read that fails says so on every symbol, never a guessed change."""
    from sim.mode import is_replay_desk
    from strategy.symbol_pillars import find_board_row, raw_boards

    syms = [s.upper() for s in dict.fromkeys(symbols)]
    if not syms:
        return {}
    try:
        if is_replay_desk():
            said = _none("the desk shows a Sim replay: today's change shows on Paper, Live or the Sim's live edge")
            return {s: dict(said) for s in syms}
        from ibkr import ticks

        boards = raw_boards()
        quotes = ticks.last_quotes(syms)
    except Exception:
        logger.warning("triggers audit: the boards or the Level 1 lines could not be read", exc_info=True)
        said = _none("the scanner boards or the Level 1 lines could not be read (the backend log has the error)")
        return {s: dict(said) for s in syms}
    out = {}
    for sym in syms:
        row, board = find_board_row(sym, boards)
        out[sym] = one(sym, row, board, quotes.get(sym))
    return out
