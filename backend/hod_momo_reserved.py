"""HOD Momo's reserved block (ADR 008; ADR 044, amended 2026-10-06): who takes its slots, in order. Pure.

``HOD_MOMO_FORMER_MOMO_MAX_SLOTS`` slots of the active set are kept off the live movers' round-robin:

1. the stocks the bot buys (``bot_symbols``: Buy set to Bot on the desk's venue -- the bot can only buy
   what a lane reads), reason ``bot_buy``;
2. today's hot list (``hot_symbols``) in list order, reason ``hot_list``;
3. the manual Former Momo list (``priority_symbols``) in what is left, reason ``former_momo``.

A name on two lists counts once, as the first's. A name past the block is left out with reason
``bot_buy_over_reserved`` / ``hot_list_over_reserved`` / ``former_momo_over_cap``, and one IBKR cannot
stream with ``bot_buy_l1_blocked`` / ``hot_list_l1_blocked`` (it frees its slot); such a name still competes
for a mover's slot on its own move. ``hod_momo_active.build_active_set`` owns the state and calls this.
"""
from __future__ import annotations

from typing import Callable, Iterable

from constants_hot_list import (
    BOT_BUY_ACTIVE_L1_BLOCKED,
    BOT_BUY_ACTIVE_OVER_RESERVED,
    BOT_BUY_ACTIVE_REASON,
    HOT_LIST_ACTIVE_L1_BLOCKED,
    HOT_LIST_ACTIVE_OVER_RESERVED,
    HOT_LIST_ACTIVE_REASON,
)
from hod_momo_active_rank import ordered_unique

FORMER_MOMO_REASON = "former_momo"
FORMER_MOMO_OVER_CAP = "former_momo_over_cap"


def admit_reserved(*, bot_symbols: Iterable[str] | None, hot_symbols: Iterable[str] | None,
                   priority_symbols: Iterable[str] | None, slots: int, take: Callable[[str, str], bool],
                   blocked: Callable[[str], bool]) -> dict[str, str]:
    """Offer the block's names to ``take(symbol, reason)`` (True when it admitted the name) in the order
    above, at most ``slots`` of them. Returns the reason for each name the block left out."""
    left_out: dict[str, str] = {}
    taken = 0
    bots = ordered_unique(bot_symbols or [])
    hot = [s for s in ordered_unique(hot_symbols or []) if s not in set(bots)]
    for names, over, no_line, why in ((bots, BOT_BUY_ACTIVE_OVER_RESERVED, BOT_BUY_ACTIVE_L1_BLOCKED,
                                       BOT_BUY_ACTIVE_REASON),
                                      (hot, HOT_LIST_ACTIVE_OVER_RESERVED, HOT_LIST_ACTIVE_L1_BLOCKED,
                                       HOT_LIST_ACTIVE_REASON)):
        for s in names:
            if taken >= slots:
                left_out[s] = over
            elif blocked(s):
                left_out[s] = no_line
            elif take(s, why):
                taken += 1
    first = set(bots) | set(hot)
    for s in ordered_unique(priority_symbols or []):
        if s in first:
            continue
        if taken >= slots:
            left_out[s] = FORMER_MOMO_OVER_CAP
        elif take(s, FORMER_MOMO_REASON):
            taken += 1
    return left_out
