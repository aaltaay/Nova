"""What an agent's show or move would put at stake (ADR 050 decision 5).

The operator: an agent may switch the desk to the Sim "when nothing is at stake". On the venue the desk would
leave, a position, a working order or an armed desk is at stake -- a venue change disarms (ADR 018). (The Bot
switch, the bot's trade and Nova's stock modes retired with the bots, ADR 072.) Loading another Sim window starts
the Sim's scratch account over, so its positions and working orders are at stake too. Memory reads only, as ``diagnostics/restart_check`` does; a check that cannot be read
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


def _armed(venue: str) -> list[Item]:
    from ibkr import safety

    if safety.armed():
        return [_item("armed", f"The desk is armed on {venue.capitalize()}: switching disarms it", venue)]
    return []


READERS: tuple[tuple[str, Callable[[str], list[Item]]], ...] = (
    ("orders", _positions_and_orders),
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


# What a venue switch changes on the desk itself, whatever it leaves behind: the padlock. The Bot it also turned
# off retired with the bots (ADR 072); nothing of Nova's waits to fill on a venue any more.
SWITCH_READERS: tuple[tuple[str, Callable[[str], list[Item]]], ...] = (("armed", _armed),)


def switch_changes(venue: str) -> tuple[list[Item], list[dict]]:
    """``(items, unknown)``: the padlock a switch away from ``venue`` would close.

    The phone's venue menu reads it before the tap (ADR 070 amendment 2026-11-13); a check that cannot be
    read is in ``unknown``, never "nothing there"."""
    return _read(venue, SWITCH_READERS)


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
