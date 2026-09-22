"""The depth line a historical replay's Level 2 holds (QA R44, 2026-09-22).

A bot fires only on a symbol whose depth line the backend holds
(``bot.eligibility.holds_depth_line``; ``409 BOT_NO_DEPTH_LINE`` otherwise). A
capture replay's Level 2 opens the ordinary depth socket, which reserves the
replay slot on a Sim desk; a historical replay's Level 2 reads the recorded
book from the snapshot instead, so nothing was reserved and every bot was
refused "open its Level 2" with that panel open. The historical panel now holds
the same replay slot while it is shown: reserved only on a replay desk, only
for the loaded historical window's symbol, and released only while it is
still a slot that no depth socket or recording uses. No IBKR line is opened,
and no book is pushed or recorded -- the slot is the fact the gate reads.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _loaded_symbol() -> str | None:
    from sim import history_playback

    spec = history_playback.status()
    return str(spec["symbol"]).upper() if spec else None


def _refusal(symbol: str) -> str | None:
    """Why this desk may not hold a replay slot for ``symbol``, or None."""
    from sim.mode import is_replay_desk

    if not is_replay_desk():
        return "not a replay desk"
    loaded = _loaded_symbol()
    if loaded != symbol:
        return f"{symbol} is not the loaded historical replay"
    return None


def hold(symbol: str) -> dict[str, Any]:
    """Reserve the replay depth slot for the loaded historical symbol."""
    from ibkr.depth import state

    sym = (symbol or "").strip().upper()
    reason = _refusal(sym)
    if reason is not None:
        return {"ok": False, "held": False, "reason": reason, "symbols": state.subscribed_symbols()}
    if not state.is_subscribed(sym):
        state.reserve_slot(sym)
        logger.info("SIM history: %s holds the replay depth slot (historical Level 2 open)", sym)
    return {"ok": True, "held": True, "reason": None, "symbols": state.subscribed_symbols()}


def release(symbol: str) -> dict[str, Any]:
    """Drop the slot when the historical Level 2 closes -- never a live line, a socket's slot or a recording's."""
    from ibkr.depth import state

    sym = (symbol or "").strip().upper()
    in_use = state.is_live(sym) or state.viewer_count(sym) > 0 or _recording(sym)
    if state.is_subscribed(sym) and not in_use:
        state.drop_slot(sym)
    return {"ok": True, "held": state.is_subscribed(sym), "reason": None, "symbols": state.subscribed_symbols()}


def _recording(symbol: str) -> bool:
    try:
        from l2 import recorder

        return bool(recorder.is_recording(symbol))
    except Exception:
        logger.warning("SIM history: recorder state unreadable for %s -- depth slot kept", symbol, exc_info=True)
        return True
