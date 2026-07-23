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
from hod_momo_models import AlertObject, alert_to_dict

logger = logging.getLogger(__name__)


async def flush_consolidated_loop() -> None:
    """Emit expired same-symbol consolidation buckets."""
    while True:
        try:
            await asyncio.sleep(1.0)
            state = _state.get_state()
            now = time.time()
            to_emit: list[AlertObject] = []
            for symbol in list(state.pending_consolidation.keys()):
                bucket = state.pending_consolidation[symbol]
                ready = [alert for emit_ts, alert in bucket if now >= emit_ts]
                state.pending_consolidation[symbol] = [
                    (emit_ts, alert)
                    for emit_ts, alert in bucket
                    if now < emit_ts
                ]
                if not ready:
                    continue
                # Warrior consolidates bursts of the *same* strategy. Collapsing
                # all strategies into one row drops Former Momo when Low Float
                # also fires in the same window — emit one primary per strategy_id.
                by_strategy: dict[int, list[AlertObject]] = {}
                for alert in ready:
                    by_strategy.setdefault(int(alert.strategy_id), []).append(alert)
                for group in by_strategy.values():
                    if len(group) == 1:
                        to_emit.append(group[0])
                        continue
                    primary = group[-1]
                    primary.consolidation_count = len(group)
                    primary.consolidated_ids = [alert.id for alert in group[:-1]]
                    first_ts = min((alert.created_ts or 0.0) for alert in group) or now
                    last_ts = max((alert.created_ts or 0.0) for alert in group) or now
                    span = int(round(max(0.0, last_ts - first_ts)))
                    primary.consolidation_span_sec = max(1, span) if span > 0 else 1
                    to_emit.append(primary)

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
            _persist.flush_pending_alert_save()
            _persist.flush_pending_highs_save()
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
