"""Benign WebSocket send-after-close detection."""
from __future__ import annotations

from ws_close_errors import is_websocket_send_after_close


def test_detects_send_after_close_runtime_error():
    exc = RuntimeError('Cannot call "send" once a close message has been sent.')
    assert is_websocket_send_after_close(exc) is True


def test_rejects_other_runtime_errors():
    assert is_websocket_send_after_close(RuntimeError("something else")) is False


def test_rejects_non_runtime():
    assert is_websocket_send_after_close(ValueError("send close")) is False
