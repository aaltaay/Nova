"""Load the order path before the first order needs it (operator report 2026-10-14, GLND order 247).

The order path imports these modules inside its functions, so the first order after every backend
start loaded them while the operator waited: 35 to 170 ms from the click to the venue, against a
20 ms median for every later order. Order 247, a $4.00 bid, reached Paper 97 ms after the click --
after the $4.00 offer had gone -- and rested; its reply waited another 96 ms on the journal's.
``warm_order_path`` imports them at startup, off the request loop (``app_lifespan``).
``tests/test_execution_warm.py`` places a Paper order in a fresh interpreter and fails, naming the
module, when the first order still imports one this list does not.
"""
from __future__ import annotations

import logging
from importlib import import_module

logger = logging.getLogger(__name__)

# In the order a first Paper / Sim order reaches them.
ORDER_PATH_MODULES = (
    "short_sale.door",            # the short check's door and its rules, before the lock
    "short_sale.check",
    "execution.practice_checks",  # the session gate and validation: the practice venue's checks
    "kill_switch",                # the kill switch, read before any spend
    "bot.buy_lock",               # the buy lock, after validation
    "bot.breaker_limits",
    "sim.execution",              # the practice send
    "short_sale.ssr_fill",        # the practice fill's SSR rule
    "execution.sent_by",          # the receipt's who-sent-it and closed-order row
    "execution.closed_blotter",
    "journal.db",                 # the fill's journal rows, written before the reply
    "journal.flatten_close",
    "journal.net_pnl",
    "journal.round_trip",
)


def warm_order_path() -> list[str]:
    """Import every module of ``ORDER_PATH_MODULES``; returns the ones that failed (each logged)."""
    failed: list[str] = []
    for name in ORDER_PATH_MODULES:
        try:
            import_module(name)
        except Exception:
            # The first order then imports it itself, as before: slower, never wrong.
            logger.exception("execution: could not load %s before the first order", name)
            failed.append(name)
    return failed
