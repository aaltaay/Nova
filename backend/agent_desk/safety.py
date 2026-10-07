"""What an agent's show or move would put at stake (ADR 050 decision 5).

The operator: an agent may switch the desk to the Sim "when nothing is at stake". On the venue the desk would
leave, a position, a working order, the Bot on, an open bot or Nova trade, a Nova stock mode or approval, or an
armed desk is at stake -- a venue change disarms, turns the Bot off and cancels Nova's working entries there
(ADR 042). Loading another Sim window starts the Sim's scratch account over, so its positions and working
orders are at stake too. Memory reads only, as ``diagnostics/restart_check`` does; a check that cannot be read
is at stake.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from diagnostics import restart_check

logger = logging.getLogger(__name__)

Item = dict[str, Any]


def _item(kind: str, text: str, venue: str | None, symbol: str | None = None) -> Item:
    return {"kind": kind, "venue": venue, "symbol": symbol, "text": text}


def _positions_and_orders(venue: str) -> list[Item]:
    if venue == "live":
        return [dict(i, venue="live") for i in restart_check.ibkr()]
    if venue == "paper":
        return [i for i in restart_check.practice() if i.get("venue") == "paper"]
    return []


def _bot(venue: str) -> list[Item]:
    from bot.session import get_session

    session = get_session()
    items: list[Item] = []
    if session.get("active") or session.get("bot_on"):
        items.append(_item("bot", f"The Bot is on for {venue.capitalize()}: switching turns it off", venue))
    for row in restart_check.bot_trade():
        if row.get("venue") in (None, venue):
            items.append(row)
    return items


def _stock_modes(venue: str) -> list[Item]:
    return [i for i in restart_check.stock_modes() if i.get("venue") in (None, venue)]


def _armed(venue: str) -> list[Item]:
    from ibkr import safety

    if safety.armed():
        return [_item("armed", f"The desk is armed on {venue.capitalize()}: switching disarms it", venue)]
    return []


READERS: tuple[tuple[str, Callable[[str], list[Item]]], ...] = (
    ("orders", _positions_and_orders),
    ("bot", _bot),
    ("stock_mode", _stock_modes),
    ("armed", _armed),
)


def _sim_account(_venue: str) -> list[Item]:
    """The Sim's scratch account: loading another window starts it over (ADR 020 decision 3)."""
    items = [dict(i, text=i["text"].split(":")[0] + ": loading another window starts the Sim account over")
             for i in restart_check.practice() if i.get("venue") == "sim"]
    return items


SIM_READERS: tuple[tuple[str, Callable[[str], list[Item]]], ...] = (("sim_account", _sim_account),)


def _read(venue: str, readers: tuple[tuple[str, Callable[[str], list[Item]]], ...]) -> tuple[list[Item], list[dict]]:
    items: list[Item] = []
    unknown: list[dict[str, str]] = []
    for kind, read in readers:
        try:
            items.extend(read(venue))
        except Exception as exc:  # a check that cannot be read is at stake, never "nothing there"
            logger.warning("agent desk: could not check %s on %s: %s", kind, venue, exc, exc_info=True)
            unknown.append({"kind": kind, "error": f"{type(exc).__name__}: {exc}"})
    return items, unknown


def at_stake(venue: str, *, switching: bool = True, reloading: bool = False,
             readers: tuple[tuple[str, Callable[[str], list[Item]]], ...] | None = None,
             sim_readers: tuple[tuple[str, Callable[[str], list[Item]]], ...] | None = None) -> dict[str, Any]:
    """``{venue, safe, items, unknown}``: ``safe`` is true only when every check answered and found nothing.

    ``switching``: the desk leaves ``venue`` for the Sim (nothing is left when it is on the Sim already).
    ``reloading``: another Sim window is loaded, which starts the Sim's scratch account over.
    """
    items: list[Item] = []
    unknown: list[dict[str, str]] = []
    if switching and venue != "sim":
        found, failed = _read(venue, READERS if readers is None else readers)
        items += found
        unknown += failed
    if reloading:
        found, failed = _read("sim", SIM_READERS if sim_readers is None else sim_readers)
        items += found
        unknown += failed
    return {"venue": venue, "safe": not items and not unknown, "items": items, "unknown": unknown}
