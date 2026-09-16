"""LULD / halt reopen ETA clock (pure).

IBKR incoming tick type 49 (ib_async: ``ticker.halted``; Generic tick
required = "-"; do not put 49 in genericTickList -- #178):
  -1 status unavailable (not a halt)
   0 not halted
   1 general halt (news / regulatory) -- HALTED + reason, no timer
   2 volatility halt (LULD) -- timed 0-5 / 5-10 / >10 clock

``halt_start`` is the first observed ``ticker.halted`` transition, not the
SIP official start. A quiet tape is a hint only -- it never creates a chip
or countdown.
"""
from __future__ import annotations

import math
from typing import Any

from constants import LULD_CONFIDENT_WINDOW_SEC, LULD_PAUSE_SEC

KIND_LULD = "luld"
KIND_REGULATORY = "regulatory"
KIND_UNKNOWN = "unknown"

PHASE_PAUSE = "luld_pause"
PHASE_EXTENDED = "luld_extended"
PHASE_STILL = "luld_still"

LABEL_STILL = "Still halted · auction extended"
LABEL_REGULATORY = "HALTED · news/regulatory"
LABEL_UNKNOWN = "HALTED · ETA unknown"

RULE_LULD = (
    "halt_start + 5m LULD pause, then ~5m auction. "
    "After 10m still halted: no confident countdown "
    "(further +5m auction windows possible)."
)
RULE_REGULATORY = "News / regulatory halt -- no timed reopen estimate."
RULE_UNKNOWN = "Halt signaled; type unknown -- no timed reopen estimate."

REASON_LULD = "Volatility pause (ticker.halted=2, incoming tick type 49)"
REASON_REGULATORY = (
    "General halt -- news / regulatory (ticker.halted=1, incoming tick type 49)"
)
REASON_UNKNOWN = "Halt signaled; ticker.halted type unknown"

HALT_START_SOURCE = "observed_ticker_halted"


def parse_halt_code(raw: Any) -> int | None:
    """Return the integer ticker.halted code, or None when missing / NaN."""
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val != val:  # NaN
        return None
    return int(val)


def classify_halt_code(code: int | None) -> str | None:
    """Map a ticker.halted code to a chip kind, or None when not halted.

    IBKR Halted values (incoming tick type 49): 2 is LULD, 1 is general/news,
    -1 is unavailable, 0 is not halted. Any other positive code is treated
    as halted-unknown rather than a fake LULD timer.
    """
    if code is None or code in (0, -1):
        return None
    if code == 2:
        return KIND_LULD
    if code == 1:
        return KIND_REGULATORY
    return KIND_UNKNOWN


def _minutes_left(remaining_sec: float) -> int:
    if remaining_sec <= 0:
        return 0
    return max(1, math.ceil(remaining_sec / 60.0))


def luld_phase(elapsed_sec: float) -> str:
    if elapsed_sec < LULD_PAUSE_SEC:
        return PHASE_PAUSE
    if elapsed_sec < LULD_CONFIDENT_WINDOW_SEC:
        return PHASE_EXTENDED
    return PHASE_STILL


def luld_label(elapsed_sec: float) -> str:
    phase = luld_phase(elapsed_sec)
    if phase == PHASE_PAUSE:
        left = _minutes_left(LULD_PAUSE_SEC - elapsed_sec)
        return f"LULD · ~{left}m left"
    if phase == PHASE_EXTENDED:
        left = _minutes_left(LULD_CONFIDENT_WINDOW_SEC - elapsed_sec)
        return f"Extended · ~{left}m"
    return LABEL_STILL


def halt_chip_view(
    *,
    kind: str | None,
    halt_start: float | None,
    now: float,
    halted: bool = True,
) -> dict[str, Any] | None:
    """Pure chip view. Returns None when the chip must not render."""
    if not halted or not kind:
        return None
    elapsed = 0.0
    if halt_start is not None:
        elapsed = max(0.0, float(now) - float(halt_start))

    if kind == KIND_LULD:
        label = luld_label(elapsed)
        rule = RULE_LULD
        reason = REASON_LULD
        halt_type = "LULD / volatility pause"
        phase = luld_phase(elapsed)
    elif kind == KIND_REGULATORY:
        label = LABEL_REGULATORY
        rule = RULE_REGULATORY
        reason = REASON_REGULATORY
        halt_type = "News / regulatory"
        phase = KIND_REGULATORY
    else:
        label = LABEL_UNKNOWN
        rule = RULE_UNKNOWN
        reason = REASON_UNKNOWN
        halt_type = "Unknown"
        phase = KIND_UNKNOWN

    return {
        "kind": kind,
        "phase": phase,
        "label": label,
        "elapsed_sec": elapsed,
        "halt_type": halt_type,
        "reason": reason,
        "rule": rule,
        "halt_start_source": HALT_START_SOURCE,
    }
