"""Refuse places while Capture is on."""
from __future__ import annotations

from capture.constants_capture import CAPTURE_NO_PLACE_CODE, CAPTURE_NO_PLACE_REASON, CAPTURE_MODE_LABEL


def refuse_place() -> dict:
    return {
        "ok": False,
        "order_id": None,
        "error": CAPTURE_NO_PLACE_REASON,
        "code": CAPTURE_NO_PLACE_CODE,
        "mode": CAPTURE_MODE_LABEL,
    }
