"""Append-only bot audit stream.

A bot trade line's outcome is one of ``BOT_TRADE_OUTCOMES`` (architecture/schema/bot.md, "Fills on the bot audit
stream"); another name is logged as an error and the line is still written.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from bot.persist import append_audit_line, load_session, read_audit_lines
from constants_bot import BOT_TRADE_AUDIT_ACTIONS, BOT_TRADE_OUTCOMES

logger = logging.getLogger(__name__)

_SUBSCRIBERS: list[Any] = []


def subscribe() -> Any:
    import asyncio

    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    _SUBSCRIBERS.append(queue)
    return queue


def unsubscribe(queue: Any) -> None:
    if queue in _SUBSCRIBERS:
        _SUBSCRIBERS.remove(queue)


def _publish(row: dict[str, Any]) -> None:
    dead: list[Any] = []
    for queue in list(_SUBSCRIBERS):
        try:
            queue.put_nowait(row)
        except Exception:
            dead.append(queue)
    for queue in dead:
        unsubscribe(queue)


def record(
    *,
    action: str,
    outcome: str,
    reason: str | None = None,
    order_id: int | None = None,
    advise_spend: float | None = None,
    inputs: dict[str, Any] | None = None,
    level: int | None = None,
    strategy: str | None = None,
    brain_session_id: str | None = None,
    fill: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if action in BOT_TRADE_AUDIT_ACTIONS and outcome not in BOT_TRADE_OUTCOMES:
        logger.error("bot audit: %s line with an outcome outside BOT_TRADE_OUTCOMES: %r", action, outcome)
    row = load_session()
    from bot.gates import current_venue

    entry = {
        "timestamp": time.time(),
        # The venue the desk was on: the daily entry cap counts one venue's entries.
        "venue": current_venue(),
        "level": int(level if level is not None else row.get("level") or 0),
        # LEGACY: the session's strategy is gone (ADR 042); null unless a caller names one.
        "strategy": strategy,
        "brain_session_id": (
            brain_session_id if brain_session_id is not None else row.get("brain_session_id")
        ),
        "action": action,
        "inputs": dict(inputs or {}),
        "reason": reason,
        "order_id": order_id,
        "advise_spend": advise_spend,
        "outcome": outcome,
    }
    if fill is not None:
        entry["fill"] = dict(fill)    # a partial or full fill: shares filled, remaining, the average (2026-10-16)
    from bot.replay_desk import audit_stamp

    stamp = audit_stamp()
    if stamp is not None:
        entry["replay"] = stamp       # a line written on a Sim replay (ADR 052): its replay and playhead
    append_audit_line(entry)
    _publish(entry)
    return entry


def list_entries(*, limit: int = 200) -> list[dict[str, Any]]:
    return read_audit_lines(limit=limit)
