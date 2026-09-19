"""Per-symbol session record (right-click tab Record) — not a desk capsule mode."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_recording: bool = False
_symbol: str | None = None


def reset_for_tests() -> None:
    global _recording, _symbol
    _recording = False
    _symbol = None


def is_capture_mode() -> bool:
    """True while a tab Record session is active (legacy name kept for guards)."""
    return _recording


def capture_symbol() -> str | None:
    return _symbol if _recording else None


def set_capture_mode(enabled: bool, *, symbol: str | None = None) -> dict[str, Any]:
    """Start/stop per-symbol IBKR session record. Does not switch Paper/Live/Sim."""
    global _recording, _symbol
    if enabled:
        sym = (symbol or _symbol or "").strip().upper()
        if not sym:
            return {
                "capture": False,
                "error": "Pick a symbol tab before Record",
                "mode": None,
                "capture_symbol": None,
                "spend_status": None,
            }
        _symbol = sym
        _recording = True
        try:
            from capture.recorder import start_recorder

            start_recorder(sym, resume=True)
        except Exception:
            logger.exception("RECORD: recorder start failed")
            _recording = False
            return status_payload() | {"error": "Recorder start failed"}
    else:
        try:
            from capture.recorder import stop_recorder

            stop_recorder()
        except Exception:
            logger.exception("RECORD: recorder stop failed")
        _recording = False
    logger.info("RECORD: %s symbol=%s", "on" if _recording else "off", _symbol)
    return status_payload()


def status_payload() -> dict[str, Any]:
    on = _recording
    return {
        "capture": on,
        "mode": "record" if on else None,
        "capture_symbol": _symbol if on else None,
        "spend_status": "recording" if on else None,
    }
