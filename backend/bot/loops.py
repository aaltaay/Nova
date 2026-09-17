"""Background TTL + breaker polls. Spawned from app_lifespan."""
from __future__ import annotations

import asyncio
import logging

from constants_bot import BOT_BREAKER_POLL_SEC, BOT_TTL_POLL_SEC

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


async def breaker_loop() -> None:
    from bot.breakers import poll_once

    while True:
        try:
            await poll_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("bot breaker loop failed")
        await asyncio.sleep(BOT_BREAKER_POLL_SEC)
