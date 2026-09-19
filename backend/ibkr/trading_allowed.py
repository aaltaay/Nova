"""Single source of truth for whether Nova may place (looks vs is).

Owner: ibkr.safety spend gates + this snapshot. UI padlock / Activate / ticket
and API place all read this -- not three priority locks.
Invalidation: IBKR connect generation, env spend flags, broker account kind.
schema_version: n/a (derived; nothing persisted).

PIN unlock stays a desk-session affordance on the client. It is AND-ed onto
this snapshot in frontend/src/ibkr/tradingAllowed.ts. Flatten / KILL / cancel
remain protective and do not use this helper to refuse an exit.
"""
from __future__ import annotations

from typing import Any

from ibkr.safety import assert_orders_allowed, spend_state


def evaluate_trading_allowed(
    *,
    client_enabled: bool,
    connected: bool,
    account_mode: str,
    broker_account_kind: str = "unknown",
) -> dict[str, Any]:
    """Spend + connection snapshot. Same gate as place_order."""
    spend, locked_reason = spend_state(broker_account_kind)
    ok, reason = assert_orders_allowed(
        client_enabled=client_enabled,
        connected=connected,
        account_mode=account_mode,
        broker_account_kind=broker_account_kind,
    )
    return {
        "trading_allowed": bool(ok),
        "trading_allowed_reason": None if ok else (reason or locked_reason or "orders locked"),
        "spend_status": spend,
        "spend_locked_reason": locked_reason or None,
    }


def places_allowed() -> tuple[bool, str]:
    """Wire evaluate_trading_allowed to the live IBKR client."""
    from sim.mode import is_sim_mode

    if is_sim_mode():
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
