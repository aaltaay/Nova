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
    from capture.worker import transition

    result = transition(lambda: _set_capture_mode(enabled, symbol=symbol))
    return status_payload() | (result or {})


def _set_capture_mode(enabled: bool, *, symbol: str | None = None) -> dict[str, Any] | None:
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
            return {"error": "Recorder start failed"}
    else:
        try:
            from capture.recorder import stop_recorder

            stop_recorder()
        except Exception:
            logger.exception("RECORD: recorder stop failed")
        _recording = False
    logger.info("RECORD: %s symbol=%s", "on" if _recording else "off", _symbol)
    return None


def _reconcile() -> str | None:
    """Follow the recorder, not our own flag (D-068).

    The recorder stops itself when writes keep failing (disk full, drive
    unplugged, revoked handle).  Without this, ``_recording`` stayed True and
    ``/api/capture`` kept answering ``capture: true`` while nothing was being
    written — the operator only found out at replay time.  Returns the
    recorder's error so the caller can surface it.
    """
    global _recording
    if not _recording:
        return None
    try:
        from capture.recorder import is_recording, last_error
    except Exception:
        logger.exception("RECORD: recorder status unavailable")
        return None
    if is_recording():
        return None
    err = last_error()
    _recording = False
    logger.warning("RECORD: recorder stopped itself (%s) — clearing record mode", err or "unknown")
    return err


def status_payload() -> dict[str, Any]:
    err = _reconcile()
    on = _recording
    out: dict[str, Any] = {
        "capture": on,
        "mode": "record" if on else None,
        "capture_symbol": _symbol if on else None,
        "spend_status": "recording" if on else None,
    }
    if err:
        out["error"] = err
    from capture.worker import status as worker_status

    worker = worker_status()
    out["writer"] = worker
    if worker["error"]:
        out["error"] = worker["error"]
    return out
