"""Load the order path before the first order needs it (operator report 2026-10-14, GLND order 247).

The order path imports these modules inside its functions, so the first order after every backend
start loaded them while the operator waited: 35 to 170 ms from the click to the venue, against a
20 ms median for every later order. Order 247, a $4.00 bid, reached Paper 97 ms after the click --
after the $4.00 offer had gone -- and rested; its reply waited another 96 ms on the journal's.
``warm_order_path`` imports them and builds the Paper broker (its ledger is read from disk) at
startup, off the request loop and before IBKR is asked to connect (``app_lifespan``): a Paper or
Live order is refused until IBKR's feed or Gateway answers, so none can arrive before this is done.
``tests/test_execution_warm.py`` places a Paper order in a fresh interpreter and fails, naming the
module, when the first order still imports one this list does not.
"""
from __future__ import annotations

import logging
from importlib import import_module

from constants_practice import PRACTICE_VENUE_PAPER

logger = logging.getLogger(__name__)

# In the order a first Paper / Sim order reaches them.
ORDER_PATH_MODULES = (
    "short_sale.door",            # the short check's door and its rules, before the lock
    "short_sale.check",
    "execution.practice_checks",  # the session gate and validation: the practice venue's checks
    "kill_switch",                # the kill switch, read before any spend
    "loss_limit.gate",            # the daily loss limit's No new buys, after validation (ADR 056)
    "loss_limit.settings",
    "loss_limit.state",
    "sim.execution",              # the practice send
    "practice.broker",            # the practice venue and its ledger file
    "practice.persist",
    "short_sale.ssr_fill",        # the practice fill's SSR rule
    "execution.sent_by",          # the receipt's who-sent-it and closed-order row
    "execution.closed_blotter",
    "journal.db",                 # the fill's journal rows, written before the reply
    "journal.flatten_close",
    "journal.net_pnl",
    "journal.round_trip",
)
PAPER_BROKER = "practice.broker.for_venue(paper)"


def warm_order_path() -> list[str]:
    """Import every module of ``ORDER_PATH_MODULES`` and build the Paper broker; returns what failed (each
    logged). The Paper broker exists on every desk: its matcher runs whatever the venue."""
    failed: list[str] = []
    for name in ORDER_PATH_MODULES:
        try:
            import_module(name)
        except Exception:
            # The first order then imports it itself, as before: slower, never wrong.
            logger.exception("execution: could not load %s before the first order", name)
            failed.append(name)
    try:
        import_module("practice.broker").for_venue(PRACTICE_VENUE_PAPER)
    except Exception:
        logger.exception("execution: could not open the Paper account before the first order")
        failed.append(PAPER_BROKER)
    return failed
