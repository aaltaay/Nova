"""Background TTL and commission-hold polls. Spawned from app_lifespan."""
from __future__ import annotations

import asyncio
import logging

from constants_bot import BOT_COMMISSION_POLL_SEC, BOT_TTL_POLL_SEC

logger = logging.getLogger(__name__)


async def ttl_loop() -> None:
    from bot.ttl import cancel_due

    while True:
        try:
            await cancel_due()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("bot ttl loop failed")
        await asyncio.sleep(BOT_TTL_POLL_SEC)


async def commission_loop() -> None:
    """#564: re-read the day P&L meter, whose Live read keeps the commission hold current.

    The loss breakers used to drive this read every second (ADR 056 removed them); the hold still
    needs it, or a failed commission read would never be noticed (nor a recovered one released)."""
    from bot.day_pnl import read_account_day_pnl

    while True:
        try:
            read_account_day_pnl()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("bot commission hold loop failed")
        await asyncio.sleep(BOT_COMMISSION_POLL_SEC)
