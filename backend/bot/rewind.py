"""Practice rewind notices for bots (ADR 020 decision 3, second pass 2026-09-21).

When the Sim scratch account unwinds behind a backward playhead move, every
practice order and fill after the new playhead never happened. A bot that
remembers placing them would be trading a ledger that no longer exists, so
Nova tells it twice:

* **push** -- a ``practice_rewind`` entry on the bot audit stream
  (``ws://127.0.0.1:8000/ws/bot/audit``, the channel that already carries
  breaker and TTL events), with the event under ``inputs``;
* **poll** -- ``last_rewind`` on ``GET /api/bot/session``.

Either way the instruction is the same: re-read positions and working orders
from the practice account (``/api/practice/account?venue=sim``,
``/api/ibkr/positions``) and never trust memory over the ledger.

Process-local on purpose: the scratch account itself does not survive a
restart, so a stale notice would only mislead. Never raises -- a venue must
not fail its own time travel over bot bookkeeping.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants_bot import BOT_AUDIT_ACTION_PRACTICE_REWIND

logger = logging.getLogger(__name__)

_last: dict[str, Any] | None = None


def build_event(
    *,
    venue: str,
    playhead_ts: float,
    dropped_orders: int,
    dropped_fills: int,
) -> dict[str, Any]:
    """The wire shape, shared by the audit entry and the session payload."""
    return {
        "venue": str(venue),
        "playhead_ts": float(playhead_ts),
        "dropped_orders": int(dropped_orders),
        "dropped_fills": int(dropped_fills),
        "ts": time.time(),
    }


def publish(
    *,
    venue: str,
    playhead_ts: float,
    dropped_orders: int,
    dropped_fills: int,
) -> dict[str, Any]:
    """Record the rewind for pollers and push it to audit-stream subscribers."""
    global _last
    event = build_event(
        venue=venue,
        playhead_ts=playhead_ts,
        dropped_orders=dropped_orders,
        dropped_fills=dropped_fills,
    )
    _last = event
    try:
        from bot.audit import record as audit

        audit(action=BOT_AUDIT_ACTION_PRACTICE_REWIND, outcome="ok", inputs=dict(event))
    except Exception:
        logger.warning("BOT: practice_rewind audit push failed", exc_info=True)
    return dict(event)


def last() -> dict[str, Any] | None:
    """The most recent rewind this process published, or ``None``."""
    return dict(_last) if _last is not None else None


def reset_for_tests() -> None:
    global _last
    _last = None
