"""IBKR connection settings as the environment has them.

Read by the dialer on every pass (``session_reconnect``) and by
``client.is_enabled`` before that first pass. ``ibkr.client`` re-exports both
names, so ``client._resolve_config`` / ``client.reload_env_from_dotenv`` keep
working for callers and tests.
"""
from __future__ import annotations

import os

from constants import (
    IBKR_CLIENT_ID,
    IBKR_HOST,
    IBKR_LIVE_PORT,
    IBKR_PAPER_PORT,
)
from ibkr import safety as _safety


def _resolve_config() -> tuple[bool, str, int, str, int]:
    """Return (enabled, host, port, mode_label, client_id) from env, never raises."""
    enabled = os.environ.get("IBKR_ENABLED", "false").lower() in ("1", "true", "yes")
    host = os.environ.get("IBKR_HOST", IBKR_HOST)
    mode_label = _safety.gateway_mode()
    if mode_label == "live":
        port = int(os.environ.get("IBKR_LIVE_PORT", str(IBKR_LIVE_PORT)))
    else:
        port = int(os.environ.get("IBKR_PAPER_PORT", str(IBKR_PAPER_PORT)))
    try:
        client_id = int(os.environ.get("IBKR_CLIENT_ID", str(IBKR_CLIENT_ID)))
    except (TypeError, ValueError):
        client_id = int(IBKR_CLIENT_ID)
    return enabled, host, port, mode_label, client_id


def reload_env_from_dotenv() -> dict[str, str]:
    """Reload root .env into os.environ (override=True). Returns resolved config."""
    from dotenv import load_dotenv
    from paths import env_file_path

    load_dotenv(env_file_path(), override=True)
    enabled, host, port, mode_label, client_id = _resolve_config()
    return {
        "enabled": str(enabled),
        "host": host,
        "port": str(port),
        "gateway_mode": mode_label,
        "client_id": str(client_id),
    }
