"""What turning Claude's or the brain's switch Off does (ADR 072 decision 6, ``traders.md`` "The switches").

Off is never refused, and runs in this order: the file first (``switches``), so a crash part way never leaves the
trader On; then every position it holds on Paper and Sim is handed to you (``handed``); then its unfilled entries
are cancelled on both venues (source ``cancel_working``, code ``TAKEOVER``) -- an entry's waiting exits go with it,
and the exits of shares it holds keep resting; then Claude's armed breaks and reflexes are dropped (its guard skips
a handed stock, ``agent_trader.ledger``). Each step is said on the trader's stream.
"""
from __future__ import annotations

import logging
from typing import Any

from constants_owners import OWNER_CLAUDE, OWNER_NAMES, TAKEOVER_CODE

logger = logging.getLogger(__name__)


def _entry(row: dict[str, Any]) -> bool:
    """An unfilled order that opens or adds -- not an exit of shares held, nor a bracket leg waiting on an entry
    (that one goes with its entry)."""
    return (row.get("effect") == "opens" and row.get("parent_id") is None
            and row.get("leg_role") in (None, "parent"))


def cancel_entries(trader: str) -> list[dict[str, Any]]:
    """Cancel ``trader``'s unfilled entries on Paper and Sim; ``[{venue, order_id, symbol, ok, error}]``."""
    from owners.whose import book_of, holder_of
    from practice.broker import for_venue, loaded
    from traders.handed import PRACTICE_VENUES

    out: list[dict[str, Any]] = []
    for venue in PRACTICE_VENUES:
        broker = for_venue(venue) if venue == "paper" else loaded(venue)
        if broker is None:
            continue
        for row in list(broker.ledger.working_orders()):
            if book_of(holder_of(row)) != trader or not _entry(row):
                continue
            answer = broker.cancel(int(row["order_id"]), source="cancel_working", code=TAKEOVER_CODE,
                                   reason=f"{OWNER_NAMES.get(trader, trader)} was switched off")
            out.append({"venue": venue, "order_id": int(row["order_id"]), "symbol": row.get("symbol"),
                        "ok": bool(answer.get("ok")), "error": answer.get("error")})
    return out


def _resting_stops(trader: str, venue: str, symbol: str) -> list[float]:
    from owners.whose import book_of, holder_of
    from practice.broker import loaded

    broker = loaded(venue)
    if broker is None:
        return []
    return [float(r["stop_price"]) for r in broker.ledger.working_orders()
            if str(r.get("symbol") or "").upper() == symbol and book_of(holder_of(r)) == trader
            and r.get("stop_price") is not None]


def handed_words(trader: str, venue: str, symbol: str, qty: float) -> str:
    name = OWNER_NAMES.get(trader, trader)
    stops = _resting_stops(trader, venue, symbol)
    rest = f" Its stop at {stops[0]:g} keeps resting." if stops else ""
    return f"{name} is off: its {abs(qty):g} {symbol} are yours to close.{rest}"


async def turn_off(trader: str, by: str, now: float | None = None) -> list[str]:
    """Switch ``trader`` Off and do what Off means; returns each step in words (also on its stream and the log)."""
    from practice.broker import loaded
    from traders import handed, switches

    t = switches.now_ts() if now is None else float(now)
    switches.set_switch(trader, False, by, t)
    name = OWNER_NAMES.get(trader, trader)
    steps = [f"{name} is off: no new trades."]
    for venue, symbols in handed.hand_held(trader, t).items():
        broker = loaded(venue)
        for symbol in symbols:
            qty = broker.ledger.owners.qty_of(symbol, trader) if broker is not None else 0.0
            steps.append(handed_words(trader, venue, symbol, qty) + ("" if venue == "paper" else " (Sim)"))
    for row in cancel_entries(trader):
        if row["ok"]:
            steps.append(f"Its unfilled order on {row['symbol']} was cancelled.")
        else:
            steps.append(f"Its order on {row['symbol']} could not be cancelled: {row['error']}.")
    if trader == OWNER_CLAUDE:
        from agent_trader import seat

        seat.switch_off(steps, t)
    for step in steps:
        logger.info("TRADERS: %s", step)
    return steps
