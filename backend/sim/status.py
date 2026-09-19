"""Overlay /api/ibkr/status so Sim never looks like paper or live IBKR."""
from __future__ import annotations

from typing import Any

from constants_sim import SIM_MODE_LABEL, SIM_SPEND_STATUS, SIM_SYMBOL
from sim.mode import is_sim_mode, status_payload


def overlay_ibkr_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Force desk-usable Sim fields. Gateway transport stays honest."""
    if not is_sim_mode():
        out = dict(payload)
        out.setdefault("sim", False)
        out.setdefault("sim_symbol", None)
        return out
    out = dict(payload)
    out.update(status_payload())
    out["mode"] = SIM_MODE_LABEL
    out["connected"] = True
    out["enabled"] = True
    out["session_state"] = "ready"
    out["session_reason"] = "ok"
    out["spend_status"] = SIM_SPEND_STATUS
    out["spend_locked_reason"] = None
    out["armed_for_account_kind"] = None
    out["sim"] = True
    out["sim_symbol"] = SIM_SYMBOL
    return out
