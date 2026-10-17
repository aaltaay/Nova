"""Session READY side effects, delayed market-data fallback, and diagnostic snapshot.

Extracted from ``ibkr/client.py`` so the singleton connection state module stays
under the 400-line soft limit while preserving ``ibkr.client``'s public surface.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from constants import (
    IBKR_MARKET_DATA_TYPE_DELAYED,
    IBKR_MARKET_DATA_TYPE_LIVE,
)

logger = logging.getLogger(__name__)


def clear_sticky_bridge_error_on_ready(
    get_runtime_state_fn: Callable[[], Any],
) -> None:
    """Drop any ``ibkr_bridge_last_error`` recorded while the session was
    down/degraded (see PROBLEM_LOG 2026-07-23 sticky-banner-after-reconnect).

    A disconnect-window failure (``ib=none``) must not outlive reconnect --
    once the session reaches READY, movers/L1 are live again, so an old
    error string left over from the outage would otherwise paint Integrity
    fail red indefinitely until the next successful movers refresh (or a
    full API restart). This makes reconnect self-heal immediately.
    """
    try:
        state = get_runtime_state_fn()
    except Exception:
        return
    if getattr(state, "ibkr_bridge_last_error", ""):
        state.ibkr_bridge_last_error = ""
        state.ibkr_bridge_last_error_ts = 0.0


async def on_session_ready(
    ib: Any,
    *,
    reason: str,
    session_errors: Any,
) -> int | None:
    """Side effects that must run at every READY transition (G1/G2/G4).

    Lets go of the prior connection's L1 lines (#565: cancelling on ``ib`` the
    ones a 1101 lost), installs the errorEvent hook, requests live market data.
    Returns the new ``market_data_type`` when ``reqMarketDataType`` succeeds.
    """
    try:
        from ibkr import ticks as _ticks

        await _ticks.clear_all_subscriptions(reason=reason, ib=ib)
    except Exception:
        logger.exception("IBKR: clear_all_subscriptions failed on READY (%s)", reason)
    try:
        from ibkr import discovery as _discovery, qualified_contracts as _qualified

        _discovery.clear_inflight_scan_reqids(reason=reason)
        _qualified.clear_qualified_contracts(reason=reason)
    except Exception:
        logger.exception("IBKR: clear_inflight_scan_reqids failed on READY (%s)", reason)
    try:
        session_errors.install_error_hook(ib)
    except Exception:
        logger.exception("IBKR: session_errors hook install failed on READY (%s)", reason)
    try:
        session_errors.reset_session_md_flags()
        ib.reqMarketDataType(int(IBKR_MARKET_DATA_TYPE_LIVE))
        md_type = int(IBKR_MARKET_DATA_TYPE_LIVE)
        logger.info(
            "IBKR: requested market data type %s (%s)",
            md_type,
            reason,
        )
        return md_type
    except Exception:
        logger.exception("IBKR: reqMarketDataType failed on READY (%s)", reason)
        return None


def fallback_to_delayed_market_data(
    ib: Any,
    *,
    ready: bool,
    current_md_type: int | None,
    session_errors: Any,
) -> int | None:
    """If Error 10089 blocked live API MD, switch to delayed (type 3).

    Returns the new ``market_data_type`` when a downgrade request was issued
    this call, else ``None``.
    """
    if not session_errors.live_market_data_blocked():
        return None
    if current_md_type == int(IBKR_MARKET_DATA_TYPE_DELAYED):
        return None
    if ib is None or not ready:
        return None
    try:
        ib.reqMarketDataType(int(IBKR_MARKET_DATA_TYPE_DELAYED))
        md_type = int(IBKR_MARKET_DATA_TYPE_DELAYED)
        logger.warning(
            "IBKR: fell back to delayed market data type %s "
            "(live API entitlement missing -- Error 10089)",
            md_type,
        )
        return md_type
    except Exception:
        logger.exception("IBKR: delayed market data fallback failed")
        return None


def build_session_snapshot(
    *,
    usable: bool,
    connected: bool,
    reason: str,
    mode: str,
    enabled: bool,
    reconnect_task: Any,
    session_state: Any,
    session_errors: Any,
) -> dict[str, Any]:
    """Diagnostic snapshot for /readyz and PROBLEM_LOG-style evidence."""
    from ibkr import ib_scheduler as _ib_scheduler
    from ibkr import session_reconnect as _reconnect
    from ibkr import session_usable as _session_usable

    return {
        "state": session_state.state(),
        "generation": session_state.generation(),
        "ready": usable,
        "usable": usable,
        "connected": connected,
        "transport_up": connected,
        "reason": reason,
        "unusable_since": session_errors.unusable_since(),
        "last_connectivity_code": session_errors.last_connectivity_code(),
        "mode": mode,
        "enabled": enabled,
        # Diagnostics for the exact freeze this instrumentation was added
        # for (PROBLEM_LOG 2026-08-31) -- one query instead of an hour of
        # log archaeology next time.
        "earn_in_flight": _session_usable.earn_in_flight(),
        "ib_cold_inflight": _ib_scheduler.inflight_label() or None,
        "dialer_alive": reconnect_task is not None and not reconnect_task.done(),
        "dialer_heartbeat_age_sec": _reconnect.dialer_heartbeat_age_sec(),
    }
