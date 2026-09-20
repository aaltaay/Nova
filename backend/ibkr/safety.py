"""
IBKR trading safety — SINGLE SOURCE OF TRUTH for whether money can move.

Every place_order / place_bracket_order path MUST call `assert_orders_allowed()`.
Cancel is intentionally softer (enabled + connected) so accidental live orders
from TWS can still be flattened.

Env gates (all must pass for a LIVE buy/sell):
  1. IBKR_ENABLED=true
  2. Connected to Gateway
  3. IBKR_ORDERS_ENABLED=true          ← master kill switch (default OFF)
  4. If gateway mode / connection / broker accounts are live:
       IBKR_LIVE_TRADING_CONFIRMED=true

Paper pin (when IBKR_GATEWAY_MODE=paper):
  - Connection mode must be paper (port 4002 path)
  - Broker managedAccounts must classify as paper (DU… / DF…)

Account pin (ADR 013 — the account class is the truth, not the env door):
  - A live place needs `broker_account_kind == "live"`. `unknown` (managed
    accounts not received yet), `paper`, and `mixed` all refuse.
  - `spend_status` is derived from (gateway mode, broker_account_kind) so the
    header can never say `live_armed` over a DU… account.

IBKR_GATEWAY_MODE=paper|live chooses which Gateway port to connect.
Default is live (4001). Paper (4002) is the fallback when live is dark.
It does NOT authorize spending by itself.
"""
from __future__ import annotations

import logging
import os
from typing import Literal

from constants import (
    IBKR_GATEWAY_MODE_DEFAULT,
    IBKR_ORDERS_ENABLED_DEFAULT,
    IBKR_SHORT_ENABLED_DEFAULT,
)

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


def short_enabled() -> bool:
    """Third key for opening shorts (Phase K / ADR 009). Default OFF."""
    return _env_bool("IBKR_SHORT_ENABLED", IBKR_SHORT_ENABLED_DEFAULT)


def normalize_account_kind(broker_account_kind: str | None) -> str:
    """paper | live | mixed | unknown — anything unrecognized is `unknown`."""
    kind = (broker_account_kind or "unknown").strip().lower()
    return kind if kind in ("paper", "live", "mixed") else "unknown"


# ── Runtime arm latch (ADR 018) ───────────────────────────────────────────────
#
# `spend_permitted` (below) is the env capability: this desk is *allowed* to
# spend. `armed` (here) is this process's latch: it *currently* may. A place
# needs both, and `spend_state` is the AND of the two.
#
# Owner: this module. Invalidation: process start (the latch is a plain module
# global, so a fresh process is disarmed by construction) and any venue change
# (sim.mode.set_sim_mode). Nothing persists it -- that is the whole point.
_armed: bool = False

DISARMED_REASON = (
    "Desk is disarmed -- arm trading in this session before placing "
    "(a restart never lands armed, ADR 018)"
)

# Risk-reducing sources never consult the latch. A disarmed desk must always be
# able to get flat; it just cannot open. Mirrors the deliberately softer
# `assert_cancel_allowed` above.
PROTECTIVE_SOURCES = frozenset({"kill", "cancel_working", "flatten"})


def armed() -> bool:
    """Whether this process is currently armed to open positions."""
    return _armed


def set_armed(value: bool, *, reason: str = "") -> bool:
    """Arm or disarm this process. Returns the new state.

    Only an explicit operator action should arm. Never call this from a
    connect, reconnect or self-heal path -- re-arming on a healthy Gateway
    would re-arm on exactly the event the watchdog generates.
    """
    global _armed
    was = _armed
    _armed = bool(value)
    if was != _armed:
        logger.info(
            "IBKR: desk %s%s", "ARMED" if _armed else "DISARMED",
            f" ({reason})" if reason else "",
        )
    return _armed


def assert_armed_for(source: str | None) -> tuple[bool, str]:
    """(ok, reason) for an opening order from *source*."""
    if (source or "") in PROTECTIVE_SOURCES:
        return True, ""
    if not _armed:
        return False, DISARMED_REASON
    return True, ""


def spend_permitted(broker_account_kind: str | None) -> tuple[str, str]:
    """(spend_status, locked_reason) from env + account class alone.

    This is the *capability*: what this desk is configured to be allowed to do.
    It deliberately ignores the runtime arm latch so the UI can say "permitted
    but disarmed" instead of collapsing both into one lock.

    ADR 013: the account class behind the socket decides, not the env door.
    A door whose accounts are not yet classified is locked, not armed.
    """
    mode = gateway_mode()
    kind = normalize_account_kind(broker_account_kind)
    if not orders_enabled():
        return "locked", (
            "IBKR_ORDERS_ENABLED is false — orders locked "
            "(market data / Level 2 still allowed)"
        )
    if mode == "live" and not live_trading_confirmed():
        return "locked_live_unconfirmed", (
            "Live trading requires IBKR_LIVE_TRADING_CONFIRMED=true"
        )
    if kind != mode:
        return "locked_account_unconfirmed", (
            f"{mode} door but broker managedAccounts are {kind!r} — "
            f"spending stays locked until the account class reads {mode!r}"
        )
    return ("live_armed" if mode == "live" else "paper_armed"), ""


def spend_state(broker_account_kind: str | None) -> tuple[str, str]:
    """(spend_status, locked_reason) — the *effective* state: permitted AND armed.

    Every existing caller keeps reading one field and gets the safe answer:
    a permitted-but-disarmed desk reads locked, not armed.
    """
    status, locked_reason = spend_permitted(broker_account_kind)
    if status in ("live_armed", "paper_armed") and not _armed:
        return "locked_disarmed", DISARMED_REASON
    return status, locked_reason


def status_snapshot(broker_account_kind: str | None = None) -> dict:
    """Fields for /api/ibkr/status — UI + operators."""
    mode = gateway_mode()
    permitted, permitted_reason = spend_permitted(broker_account_kind)
    spend, locked_reason = spend_state(broker_account_kind)
    armed_kind = mode if spend in ("live_armed", "paper_armed") else None
    return {
        "gateway_mode": mode,
        "orders_enabled": orders_enabled(),
        "live_trading_confirmed": live_trading_confirmed(),
        "short_enabled": short_enabled(),
        "spend_status": spend,
        "armed_for_account_kind": armed_kind,
        "spend_locked_reason": locked_reason or None,
        # ADR 018 decision 5: venue and arm state are separate facts, so no
        # surface can say "practice" while the engine is armed for live.
        "spend_permitted": permitted in ("live_armed", "paper_armed"),
        "spend_permitted_status": permitted,
        "spend_permitted_reason": permitted_reason or None,
        "armed": _armed,
    }


def assert_orders_allowed(
    *,
    client_enabled: bool,
    connected: bool,
    account_mode: str,
    broker_account_kind: str = "unknown",
) -> tuple[bool, str]:
    """
    Returns (ok, reason). Sole gate used by place_order / place_bracket_order.

    ``broker_account_kind`` comes from IB managedAccounts classification
    (``paper`` | ``live`` | ``mixed`` | ``unknown``).
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

    env_mode = gateway_mode()
    conn_mode = account_mode if account_mode in ("paper", "live") else env_mode
    kind = normalize_account_kind(broker_account_kind)

    # ── Paper pin: env paper ⇒ connection + accounts must be paper ──────────
    if env_mode == "paper":
        if conn_mode != "paper":
            return False, (
                "Paper pin: IBKR_GATEWAY_MODE=paper but connection mode is "
                f"{conn_mode!r} — refusing place"
            )
        if kind != "paper":
            return False, (
                "Paper pin: broker managedAccounts are "
                f"{kind!r} (need paper DU/DF) — refusing place"
            )
        return True, ""

    # ── Live env / live accounts / live connection: second key required ─────
    if not live_trading_confirmed():
        return False, "Live trading requires IBKR_LIVE_TRADING_CONFIRMED=true"
    # Account pin (ADR 013): `unknown` means managedAccounts has not arrived
    # yet — an unclassified account is never allowed to spend live money.
    if kind != "live":
        return False, (
            "Live pin: broker managedAccounts are "
            f"{kind!r} (need live) — refusing place"
        )
    return True, ""


def assert_cancel_allowed(*, client_enabled: bool, connected: bool) -> tuple[bool, str]:
    """Cancel is allowed whenever connected — protective, not spending."""
    if not client_enabled:
        return False, "IBKR_ENABLED is not set"
    if not connected:
        return False, "IBKR not connected"
    return True, ""
