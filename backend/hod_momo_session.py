"""HOD Momo session initialization and rollover shell (Phase 10)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import hod_momo_metrics as _metrics
import hod_momo_persist as _persist
import hod_momo_state as _state
from constants import (
    HOD_MOMO_SESSION_RESET_HOUR_ET,
    HOD_MOMO_SESSION_RESET_POLL_SEC,
)

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")


def current_date_et() -> str:
    return datetime.now(_ET).strftime("%Y-%m-%d")


def check_and_reset_session() -> bool:
    """Reset per-session state after the ET date rolls past the reset hour."""
    state = _state.get_state()
    now_et = datetime.now(_ET)
    if now_et.hour < HOD_MOMO_SESSION_RESET_HOUR_ET:
        return False
    current = now_et.strftime("%Y-%m-%d")
    if not state.session_date:
        state.session_date = current
        return False
    if current == state.session_date:
        return False

    previous = state.session_date
    if state.today_alerts:
        try:
            _persist.archive_session_alerts(previous)
            logger.info(
                "HOD Momo: archived %d alerts to %s before session rollover",
                len(state.today_alerts),
                previous,
            )
        except Exception:
            logger.warning(
                "HOD Momo: failed to archive alerts for %s",
                previous,
                exc_info=True,
            )

    logger.info("HOD Momo: session rollover → %s (was %s)", current, previous)
    state.session_date = current
    state.today_alerts = []
    state.session_highs = {}
    state.session_high_seeded = set()
    state.day_highs = {}
    state.session_high_source = {}
    state.session_high_raised_ts = {}
    state.cooldown = {}
    state.pending_consolidation = {}
    state.price_buffer = {}
    state.surge_seeded = set()
    state.pending_surge_seed = set()
    state.last_trade_ts = None
    _metrics.clear_volume_buffers()
    try:
        import hod_momo_active as _active

        _active.clear_session_state()
    except Exception:
        logger.warning("HOD Momo: active-set session clear failed", exc_info=True)
    try:
        import hod_momo_session_focus as _focus

        _focus.clear_session_focus(persist=True)
    except Exception:
        logger.warning("HOD Momo: session-focus sticky clear failed", exc_info=True)
    _persist.save_alerts(force=True)
    return True


def load_state() -> None:
    """Load persisted state without treating a cold start as a new session."""
    _persist.load_persisted_state()
    state = _state.get_state()
    state.session_date = current_date_et()
    check_and_reset_session()
    logger.info(
        "HOD Momo: loaded %d alerts, %d blocked symbols, %d strategies",
        len(state.today_alerts),
        len(state.blocklist),
        len(state.configs),
    )


async def session_reset_loop() -> None:
    while True:
        try:
            await asyncio.sleep(HOD_MOMO_SESSION_RESET_POLL_SEC)
            check_and_reset_session()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("HOD Momo session reset loop error: %s", exc)
