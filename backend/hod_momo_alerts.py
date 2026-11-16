"""HOD Momo consolidation, broadcast, and WebSocket client boundary.

Every ``/ws/hod-momo`` frame but the keep-alive ping is sent from here, and the
live list changes only while ``HodMomoState.feed_lock`` is held (#800):
``emit_due_alerts`` adds and sends the due alerts, ``restate_feed`` replaces the
list (the 04:00 rollover, the explicit Clear) and restates it to every desk, and
``add_desk`` sends a new desk the whole list before any alert frame can reach it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, TypeVar

import hod_momo_persist as _persist
import hod_momo_state as _state
from alerts.hooks import notify_hod_alert_async
from constants import HOD_MOMO_FLUSH_TICK_SEC
from hod_momo_alert_queue import take_due
from hod_momo_models import AlertObject, alert_to_dict

logger = logging.getLogger(__name__)

_Answer = TypeVar("_Answer")


async def flush_consolidated_loop() -> None:
    """Emit expired same-symbol consolidation buckets."""
    while True:
        try:
            await asyncio.sleep(HOD_MOMO_FLUSH_TICK_SEC)
            await emit_due_alerts()
            # Throttled, not forced: a forced save each tick wrote the whole
            # day's file every second while alerts flowed (#553).
            _persist.flush_pending_alert_save(force=False)
            _persist.flush_pending_highs_save(force=False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("HOD Momo flush loop error: %s", exc)


async def emit_due_alerts() -> list[AlertObject]:
    """Add the queued alerts now due to today's list and send each one to every desk.

    The whole tick holds the feed lock: a rollover or Clear lands before the tick
    or after it, never between its alerts, so none of them joins a list that was
    just replaced or reaches a desk behind the list that replaced it.
    """
    state = _state.get_state()
    async with state.feed_lock:
        # momentum consolidates bursts of the *same* strategy: one row per
        # strategy_id, so Former Momo is never folded into Low Float's row.
        due: list[AlertObject] = take_due(state, time.time())
        for alert in due:
            state.today_alerts.insert(0, alert)
            _persist.save_alerts()
            await _send_to_desks(json.dumps({"type": "alert", "alert": alert_to_dict(alert)}))
            asyncio.create_task(notify_hod_alert_async(alert_to_dict(alert)))
    return due


async def restate_feed(change: Callable[[], _Answer]) -> _Answer:
    """Run ``change`` on today's list; when it answers truthy, restate the list to every desk.

    The one way an open desk's list is replaced: the 04:00 rollover (``change``
    answers whether the session rolled) and ``DELETE /api/hod-momo/alerts``. An
    ``alert`` frame only adds to a desk's list, so a reset that is not restated
    leaves the old day on screen (04:00 rollover, 2026-10-19). Both steps hold the
    feed lock: each desk gets the ``initial`` frame after every alert added before
    the change and before every alert added after it.
    """
    async with _state.get_state().feed_lock:
        answer = change()
        if answer:
            await _send_to_desks(json.dumps(get_ws_initial_payload()))
    return answer


async def add_desk(ws: Any) -> None:
    """Join ``ws`` to the feed and send it today's whole list, under the feed lock.

    No alert frame can reach the desk ahead of the list it adds to.
    """
    state = _state.get_state()
    async with state.feed_lock:
        state.hod_ws_clients.add(ws)
        await ws.send_text(json.dumps(get_ws_initial_payload()))


async def _send_to_desks(text: str) -> None:
    """Send one frame to every open desk. A desk whose send fails is dropped; the rest still get it."""
    state = _state.get_state()
    dead: list[Any] = []
    for ws in list(state.hod_ws_clients):
        try:
            await ws.send_text(text)
        except Exception:
            logger.debug("HOD Momo: a desk's send failed; dropping it", exc_info=True)
            dead.append(ws)
    for ws in dead:
        state.hod_ws_clients.discard(ws)


def add_ws_client(ws: Any) -> None:
    _state.get_state().hod_ws_clients.add(ws)


def remove_ws_client(ws: Any) -> None:
    _state.get_state().hod_ws_clients.discard(ws)


def get_ws_clients() -> set:
    return _state.get_state().hod_ws_clients


def get_today_alerts() -> list[dict]:
    return [alert_to_dict(alert) for alert in _state.get_state().today_alerts]


def clear_today_alerts() -> dict:
    state = _state.get_state()
    cleared = len(state.today_alerts)
    state.today_alerts = []
    state.pending_consolidation = {}
    state.consolidation_bursts = {}
    _persist.save_alerts(force=True)
    logger.info(
        "HOD Momo: cleared %d alerts for today (user request)",
        cleared,
    )
    from hod_momo_session import current_date_et

    return {
        "cleared": cleared,
        "date": current_date_et(),
        "alerts": [],
        "total": 0,
    }


def get_ws_initial_payload() -> dict:
    alerts = get_today_alerts()
    return {
        "type": "initial",
        "alerts": alerts,
        "total": len(alerts),
    }
