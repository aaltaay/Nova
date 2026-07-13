"""
IBKR trading safety — SINGLE SOURCE OF TRUTH for whether money can move.

Every place_order / place_bracket_order path MUST call `assert_orders_allowed()`.
Cancel is intentionally softer (enabled + connected) so accidental live orders
from TWS can still be flattened.

Env gates (all must pass for a LIVE buy/sell):
  1. IBKR_ENABLED=true
  2. Connected to Gateway
  3. IBKR_ORDERS_ENABLED=true          ← master kill switch (default OFF)
  4. If gateway mode is live:
       IBKR_LIVE_TRADING_CONFIRMED=true

IBKR_GATEWAY_MODE=paper|live chooses which Gateway port to connect for
market data. It does NOT authorize spending. You can be on live Gateway
for L1/L2 while orders stay locked.
"""
from __future__ import annotations

import logging
import os
from typing import Literal

from constants import IBKR_GATEWAY_MODE_DEFAULT, IBKR_ORDERS_ENABLED_DEFAULT

logger = logging.getLogger(__name__)

GatewayMode = Literal["paper", "live"]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes")


def gateway_mode() -> GatewayMode:
    """Which IB Gateway login/port Nova targets (data connection)."""
    raw = os.environ.get("IBKR_GATEWAY_MODE", IBKR_GATEWAY_MODE_DEFAULT).strip().lower()
    return "live" if raw == "live" else "paper"


def orders_enabled() -> bool:
    """Master kill switch — default OFF so a live Gateway cannot spend."""
    return _env_bool("IBKR_ORDERS_ENABLED", IBKR_ORDERS_ENABLED_DEFAULT)


def live_trading_confirmed() -> bool:
    """Second key for live money — must be explicit even if orders_enabled."""
    return _env_bool("IBKR_LIVE_TRADING_CONFIRMED", False)


def status_snapshot() -> dict:
    """Fields for /api/ibkr/status — UI + operators."""
    mode = gateway_mode()
    orders_on = orders_enabled()
    live_ok = live_trading_confirmed()
    if not orders_on:
        spend = "locked"
    elif mode == "live" and not live_ok:
        spend = "locked_live_unconfirmed"
    elif mode == "live":
        spend = "live_armed"
    else:
        spend = "paper_armed"
    return {
        "gateway_mode": mode,
        "orders_enabled": orders_on,
        "live_trading_confirmed": live_ok,
        "spend_status": spend,
    }


def assert_orders_allowed(*, client_enabled: bool, connected: bool, account_mode: str) -> tuple[bool, str]:
    """
    Returns (ok, reason). Sole gate used by place_order / place_bracket_order.
    """
    if not client_enabled:
        return False, "IBKR_ENABLED is not set"
    if not connected:
        return False, "IBKR not connected"
    if not orders_enabled():
        return False, (
            "IBKR_ORDERS_ENABLED is false — orders locked "
            "(market data / Level 2 still allowed)"
        )
    # Prefer detected account mode from the live connection when available.
    mode = account_mode if account_mode in ("paper", "live") else gateway_mode()
    if mode == "live" and not live_trading_confirmed():
        return False, "Live trading requires IBKR_LIVE_TRADING_CONFIRMED=true"
    return True, ""


def assert_cancel_allowed(*, client_enabled: bool, connected: bool) -> tuple[bool, str]:
    """Cancel is allowed whenever connected — protective, not spending."""
    if not client_enabled:
        return False, "IBKR_ENABLED is not set"
    if not connected:
        return False, "IBKR not connected"
    return True, ""
