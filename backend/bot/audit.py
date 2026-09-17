"""Append-only bot audit stream."""
from __future__ import annotations

import time
from typing import Any

from bot.persist import append_audit_line, load_session, read_audit_lines

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
) -> dict[str, Any]:
    row = load_session()
    entry = {
        "timestamp": time.time(),
        "level": int(level if level is not None else row.get("level") or 0),
        "strategy": strategy if strategy is not None else row.get("strategy"),
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
    append_audit_line(entry)
    _publish(entry)
    return entry


def list_entries(*, limit: int = 200) -> list[dict[str, Any]]:
    return read_audit_lines(limit=limit)
