"""Single source of truth for whether Nova may place (looks vs is).

Owner: ibkr.safety spend gates + this snapshot. UI padlock / Activate / ticket
and API place all read this -- not three priority locks.
Invalidation: IBKR connect generation, env spend flags, broker account kind,
desk venue.
schema_version: n/a (derived; nothing persisted).

PIN unlock stays a desk-session affordance on the client. It is AND-ed onto
this snapshot in frontend/src/ibkr/tradingAllowed.ts. Flatten / KILL / cancel
remain protective and do not use this helper to refuse an exit.

ADR 020: on Paper / Sim the only gate is the ADR 018 arm latch -- the IBKR
env gates (``IBKR_ORDERS_ENABLED``, ``IBKR_LIVE_TRADING_CONFIRMED``) and the
Gateway session apply to the Live door only.
"""
from __future__ import annotations

from typing import Any

from ibkr.safety import DISARMED_REASON, armed, assert_orders_allowed, spend_state


def _on_practice_venue() -> bool:
    from sim.mode import is_practice_venue

    return is_practice_venue()


def evaluate_trading_allowed(
    *,
    client_enabled: bool,
    connected: bool,
    account_mode: str,
    broker_account_kind: str = "unknown",
) -> dict[str, Any]:
    """Spend + connection snapshot. Same gate as place_order."""
    spend, locked_reason = spend_state(broker_account_kind)
    if _on_practice_venue():
        # Fake money: the latch alone. The venue's own admission (a priced
        # replay or a fresh live last) is checked per order, not here.
        ok, reason = (True, "") if armed() else (False, DISARMED_REASON)
    else:
        ok, reason = assert_orders_allowed(
            client_enabled=client_enabled,
            connected=connected,
            account_mode=account_mode,
            broker_account_kind=broker_account_kind,
        )
        # ADR 018: `assert_orders_allowed` is source-blind, so it cannot hold the
        # arm latch -- flatten / KILL route through it and must survive a disarm.
        # The padlock snapshot is about *opening*, so it AND-s the latch here.
        if ok and not armed():
            ok, reason = False, DISARMED_REASON
    return {
        "trading_allowed": bool(ok),
        "trading_allowed_reason": None if ok else (reason or locked_reason or "orders locked"),
        "spend_status": spend,
        "spend_locked_reason": locked_reason or None,
        "armed": armed(),
    }


def places_allowed() -> tuple[bool, str]:
    """Wire evaluate_trading_allowed to the live IBKR client.

    ADR 018 splits the two reads this used to collapse. The arm latch is asked
    first and is venue-independent, so being on a practice venue is no longer
    an answer to "may I spend" -- it only decides *where* an allowed order is
    routed.
    """
    if not armed():
        return False, DISARMED_REASON
    if _on_practice_venue():
        return True, ""
    from ibkr import client as _client

    snap = evaluate_trading_allowed(
        client_enabled=_client.is_enabled(),
        connected=_client.is_ready(),
        account_mode=_client.account_mode(),
        broker_account_kind=_client.broker_account_kind(),
    )
    reason = str(snap.get("trading_allowed_reason") or "")
    return bool(snap.get("trading_allowed")), reason


def require_places_allowed() -> None:
    from bot.errors import BotError
    from constants_bot import BOT_REASON_TRADING_LOCKED

    ok, reason = places_allowed()
    if not ok:
        raise BotError(
            reason or "trading is not allowed -- spend or Gateway gate",
            409,
            BOT_REASON_TRADING_LOCKED,
        )
