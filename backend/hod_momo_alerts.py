"""HOD Momo consolidation, broadcast, and WebSocket client boundary."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import hod_momo_persist as _persist
import hod_momo_state as _state
from alerts.hooks import notify_hod_alert_async
from constants import HOD_MOMO_FLUSH_TICK_SEC
from hod_momo_alert_queue import take_due
from hod_momo_models import AlertObject, alert_to_dict

logger = logging.getLogger(__name__)


async def flush_consolidated_loop() -> None:
    """Emit expired same-symbol consolidation buckets."""
    while True:
        try:
            await asyncio.sleep(HOD_MOMO_FLUSH_TICK_SEC)
            state = _state.get_state()
            # momentum consolidates bursts of the *same* strategy: one row per
            # strategy_id, so Former Momo is never folded into Low Float's row.
            to_emit: list[AlertObject] = take_due(state, time.time())

            for alert in to_emit:
                state.today_alerts.insert(0, alert)
                _persist.save_alerts()
                payload = json.dumps(
                    {"type": "alert", "alert": alert_to_dict(alert)}
                )
                dead: list[Any] = []
                for ws in list(state.hod_ws_clients):
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    state.hod_ws_clients.discard(ws)
                asyncio.create_task(notify_hod_alert_async(alert_to_dict(alert)))
            # Throttled, not forced: a forced save each tick wrote the whole
            # day's file every second while alerts flowed (#553).
            _persist.flush_pending_alert_save(force=False)
            _persist.flush_pending_highs_save(force=False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("HOD Momo flush loop error: %s", exc)


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
