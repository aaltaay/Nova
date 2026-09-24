"""IBKR's own second on each AllLast print (#563).

ib_async 2.1.0 (the pinned commit) builds each print in
``Wrapper.tickByTickAllLast(reqId, tickType, time, price, ...)`` as
``TickByTickAllLast(tickType, self.lastTime, price, ...)``. ``lastTime`` is
when the message reached Nova, and IBKR's ``time`` argument, the print's own
epoch second, is thrown away. So a print's ``time`` is always an arrival time.

``install(ib)`` puts a thin override on that IB's wrapper. It calls ib_async's
own method unchanged, then swaps the tick it just appended for an
``ExchangeTimedAllLast``: the same tuple, with ``time`` still the arrival time,
carrying ``exchange_time``, IBKR's whole second. The arrival time stays the
order, because the books the prints are classified against are arrival-timed
too. The override is idempotent per wrapper, issues no request and never
blocks: it runs on the IB loop inside the socket callback (ADR 010).
``exchange_second(tick)`` reads the second back, or ``None`` when the override
did not see the tick.
"""
from __future__ import annotations

import logging
from typing import Any

from ib_async.objects import TickByTickAllLast

logger = logging.getLogger(__name__)

# Set on a wrapper whose tickByTickAllLast keeps IBKR's time.
_INSTALLED = "_nova_keeps_exchange_time"
_stamp_failed_logged = False
_no_hook_logged = False


class ExchangeTimedAllLast(TickByTickAllLast):
    """ib_async's AllLast tick, plus ``exchange_time``: IBKR's epoch second for the print."""

    exchange_time: int | None = None

    @classmethod
    def from_tick(cls, tick: TickByTickAllLast, exchange_time: int | None) -> "ExchangeTimedAllLast":
        timed = cls._make(tick)
        timed.exchange_time = exchange_time
        return timed


def exchange_second(tick: Any) -> int | None:
    """IBKR's whole epoch second for this print, or ``None`` when it was not caught."""
    value = getattr(tick, "exchange_time", None)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _second(time_arg: Any) -> int | None:
    try:
        value = int(time_arg)
    except (TypeError, ValueError, OverflowError):  # maintainer: allow-swallow a time that is not a number names no second
        return None
    return value if value > 0 else None


def _stamp(wrapper: Any, req_id: int, time_arg: Any) -> None:
    """Swap the AllLast tick ib_async just appended for one that carries IBKR's second."""
    registry = getattr(wrapper, "subscriptions", None)
    ticker = registry.get_ticker(req_id) if registry is not None else None
    ticks = getattr(ticker, "tickByTicks", None)
    if not ticks:
        return  # ib_async logged the unknown request id and kept nothing
    last = ticks[-1]
    if type(last) is TickByTickAllLast:
        ticks[-1] = ExchangeTimedAllLast.from_tick(last, _second(time_arg))


def _stamp_failed(req_id: int) -> None:
    """WARNING once per process, then DEBUG: this runs per print on the IB loop."""
    global _stamp_failed_logged
    level = logging.DEBUG if _stamp_failed_logged else logging.WARNING
    _stamp_failed_logged = True
    logger.log(level, "IBKR tape: could not keep IBKR's second on an AllLast print (reqId %s); "
               "prints go on without it", req_id, exc_info=True)


def install(ib: Any) -> bool:
    """Keep IBKR's print second on this IB's AllLast ticks. True when installed (now or before)."""
    global _no_hook_logged
    wrapper = getattr(ib, "wrapper", None)
    if wrapper is None:
        return False
    if getattr(wrapper, _INSTALLED, False):
        return True
    original = getattr(wrapper, "tickByTickAllLast", None)
    if not callable(original) or not hasattr(wrapper, "subscriptions"):
        level = logging.DEBUG if _no_hook_logged else logging.WARNING
        _no_hook_logged = True
        logger.log(level, "IBKR tape: this IB wrapper has no tickByTickAllLast / registry; its prints "
                   "carry no exchange second (exchange_ts null)")
        return False

    def tickByTickAllLast(reqId, tickType, time, price, size, tickAttribLast, exchange, specialConditions):
        original(reqId, tickType, time, price, size, tickAttribLast, exchange, specialConditions)
        try:
            _stamp(wrapper, reqId, time)
        except Exception:
            # The print is kept as ib_async built it; only its exchange second is lost.
            _stamp_failed(reqId)

    wrapper.tickByTickAllLast = tickByTickAllLast
    setattr(wrapper, _INSTALLED, True)
    return True
