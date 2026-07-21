"""
Read-only IBKR Gateway port probes + disconnect hints for /api/ibkr/status.

Never attaches an IB session to the alternate port — TCP connect only.
"""
from __future__ import annotations

import logging
import os
import socket
from typing import Any

from constants import IBKR_HOST, IBKR_LIVE_PORT, IBKR_PAPER_PORT
from ibkr import gateway_heal as _heal
from ibkr import safety as _safety

logger = logging.getLogger(__name__)

# Short TCP probe — enough to distinguish LISTEN vs ConnectionRefused.
_PROBE_TIMEOUT_SEC = 0.35


def probe_port(host: str, port: int, *, timeout: float = _PROBE_TIMEOUT_SEC) -> bool:
    """Return True if a TCP connect to host:port succeeds (port is listening)."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _host() -> str:
    return os.environ.get("IBKR_HOST", IBKR_HOST)


def disconnect_hint(
    *,
    connected: bool,
    preferred_mode: str,
    preferred_reachable: bool,
    alternate_reachable: bool,
) -> str | None:
    """
    Machine-readable hint for UI copy. None when connected or both ports dark.
    """
    if connected:
        return None
    alt = _heal.alternate_mode(preferred_mode)
    if not preferred_reachable and alternate_reachable:
        return f"{preferred_mode}_port_refused_{alt}_listening"
    if not preferred_reachable and not alternate_reachable:
        return "both_ports_unreachable"
    if preferred_reachable:
        # Port open but Nova still disconnected — clientId / login / pin, etc.
        return f"{preferred_mode}_port_open_but_disconnected"
    return None


def status_port_fields(*, connected: bool) -> dict[str, Any]:
    """Fields merged into GET /api/ibkr/status (probes only when disconnected)."""
    preferred_mode = _safety.gateway_mode()
    preferred_port = _heal.port_for_mode(preferred_mode)
    alt_mode = _heal.alternate_mode(preferred_mode)
    alternate_port = _heal.port_for_mode(alt_mode)
    host = _host()

    if connected:
        preferred_reachable = True
        alternate_reachable = False  # unused when connected; avoid extra probe
        hint = None
    else:
        preferred_reachable = probe_port(host, preferred_port)
        alternate_reachable = probe_port(host, alternate_port)
        hint = disconnect_hint(
            connected=False,
            preferred_mode=preferred_mode,
            preferred_reachable=preferred_reachable,
            alternate_reachable=alternate_reachable,
        )

    return {
        "preferred_port": preferred_port,
        "alternate_port": alternate_port,
        "preferred_port_reachable": preferred_reachable,
        "alternate_port_reachable": alternate_reachable,
        "disconnect_hint": hint,
        "live_port": int(os.environ.get("IBKR_LIVE_PORT", str(IBKR_LIVE_PORT))),
        "paper_port": int(os.environ.get("IBKR_PAPER_PORT", str(IBKR_PAPER_PORT))),
    }
