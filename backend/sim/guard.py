"""Hard refuse for any IBKR Gateway place/cancel while Sim is on."""
from __future__ import annotations

from constants_sim import SIM_MODE_LABEL, SIM_NO_IBKR_CODE, SIM_NO_IBKR_REASON


def refuse_place() -> dict:
    return {
        "ok": False,
        "order_id": None,
        "error": SIM_NO_IBKR_REASON,
        "mode": SIM_MODE_LABEL,
        "reason_code": SIM_NO_IBKR_CODE,
    }


def refuse_bracket() -> dict:
    return {
        "ok": False,
        "parent_order_id": None,
        "target_order_id": None,
        "stop_order_id": None,
        "error": SIM_NO_IBKR_REASON,
        "mode": SIM_MODE_LABEL,
        "reason_code": SIM_NO_IBKR_CODE,
    }


def refuse_cancel() -> dict:
    return {
        "ok": False,
        "error": SIM_NO_IBKR_REASON,
        "reason_code": SIM_NO_IBKR_CODE,
    }
