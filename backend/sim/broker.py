"""Sim practice ledger facade -- the Sim venue's ``practice.broker`` instance (ADR 020).

The engine lives in ``backend/practice/``; this module keeps the module-level
API every existing caller uses (``sim.execution``, ``sim.feed``,
``ibkr.orders``, ``sim.account_hooks``, the tests) by delegating each call to
``practice.broker.for_venue("sim")``. Fills follow ``sim.fill_model`` and are
always estimates: each filled row carries ``fill_estimated=True`` and a
``fill_basis`` so the desk can tell a practice fill from a historical print
(architecture/practice-fills.md). Never talks to IBKR.

The account is scratch and follows the replay (ADR 020 decision 3): the clock
calls ``unwind_to`` when the playhead moves back (``sim.market``), and the
replay selection calls ``reset_scratch_account`` when the replay is unloaded
or another one is loaded (``sim.history_playback`` / ``sim.replay``).
"""
from __future__ import annotations

import logging
from typing import Any

from constants_practice import PRACTICE_VENUE_SIM
from practice.broker import PracticeBroker, notify_watch  # noqa: F401 -- re-exported
from practice.ledger import Ledger

logger = logging.getLogger(__name__)


def _sim() -> PracticeBroker:
    from practice.broker import for_venue

    return for_venue(PRACTICE_VENUE_SIM)


def reset_for_tests() -> None:
    """Test isolation resets every practice venue, not only Sim (one process, one cache dir)."""
    from practice.broker import reset_for_tests as _reset

    _reset()


def place(
    symbol: str,
    side: str,
    qty: float,
    order_type: str = "MKT",
    limit_price: float | None = None,
    stop_price: float | None = None,
    outside_rth: bool = False,
    order_id: int | None = None,
    protective: bool = False,
    source: str = "manual",
    bot_id: str | None = None,
) -> dict[str, Any]:
    """Place a practice order on the loaded replay (see ``PracticeBroker.place``)."""
    return _sim().place(
        symbol, side, qty, order_type,
        limit_price=limit_price, stop_price=stop_price, outside_rth=outside_rth,
        order_id=order_id, protective=protective, source=source, bot_id=bot_id,
    )


def cancel(order_id: int) -> dict[str, Any]:
    return _sim().cancel(order_id)


def replace(
    order_id: int,
    limit_price: float | None = None,
    stop_price: float | None = None,
) -> dict[str, Any]:
    return _sim().replace(order_id, limit_price=limit_price, stop_price=stop_price)


def open_orders() -> list[dict[str, Any]]:
    return _sim().working_orders()


def working_orders() -> list[dict[str, Any]]:
    return _sim().working_orders()


def closed_orders(limit: int | None = None) -> list[dict[str, Any]]:
    return _sim().closed_orders(limit)


def positions() -> list[dict[str, Any]]:
    return _sim().positions()


def account_summary() -> dict[str, Any]:
    return _sim().account_summary()


def try_fill_working(symbol: str, prints: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """Match resting orders for ``symbol`` against later replay prints, oldest first."""
    return _sim().try_fill_working(symbol, prints)


def working_symbols() -> list[str]:
    return _sim().working_symbols()


def snapshot() -> dict[str, Any]:
    return _sim().snapshot()


def unwind_to(ts: float) -> int:
    """Sim time travel: every order and fill after ``ts`` never happened.

    The feed's fill cursor moves back with it, so the tape from ``ts`` on is
    matched again against whatever is still resting -- the re-played stretch is
    never skipped. Returns how many ledger events were dropped.
    """
    dropped = _sim().unwind_to(ts)
    from sim import feed as _feed

    _feed.rewind_fill_cursor(ts)
    return dropped


def reset_scratch_account(reason: str) -> None:
    """The replay was unloaded or another one loaded: the Sim account starts over.

    Keeps the operator's starting cash; the account is re-created at the
    playhead so its practice day is the replay's day. Lock-free by design --
    the callers hold the replay selection locks (history -> capture order), so
    this never reads the selection back (``PracticeBroker.reset`` would, via
    its snapshot). Never raises: the replay engine must not die over scratch
    bookkeeping, but the failure is logged loud.
    """
    try:
        broker = _sim()
        broker.ledger = Ledger(broker.ledger.starting_cash, created_ts=broker.reference.now_ts())
        from sim import feed as _feed

        _feed.reset_fill_cursor()
    except Exception:
        logger.exception("SIM: scratch account reset failed (%s)", reason)
        return
    logger.info("SIM: scratch account starts over -- %s", reason)


_LEDGER_VIEWS = {
    "_working": lambda ledger: ledger._working,
    "_closed": lambda ledger: ledger._closed,
    "_positions": lambda ledger: ledger._positions,
    "_marks": lambda ledger: ledger._marks,
    "_cash": lambda ledger: ledger.cash,
    "_realized": lambda ledger: ledger.realized,
}


def __getattr__(name: str) -> Any:
    """Legacy readers of the old module state (``_working`` and friends) see the Sim ledger."""
    view = _LEDGER_VIEWS.get(name)
    if view is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return view(_sim().ledger)
