"""Nova process health for /api/health -- not Alpaca, not IBKR Gateway.

IBKR session lives on /api/ibkr/status. Alpaca account pings are aux-only
(see ping_alpaca_account) and must never drive the API chip.
"""
from __future__ import annotations

import logging

import requests

from constants_metrics import (
    HEALTH_LATENCY_SOURCE_NONE,
    HEALTH_SOURCE_NOVA_PROCESS,
)
from runtime_state import get_runtime_state

logger = logging.getLogger(__name__)


def mark_nova_process_health() -> None:
    """Record that the Nova API process is serving -- SoT for API chip 'up'."""
    state = get_runtime_state()
    state.cached_health = {
        "status": "connected",
        "latency_ms": 0,
        "health_source": HEALTH_SOURCE_NOVA_PROCESS,
        "latency_source": HEALTH_LATENCY_SOURCE_NONE,
    }


def set_health_broker_keys_missing() -> None:
    """Alpaca keys missing -- log only; do not mark Nova API as down.

    Kept for call-site compatibility. News/listing aux may be degraded, but
    the API chip and trading desk prerequisites do not depend on Alpaca.
    """
    logger.warning(
        "Alpaca credentials missing (APCA_API_KEY_ID / APCA_API_SECRET_KEY); "
        "news/listing/avg-vol aux unavailable until set. Nova API health is unchanged."
    )
    mark_nova_process_health()


def ping_alpaca_account(base_url: str, headers: dict) -> bool:
    """Probe Alpaca GET /v2/account for aux credential checks. Does not set API health."""
    try:
        r = requests.get(f"{base_url}/v2/account", headers=headers, timeout=5)
        return r.status_code == 200
    except Exception:
        logger.debug("Alpaca account ping failed", exc_info=True)
        return False


def ping_health(base_url: str, headers: dict) -> bool:
    """Backward-compatible alias for aux Alpaca credential gates.

    Legacy name used by alpaca_scanner / afterhours. Does **not** write
    cached_health -- call mark_nova_process_health for the API chip.
    """
    return ping_alpaca_account(base_url, headers)
