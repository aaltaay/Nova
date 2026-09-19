"""Sim Feed loop -- steps SIM1 tape and injects T&S / L2 / quote updates."""
from __future__ import annotations

import asyncio
import logging

from constants_sim import SIM_PRINT_SIZE, SIM_SYMBOL, SIM_TICK_INTERVAL_SEC
from sim import broker as _broker
from sim import market as _market

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


def reset_for_tests() -> None:
    stop_sim_feed()


def start_sim_feed() -> None:
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.get_running_loop().create_task(_run(), name="sim-feed")
    logger.info("SIM: feed started symbol=%s", SIM_SYMBOL)


def stop_sim_feed() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    _task = None
    logger.info("SIM: feed stopped")


def start_sim_feed_threadsafe() -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if loop.is_running():
        start_sim_feed()


def stop_sim_feed_threadsafe() -> None:
    stop_sim_feed()


async def _run() -> None:
    while True:
        try:
            tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("SIM: feed tick failed")
        await asyncio.sleep(SIM_TICK_INTERVAL_SEC)


def tick() -> dict:
    """One synchronous tape step + fill match + fan-out. Used by tests."""
    payload = _market.step()
    _broker.try_fill_working(_market.last())
    _inject(payload)
    return payload


def _inject(payload: dict) -> None:
    try:
        from ibkr.tape_stream import _push_queue

        _push_queue(SIM_SYMBOL, payload)
    except Exception:
        logger.debug("SIM: tape inject skipped", exc_info=True)

    try:
        from ibkr.depth import state as _depth_state

        book = dict(_market.book())
        book["symbol"] = SIM_SYMBOL
        _depth_state.push_book(SIM_SYMBOL, book)
    except Exception:
        logger.debug("SIM: depth inject skipped", exc_info=True)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    q = _market.quote() or {}
    last = q.get("last")
    if last is None:
        return

    async def _broadcast() -> None:
        try:
            from websocket import broadcast_trade_update

            await broadcast_trade_update(
                SIM_SYMBOL,
                float(last),
                SIM_PRINT_SIZE,
                payload.get("time"),
                q.get("volume"),
                q.get("prev_close"),
            )
        except Exception:
            logger.debug("SIM: quote inject skipped", exc_info=True)

    loop.create_task(_broadcast())
