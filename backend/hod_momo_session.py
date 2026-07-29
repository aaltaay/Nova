"""HOD Momo session initialization and rollover shell (Phase 10)."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import hod_momo_metrics as _metrics
import hod_momo_persist as _persist
import hod_momo_state as _state
from constants import HOD_MOMO_SESSION_RESET_POLL_SEC
from hod_momo_models import AlertObject
from market import ET, session_key_et

logger = logging.getLogger(__name__)


def current_date_et() -> str:
    """04:00 ET-anchored session key — matches cache filenames (ADR 008)."""
    return session_key_et()


def alert_session_key(alert: AlertObject) -> str:
    """Session that owns an alert, from created_ts or ISO timestamp."""
    created_ts = float(getattr(alert, "created_ts", 0) or 0)
    if created_ts > 0:
        return session_key_et(datetime.fromtimestamp(created_ts, tz=ET))
    ts = getattr(alert, "timestamp", "") or ""
    if ts:
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(ET)
            return session_key_et(dt)
        except ValueError:
            pass
    return current_date_et()


def reconcile_loaded_alerts_to_session() -> bool:
    """Archive alerts from prior sessions that leaked into today's live store."""
    state = _state.get_state()
    current = current_date_et()
    if not state.today_alerts:
        return False

    keep: list[AlertObject] = []
    stale_by_date: dict[str, list[AlertObject]] = defaultdict(list)
    for alert in state.today_alerts:
        if alert_session_key(alert) == current:
            keep.append(alert)
        else:
            stale_by_date[alert_session_key(alert)].append(alert)

    if not stale_by_date:
        return False

    moved = sum(len(group) for group in stale_by_date.values())
    for date_str, alerts in stale_by_date.items():
        try:
            _persist.merge_archive_session_alerts(date_str, alerts)
        except Exception:
            logger.warning(
                "HOD Momo: failed to archive stale alerts to %s",
                date_str,
                exc_info=True,
            )

    state.today_alerts = keep
    logger.info(
        "HOD Momo: reconciled %d stale alert(s) out of live session %s",
        moved,
        current,
    )
    _persist.save_alerts(force=True)
    return True


def check_and_reset_session() -> bool:
    """Reset per-session state when the 04:00 ET-anchored session key rolls."""
    state = _state.get_state()
    current = current_date_et()
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
    state.approach_armed = {}
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
    reconcile_loaded_alerts_to_session()
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
