"""Detect benign WebSocket close races (send after close)."""
from __future__ import annotations


def is_websocket_send_after_close(exc: BaseException) -> bool:
    """True for RuntimeError raised when sending on an already-closed WS."""
    if not isinstance(exc, RuntimeError):
        return False
    text = str(exc).lower()
    return "send" in text and "close" in text
