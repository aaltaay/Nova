"""Which detector reads which setup (ADR 031, ADR 049), and the window each one arms in. Pure."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from constants_bot import (
    BOT_SETUP_BACKSIDE,
    BOT_SETUP_BEAR_FLAG,
    BOT_SETUP_BULL_FLAG,
    BOT_SETUP_FAILED_BREAKOUT,
    BOT_SETUP_FIRST_PULLBACK,
    BOT_SETUP_FLAT_TOP,
    BOT_SETUP_FLAT_TOP_5M,
    BOT_SETUP_GAP_AND_GO,
    BOT_SETUP_LOST_VWAP,
    BOT_SETUP_RED_TO_GREEN,
    BOT_SETUP_SSR_BOUNCE,
)
from setup_scanner.backside import BacksideDetector
from setup_scanner.bear_flag import BearFlagDetector
from setup_scanner.bull_flag import BullFlagDetector
from setup_scanner.detector import ET, TriggerDetector, hhmm
from setup_scanner.failed_breakout import FailedBreakoutDetector
from setup_scanner.flat_top import FlatTopDetector
from setup_scanner.flat_top_5m import FlatTop5mDetector
from setup_scanner.gap_and_go import GapAndGoDetector
from setup_scanner.lost_vwap import LostVwapDetector
from setup_scanner.pullback import PullbackDetector
from setup_scanner.red_to_green import RedToGreenDetector
from setup_scanner.ssr_bounce import SsrBounceDetector

DETECTORS: dict[str, type[TriggerDetector]] = {
    BOT_SETUP_FIRST_PULLBACK: PullbackDetector,
    BOT_SETUP_BULL_FLAG: BullFlagDetector,
    BOT_SETUP_FLAT_TOP: FlatTopDetector,
    BOT_SETUP_FLAT_TOP_5M: FlatTop5mDetector,
    BOT_SETUP_RED_TO_GREEN: RedToGreenDetector,
    BOT_SETUP_GAP_AND_GO: GapAndGoDetector,
    # ADR 049: the short setups, the trigger read downward (``detector_short``).
    BOT_SETUP_BACKSIDE: BacksideDetector,
    BOT_SETUP_BEAR_FLAG: BearFlagDetector,
    BOT_SETUP_FAILED_BREAKOUT: FailedBreakoutDetector,
    BOT_SETUP_LOST_VWAP: LostVwapDetector,
    BOT_SETUP_SSR_BOUNCE: SsrBounceDetector,
}


def make_detector(setup: str, symbol: str, params: Any) -> TriggerDetector:
    return DETECTORS[setup](symbol, p=params)


def side_of(setup: str) -> str:
    """``long`` / ``short``: the side a setup's trigger enters (its detector's)."""
    cls = DETECTORS.get(setup)
    return cls.SIDE if cls is not None else "long"


def trigger_up(setup: str) -> bool:
    """Whether a price rises to the setup's trigger (every long, and the SSR bounce's resting short)."""
    cls = DETECTORS.get(setup)
    return bool(cls.TRIGGER_UP) if cls is not None else True


def window(setup: str, params: Any) -> tuple[str, str]:
    """``(start, end)`` ET: when a setup may arm (red to green: the open, then reclaim by; Gap and Go:
    the open, then the break until its cutoff)."""
    end = params.r2g_cutoff if setup == BOT_SETUP_RED_TO_GREEN else params.entry_cutoff
    return str(params.session_start), str(end)


def window_state(now: float, start: str, end: str) -> str:
    """``before`` / ``open`` / ``after`` the window at ``now`` (the venue's clock)."""
    t = datetime.fromtimestamp(now, ET).time()
    if t < hhmm(start):
        return "before"
    return "open" if t < hhmm(end) else "after"
