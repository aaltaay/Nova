"""The lanes' tick, every ``LANES_BOTS_TICK_SEC`` (ADR 071). Registered as ``line_lanes`` in ``app_runtime_tasks``.

Each tick, in order: the bots' lane is chosen again (``bots.tick``), every lane's line that is down is asked for
again (``lanes.ensure``), and the lanes' recording starts and stops what the lanes watch (``recording.sync``). Each
step's failure is logged and costs only that step. ``install`` hooks the recording into every lane move: its
recordings end before a stock's lines end, and start once a lane is on a stock.
"""
from __future__ import annotations

import asyncio
import logging

from line_lanes import bots, lanes, recording
from line_lanes.constants_lanes import LANES_BOTS_TICK_SEC

logger = logging.getLogger(__name__)


def install() -> None:
    lanes.on_before_close(recording.stop_for)
    lanes.on_after_move(recording.sync)


async def tick() -> None:
    from ibkr import client

    try:
        await bots.tick()
    except Exception:
        logger.exception("LANES: the bots' lane could not be chosen; it stays where it is")
    if client.is_ready():
        try:
            await lanes.ensure()
        except Exception:
            logger.exception("LANES: the lanes' lines could not be asked for again")
    try:
        await recording.sync()
    except Exception:
        logger.exception("LANES: the lanes' recording could not be brought up to date")


async def run() -> None:
    install()
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("LANES: a tick failed")
        await asyncio.sleep(LANES_BOTS_TICK_SEC)
