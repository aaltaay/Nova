"""Overlay /api/ibkr/status for Sim desk mode. Tab Record is a side flag only."""
from __future__ import annotations

from typing import Any

from constants_sim import SIM_MODE_LABEL, SIM_SPEND_STATUS, SIM_SYMBOL


def overlay_ibkr_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Force desk-usable Sim fields. Gateway transport stays honest."""
    try:
        from sim.mode import is_sim_mode, status_payload as sim_status_payload
    except Exception:
        is_sim_mode = lambda: False  # noqa: E731
        sim_status_payload = lambda: {}  # noqa: E731

    recording = False
    record_symbol = None
    try:
        from capture.mode import is_capture_mode, capture_symbol

        recording = bool(is_capture_mode())
        record_symbol = capture_symbol()
    except Exception:
        recording = False
        record_symbol = None

    if is_sim_mode():
        out = dict(payload)
        out.update(sim_status_payload())
        out["mode"] = SIM_MODE_LABEL
        out["connected"] = True
        out["enabled"] = True
        out["spend_status"] = SIM_SPEND_STATUS
        out["sim"] = True
        out["sim_symbol"] = SIM_SYMBOL
        out["capture"] = recording
        out["capture_symbol"] = record_symbol
        out["recording"] = recording
        return out

    out = dict(payload)
    out.setdefault("sim", False)
    out.setdefault("sim_symbol", None)
    out["capture"] = recording
    out["capture_symbol"] = record_symbol
    out["recording"] = recording
    # Tab Record must NOT rewrite mode or trading_allowed — Paper/Live stay themselves.
    return out
