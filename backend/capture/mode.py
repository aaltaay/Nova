"""Capture mode selector — mutual exclusion with Sim."""
from __future__ import annotations

import logging
import os
from typing import Any

from capture.constants_capture import (
    CAPTURE_MODE_LABEL,
    CAPTURE_SPEND_STATUS,
)

logger = logging.getLogger(__name__)

_override: bool | None = None
_symbol: str | None = None


def reset_for_tests() -> None:
    global _override, _symbol
    _override = None
    _symbol = None


def is_capture_mode() -> bool:
    if _override is not None:
        return _override
    return (os.environ.get("NOVA_DESK_MODE") or "").strip().lower() == "capture"


def capture_symbol() -> str | None:
    return _symbol if is_capture_mode() else None


def set_capture_mode(enabled: bool, *, symbol: str | None = None) -> dict[str, Any]:
    """Enable Capture; disables Sim when turning on."""
    global _override, _symbol
    _override = bool(enabled)
    if enabled:
        # Capture and Sim cannot both own the desk.
        try:
            from sim.mode import set_sim_mode

            if __import__("sim.mode", fromlist=["is_sim_mode"]).is_sim_mode():
                set_sim_mode(False)
        except Exception:
            logger.exception("CAPTURE: failed to clear Sim")
        sym = (symbol or _symbol or "").strip().upper() or None
        _symbol = sym
        os.environ["NOVA_DESK_MODE"] = "capture"
        try:
            from capture.recorder import start_recorder

            start_recorder(sym)
        except Exception:
            logger.exception("CAPTURE: recorder start failed")
    else:
        os.environ.pop("NOVA_DESK_MODE", None)
        try:
            from capture.recorder import stop_recorder

            stop_recorder()
        except Exception:
            logger.exception("CAPTURE: recorder stop failed")
    logger.info("CAPTURE: mode %s symbol=%s", "on" if enabled else "off", _symbol)
    return status_payload()


def status_payload() -> dict[str, Any]:
    on = is_capture_mode()
    return {
        "capture": on,
        "mode": CAPTURE_MODE_LABEL if on else None,
        "capture_symbol": _symbol if on else None,
        "spend_status": CAPTURE_SPEND_STATUS if on else None,
    }
