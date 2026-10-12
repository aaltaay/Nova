"""The bot's trade for an admitted trigger: what ``bot-session.json``'s ``trade`` carries from the start.

Moved out of ``admit`` (which decides whether a trigger is taken) when the trade gained its two halves
(#681, #845): ``target2`` and ``target1_fraction`` from the setup -- null sells every share at target 1,
as before -- the second target's order id, ``halves`` (each sale, ``halves.py``) and ``entry_qty`` (the
shares the entry bought; ``qty`` is the shares the trade still holds). The runner manages it from here.
"""
from __future__ import annotations

from typing import Any

from bot.first_pullback.admit import setup_of, triggered_at
from bot.first_pullback.short_side import side_of
from constants_bot import SIDE_SHORT


def _price(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out > 0 else None


def trade(event: dict[str, Any], row: dict[str, Any], *, qty: int, size_text: str | None = None,
          sized: dict[str, Any] | None = None) -> dict[str, Any]:
    """The bot's trade for an admitted trigger (``bot-session.json``'s ``trade``). A short's entry is the
    price its size was read at (``short_side.price``: the ask under SSR), and its risk runs up to its buy stop."""
    from bot.entry_rules import venue_day
    from bot.gates import current_venue
    from bot.replay_desk import desk as replay_desk
    from bot.sleeve import of as sleeve_of

    setup = event["setup"]
    side = side_of(event)
    entry, stop = float(setup["entry"]), float(setup["stop"])
    risk = float(setup["risk"])
    if side == SIDE_SHORT and sized and sized.get("limit") is not None:
        entry = float(sized["limit"])
        risk = round(stop - entry, 4)
    return {
        "setup_id": str(event.get("setup_id") or ""), "setup_type": setup_of(event), "side": side,
        "symbol": str(event.get("symbol") or "").upper(), "venue": current_venue(),
        "venue_day": venue_day(), "template_id": event.get("template_id"),
        "template_rev": event.get("template_rev"), "template_name": event.get("template_name"),
        "state": "entering", "qty": float(qty), "size_text": size_text, "trigger": setup.get("trigger"),
        "trigger_price": setup.get("trigger_price"), "triggered_at": triggered_at(event),
        "entry_planned": entry, "entry_scanned": float(setup["entry"]), "stop": stop,
        "target1": float(setup["target1"]), "risk": risk,
        # Two halves: null ``target2`` sells every share at target 1 (the setup scanners' contract, #845).
        "target2": _price(setup.get("target2")), "target1_fraction": setup.get("target1_fraction"),
        "target2_order_id": None, "halves": [], "entry_qty": None,
        "priced_at_ask": bool((sized or {}).get("priced_at_ask")), "ssr": (sized or {}).get("ssr"),
        "entry_order_id": None, "target_order_id": None, "stop_order_id": None,
        "stop_leg_at": None, "entry_sent_ts": None, "entry_ttl_sec": int(sleeve_of(row)["working_ttl_sec"]),
        "entry_cancel_ts": None, "entry_fill_price": None, "entry_filled_ts": None,
        "exit_order_id": None, "exit_attempt": 0, "exit_sent_ts": None,
        "exit_limit": None, "exit_protective": False, "exit_why": None, "exit_price": None,
        "exit_reason": None, "closed_ts": None, "slippage": None, "r": None, "note": None,
        # The Sim replay it was made on (ADR 052): it is managed only while the desk shows that replay.
        "replay_key": (replay_desk() or {}).get("key"),
    }
