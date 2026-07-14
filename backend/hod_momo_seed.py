"""IBKR volume-scanner seeds for HOD Momo focus universe.

Warrior HOD catches mid-day runners that are hot on volume but not always in
the Top % Gainer list. This loop polls IBKR HOT_BY_VOLUME / TOP_VOLUME_RATE /
MOST_ACTIVE and feeds symbols into hod_momo_universe.set_seed_symbols.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

from constants import HOD_MOMO_SEED_REFRESH_SEC

logger = logging.getLogger(__name__)


async def seed_refresh_loop(get_provider: Callable[[], str]) -> None:
    """Background task: refresh volume-seed symbols when discovery=ibkr."""
    import hod_momo_universe as _uni
    from ibkr import discovery as _discovery

    while True:
        try:
            await asyncio.sleep(HOD_MOMO_SEED_REFRESH_SEC)
            if (get_provider() or "").strip().lower() != "ibkr":
                continue
            symbols = await _discovery.scan_hod_momentum_seeds()
            _uni.set_seed_symbols(symbols)
            if symbols:
                logger.info("HOD Momo seeds: %d symbols from IBKR volume scans", len(symbols))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("HOD Momo seed refresh failed: %s", exc)
