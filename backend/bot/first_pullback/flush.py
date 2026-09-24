"""The template's flush exit, for Nova's bot's trade (ADR 034).

The setup scanner reads the tape flow on every triggered setup through its
scoring window (``Lane.read_trades``) and keeps the newest reading with the
template's flush rule (``SetupEngine.flow_reading``). This applies that rule --
``tape_flow.flush_action``, the one the scoring exit follows -- to the bot's own
trade, from its own fill: ``exit`` closes it at the bid like a stop, ``tighten``
moves the watched stop up. The pre-registered rule (``off``) does nothing.

A reading older than ``TAPE_FLOW_READING_STALE_SEC`` is not acted on; no
reading (the symbol's tape is not held, the scanner restarted) is no flush --
the stop and the time stop still hold. Reads only; the runner sends the orders.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from constants_setups import FLUSH_EXIT_OFF, TAPE_FLOW_READING_STALE_SEC
from setup_scanner.tape_flow import FlushPolicy, flush_action

logger = logging.getLogger(__name__)
_warned = False


def reading(setup_id: str) -> dict[str, Any] | None:
    """The setup scanner's newest flow reading on this setup, with its template's rule."""
    global _warned
    try:
        from setup_scanner.engine import get_engine

        return get_engine().flow_reading(setup_id)
    except Exception:
        if not _warned:
            _warned = True
            logger.warning("first-pullback bot: the tape flow is unread -- no flush exit until it answers",
                           exc_info=True)
        return None


def decide(trade: dict[str, Any], now: float, *, last: float | None,
           read: Callable[[str], dict[str, Any] | None] | None = None) -> dict[str, Any] | None:
    """``{"action": "exit" | "tighten", "stop"?, "score", "why"}`` when the template's flush rule acts, else None."""
    got = (read or reading)(str(trade.get("setup_id") or ""))
    if not got:
        return None
    raw = got.get("policy") or {}
    policy = FlushPolicy(mode=str(raw.get("mode") or FLUSH_EXIT_OFF), hold_sec=float(raw.get("hold_sec") or 0),
                         trail_r=float(raw.get("trail_r") or 0), min_r=raw.get("min_r"))
    at = float(got.get("ts") or 0)
    if not policy.active or now - at > TAPE_FLOW_READING_STALE_SEC:
        return None
    fill, risk, filled = trade.get("entry_fill_price"), trade.get("risk"), trade.get("entry_filled_ts")
    if fill is None or not risk or filled is None:
        return None
    price = last if last is not None else got.get("price")
    act = flush_action(policy, label=got.get("label"), price=price, ts=at, entry=float(fill), risk=float(risk),
                       stop=float(trade["stop"]), since=float(filled))
    if act is None:
        return None
    score = got.get("score")
    said = f"flush on the tape (score {score:+.2f})" if isinstance(score, (int, float)) else "flush on the tape"
    if act["action"] == "exit":
        act["why"] = f"{said} at {price:g} -- the template gets out"
    else:
        act["why"] = f"{said} at {price:g} -- the stop moves up to {act['stop']:g}"
    act["score"] = score
    return act


def reset_for_tests() -> None:
    global _warned
    _warned = False
