"""Overlay /api/ibkr/status for Sim desk mode. Tab Record is a side flag only."""
from __future__ import annotations

import logging
from typing import Any

from constants_sim import SIM_MODE_LABEL, SIM_SPEND_STATUS

logger = logging.getLogger(__name__)


def overlay_ibkr_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Force desk-usable Sim fields. Gateway transport stays honest."""
    try:
        from sim.mode import is_sim_mode, status_payload as sim_status_payload
    except Exception:
        is_sim_mode = lambda: False  # noqa: E731
        sim_status_payload = lambda: {}  # noqa: E731

    recording = False
    record_symbol = None
    record_error = None
    try:
        from capture.mode import status_payload as capture_status_payload

        capture = capture_status_payload()
        recording = bool(capture["capture"])
        record_symbol = capture["capture_symbol"]
        record_error = capture.get("error")
    except Exception:
        logger.exception("RECORD: capture status unavailable")
        record_error = "Recording status unavailable"
        recording = False
        record_symbol = None

    if is_sim_mode():
        out = dict(payload)
        out.update(sim_status_payload())
        out["mode"] = SIM_MODE_LABEL
        out["connected"] = True
        out["enabled"] = True
        out["session_state"] = "ready"
        out["session_reason"] = "ok"
        out["armed_for_account_kind"] = None
        # Sim practice fills are local (ADR 007 source path); IBKR spend stays
        # gated. ADR 018: the arm latch is about the *process*, not the door, so
        # Sim reads it too -- otherwise the venue would be answering "may I
        # place", which is exactly the coupling ADR 018 breaks.
        from ibkr.safety import DISARMED_REASON, armed as _armed_now

        is_armed = _armed_now()
        out["armed"] = is_armed
        out["spend_status"] = SIM_SPEND_STATUS if is_armed else "locked_disarmed"
        out["spend_locked_reason"] = None if is_armed else DISARMED_REASON
        out["trading_allowed"] = is_armed
        out["trading_allowed_reason"] = None if is_armed else DISARMED_REASON
        out["sim"] = True
        out["capture"] = recording
        out["capture_symbol"] = record_symbol
        out["recording"] = recording
        out["capture_error"] = record_error
        return out

    out = dict(payload)
    out.setdefault("sim", False)
    out["capture"] = recording
    out["capture_symbol"] = record_symbol
    out["recording"] = recording
    out["capture_error"] = record_error
    # Tab Record must NOT rewrite mode or trading_allowed — Paper/Live stay themselves.
    return out
