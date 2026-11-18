"""Claude and the brain while the desk is off Paper (ADR 072 Amendments 3 and 4, ``traders.md`` "Paused").

An AI trader opens trades on one venue (``TRADER_VENUE``, Paper). While its switch is On and the desk shows another
venue, Live or Sim, it is paused. This module owns the pause: its words (``paused``), what a venue change does about
it (``desk_changed``: leaving Paper cancels the trader's unfilled entries there, so no position of its opens during
the pause), and the entries a switch away would cancel (``entries_waiting``). The switch, the lane and an open trade
are never touched here.
"""
from __future__ import annotations

import logging
from typing import Any

from constants_owners import AI_TRADERS, OWNER_BRAIN, OWNER_CLAUDE, OWNER_NAMES
from constants_traders import TRADER_PAUSED, TRADER_VENUE

logger = logging.getLogger(__name__)
_VENUE_NAMES = {"live": "Live", "paper": "Paper", "sim": "Sim"}
EVENT_PAUSED = "paused"
EVENT_RESUMED = "resumed"


def venue_name(venue: str) -> str:
    return _VENUE_NAMES.get(venue, venue)


def paused(trader: str, now: float | None = None) -> dict[str, Any] | None:
    """``{reason, venue, text}`` while ``trader``'s switch is On and the desk is off its venue, else None."""
    from sim.mode import venue
    from traders import switches

    desk = venue()
    if desk == TRADER_VENUE or not switches.is_on(trader, now):
        return None
    name = switches.said(trader)
    return {"reason": TRADER_PAUSED, "venue": desk,
            "text": f"The desk is on {venue_name(desk)}: {name} is paused. It opens no trade until the desk is back "
                    f"on {venue_name(TRADER_VENUE)}; a trade it holds there keeps its stop and target."}


def entries_waiting() -> list[dict[str, Any]]:
    """``[{trader, symbol, order_id}]``: Claude's and the brain's unfilled entries on Paper, which leaving Paper
    cancels. Raises when Paper cannot be read: an unknown is never read as none."""
    from owners.whose import book_of, holder_of
    from practice.broker import for_venue
    from traders.off import is_entry

    out = []
    for row in for_venue(TRADER_VENUE).ledger.working_orders():
        trader = book_of(holder_of(row))
        if trader in AI_TRADERS and is_entry(row):
            out.append({"trader": trader, "symbol": str(row.get("symbol") or "").upper(),
                        "order_id": int(row["order_id"])})
    return out


def _say(trader: str, kind: str, text: str, symbol: str | None = None) -> None:
    """One line on the trader's own stream (and the log)."""
    try:
        if trader == OWNER_BRAIN:
            from brain import session

            session.event(kind, text, symbol)
        elif trader == OWNER_CLAUDE:
            from agent_trader import seat

            seat.event(kind, text)
    except Exception:
        logger.exception("TRADERS: %s's stream could not take: %s", trader, text)


def _left_paper(where: str) -> list[dict[str, Any]]:
    from traders import off, switches

    left: list[dict[str, Any]] = []
    for trader in AI_TRADERS:
        name, said = OWNER_NAMES.get(trader, trader), switches.said(trader)
        try:
            on = switches.is_on(trader)
            rows = off.cancel_entries(trader, venues=(TRADER_VENUE,), code=TRADER_PAUSED,
                                      reason=f"the desk left Paper for {where}")
        except Exception:
            logger.exception("TRADERS: %s's entries on Paper could not be read on the way to %s", trader, where)
            _say(trader, EVENT_PAUSED, f"The desk went to {where}. Nova could not read {said}'s orders on Paper, so "
                                       "a buy still waiting there may fill.")
            continue
        if on:
            _say(trader, EVENT_PAUSED, f"The desk went to {where}: {said} is paused. It opens no trade until the "
                                       "desk is back on Paper; a trade it holds there keeps its stop and target.")
        for row in rows:
            symbol = str(row.get("symbol") or "").upper()
            if row["ok"]:
                text = (f"{name}'s unfilled buy on {symbol} was cancelled: the desk left Paper for {where}, and "
                        f"{said} opens no trade while it is paused.")
                left.append({"venue": TRADER_VENUE, "symbol": symbol, "order_id": row["order_id"], "by": trader,
                             "text": text})
            else:
                text = (f"{name}'s unfilled buy on {symbol} could not be cancelled ({row['error']}): it may still "
                        "fill on Paper.")
                logger.error("TRADERS: %s", text)
            _say(trader, EVENT_PAUSED, text, symbol)
    return left


def _back_on_paper() -> None:
    from traders import switches

    for trader in AI_TRADERS:
        try:
            if switches.is_on(trader):
                _say(trader, EVENT_RESUMED, f"The desk is back on Paper: {switches.said(trader)} may trade again.")
        except Exception:
            logger.exception("TRADERS: %s's switch could not be read on the way back to Paper", trader)


def desk_changed(previous: str, now_venue: str) -> list[dict[str, Any]]:
    """The desk went from ``previous`` to ``now_venue`` (``sim.mode.set_venue``). Returns the entries cancelled on
    the way out of Paper, for the switch's ``left``: ``[{venue, symbol, order_id, by, text}]``. Never raises: a venue
    change does not fail on a trader's book or stream -- what could not be done is logged and said on the stream."""
    if previous == now_venue or TRADER_VENUE not in (previous, now_venue):
        return []
    if previous == TRADER_VENUE:
        return _left_paper(venue_name(now_venue))
    _back_on_paper()
    return []
