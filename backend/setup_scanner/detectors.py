"""Which detector reads which setup (ADR 031), and the window each one arms in. Pure."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from constants_bot import (
    BOT_SETUP_BULL_FLAG,
    BOT_SETUP_FIRST_PULLBACK,
    BOT_SETUP_FLAT_TOP,
    BOT_SETUP_RED_TO_GREEN,
)
from setup_scanner.bull_flag import BullFlagDetector
from setup_scanner.detector import ET, TriggerDetector, hhmm
from setup_scanner.flat_top import FlatTopDetector
from setup_scanner.pullback import PullbackDetector
from setup_scanner.red_to_green import RedToGreenDetector

DETECTORS: dict[str, type[TriggerDetector]] = {
    BOT_SETUP_FIRST_PULLBACK: PullbackDetector,
    BOT_SETUP_BULL_FLAG: BullFlagDetector,
    BOT_SETUP_FLAT_TOP: FlatTopDetector,
    BOT_SETUP_RED_TO_GREEN: RedToGreenDetector,
}


def make_detector(setup: str, symbol: str, params: Any) -> TriggerDetector:
    return DETECTORS[setup](symbol, p=params)


def window(setup: str, params: Any) -> tuple[str, str]:
    """``(start, end)`` ET: when a setup may arm (red to green: the open, then reclaim by)."""
    end = params.r2g_cutoff if setup == BOT_SETUP_RED_TO_GREEN else params.entry_cutoff
    return str(params.session_start), str(end)


def window_state(now: float, start: str, end: str) -> str:
    """``before`` / ``open`` / ``after`` the window at ``now`` (the venue's clock)."""
    t = datetime.fromtimestamp(now, ET).time()
    if t < hhmm(start):
        return "before"
    return "open" if t < hhmm(end) else "after"
