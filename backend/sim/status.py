"""Overlay /api/ibkr/status for Sim and Capture desk modes."""
from __future__ import annotations

from typing import Any

from constants_sim import SIM_MODE_LABEL, SIM_SPEND_STATUS, SIM_SYMBOL
from sim.mode import is_sim_mode, status_payload as sim_status_payload


def overlay_ibkr_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Force desk-usable Sim/Capture fields. Gateway transport stays honest."""
    try:
        from capture.mode import is_capture_mode, status_payload as capture_status_payload
        from capture.constants_capture import CAPTURE_MODE_LABEL, CAPTURE_SPEND_STATUS
    except Exception:
        is_capture_mode = lambda: False  # noqa: E731
        capture_status_payload = lambda: {}  # noqa: E731
        CAPTURE_MODE_LABEL = "capture"
        CAPTURE_SPEND_STATUS = "capture_armed"

    if is_capture_mode():
        out = dict(payload)
        out.update(capture_status_payload())
        out["mode"] = CAPTURE_MODE_LABEL
        out["connected"] = bool(payload.get("connected") or payload.get("transport_connected"))
        out["enabled"] = True
        out["spend_status"] = CAPTURE_SPEND_STATUS
        out["trading_allowed"] = False
        out["trading_allowed_reason"] = "CAPTURE_NO_PLACE"
        out["sim"] = False
        out["capture"] = True
        return out

    if not is_sim_mode():
        out = dict(payload)
        out.setdefault("sim", False)
        out.setdefault("sim_symbol", None)
        out.setdefault("capture", False)
        return out
    out = dict(payload)
    out.update(sim_status_payload())
    out["mode"] = SIM_MODE_LABEL
    out["connected"] = True
    out["enabled"] = True
    out["session_state"] = "ready"
    out["session_reason"] = "ok"
    out["spend_status"] = SIM_SPEND_STATUS
    out["spend_locked_reason"] = None
    out["armed_for_account_kind"] = None
    out["trading_allowed"] = True
    out["trading_allowed_reason"] = None
    out["sim"] = True
    out["sim_symbol"] = SIM_SYMBOL
    out["capture"] = False
    return out
