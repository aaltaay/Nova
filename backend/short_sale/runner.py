"""The loop that runs Nova's own closes on Paper and Sim every second (``short_sale.closes``).

Registered from ``app_runtime_tasks`` as ``short_sale.closes``. ``NOVA_SHORT_RUNNER=0`` turns it off.
"""
from __future__ import annotations

import asyncio
import logging
import os

from constants_shorts import SHORT_RUNNER_ENV, SHORT_RUNNER_INTERVAL_SEC
from short_sale import closes

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return (os.environ.get(SHORT_RUNNER_ENV) or "1").strip() != "0"


async def run() -> None:
    """Background loop on the HTTP loop, beside the practice matcher."""
    while True:
        try:
            await asyncio.sleep(SHORT_RUNNER_INTERVAL_SEC)
            if enabled():
                await closes.pass_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("SHORTS: the close loop failed a pass")
