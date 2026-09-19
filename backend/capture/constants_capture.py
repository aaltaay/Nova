"""Capture mode — IBKR session record, not for placing."""
from __future__ import annotations

CAPTURE_MODE_LABEL = "capture"
CAPTURE_SPEND_STATUS = "capture_armed"
CAPTURE_BANNER = (
    "CAPTURE MODE -- recording IBKR tape/L2/quotes/bars for Sim replay. "
    "Not for placing. Keep Trader/scanner light."
)
CAPTURE_NO_PLACE_REASON = "CAPTURE mode cannot place orders"
CAPTURE_NO_PLACE_CODE = "CAPTURE_NO_PLACE"
CAPTURE_L2_MAX_HZ = 8.0
# Outside-repo capture root (Windows trading bench). Override with NOVA_SIM_CAPTURE_DIR.
DEFAULT_SIM_CAPTURE_ROOT_WIN = r"F:\Nova\sim_capture"
