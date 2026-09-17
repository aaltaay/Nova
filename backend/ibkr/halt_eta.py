"""LULD / halt reopen ETA clock (pure).

IBKR incoming tick type 49 (ib_async: ``ticker.halted``; Generic tick
required = "-"; do not put 49 in genericTickList -- #178):
  -1 status unavailable (not a halt)
   0 not halted
   1 general halt (news / regulatory) -- NEWS badge, no timer
   2 volatility halt (LULD) -- second-precise 0-5 / 5-10 / >10 clock

``halt_start`` is the first observed ``ticker.halted`` transition, not the
SIP official start, unless Nasdaq Trade Halt RSS supplies one. A quiet
tape is a hint only -- it never creates a chip or countdown. Display only
-- never block Place from this clock.
"""
from __future__ import annotations

from typing import Any

from constants import LULD_CONFIDENT_WINDOW_SEC, LULD_PAUSE_SEC

KIND_LULD = "luld"
KIND_REGULATORY = "regulatory"
KIND_UNKNOWN = "unknown"

BADGE_LULD = "LULD"
BADGE_NEWS = "NEWS"
BADGE_UNK = "UNK"

PHASE_PAUSE = "luld_pause"
PHASE_AUCTION = "luld_auction"
PHASE_EXTENDED = "luld_extended"

LABEL_EXTENDED = "Extended · no ETA"
LABEL_REGULATORY = "NEWS · HALTED"
LABEL_UNKNOWN = "UNK · HALTED"
# Backward-compatible alias -- old tests / imports used LABEL_STILL.
LABEL_STILL = LABEL_EXTENDED

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
HALT_START_SOURCE_NASDAQ = "nasdaq_trade_halt_rss"

EXCHANGE_OK = "ok"
EXCHANGE_PENDING = "pending"
EXCHANGE_DOWN = "down"


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


def classify_rss_reason_code(reason_code: str | None) -> str:
    """Map a Nasdaq Trade Halt reason to a chip kind (LUDP/T1/…)."""
    raw = (reason_code or "").strip().upper()
    if not raw:
        return KIND_UNKNOWN
    if raw.startswith("LUD") or raw == "LULD" or raw.startswith("VOL"):
        return KIND_LULD
    if raw.startswith("T") or raw.startswith("N"):
        return KIND_REGULATORY
    return KIND_UNKNOWN


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


def kind_badge(kind: str | None) -> str:
    if kind == KIND_LULD:
        return BADGE_LULD
    if kind == KIND_REGULATORY:
        return BADGE_NEWS
    return BADGE_UNK


def format_clock(elapsed_sec: float) -> str:
    """Second-precise elapsed / countdown (M:SS or H:MM:SS)."""
    total = max(0, int(elapsed_sec))
    minutes, seconds = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def luld_phase(elapsed_sec: float) -> str:
    if elapsed_sec < LULD_PAUSE_SEC:
        return PHASE_PAUSE
    if elapsed_sec < LULD_CONFIDENT_WINDOW_SEC:
        return PHASE_AUCTION
    return PHASE_EXTENDED


def luld_label(
    elapsed_sec: float,
    *,
    start_late: bool = False,
    has_official_start: bool = False,
) -> str:
    clock = format_clock(elapsed_sec)
    confident = (not start_late) or has_official_start
    if not confident:
        return f"{BADGE_LULD} · {clock}"
    phase = luld_phase(elapsed_sec)
    if phase == PHASE_PAUSE:
        left = format_clock(LULD_PAUSE_SEC - elapsed_sec)
        return f"{BADGE_LULD} · {clock} · {left} left"
    if phase == PHASE_AUCTION:
        left = format_clock(LULD_CONFIDENT_WINDOW_SEC - elapsed_sec)
        return f"Auction · {clock} · {left} left"
    return LABEL_EXTENDED


def halt_chip_view(
    *,
    kind: str | None,
    halt_start: float | None,
    now: float,
    halted: bool = True,
    start_late: bool = False,
    official_halt_start: float | None = None,
) -> dict[str, Any] | None:
    """Pure chip view. Returns None when the chip must not render."""
    if not halted or not kind:
        return None

    clock_start = halt_start
    clock_source = HALT_START_SOURCE
    if official_halt_start is not None:
        clock_start = official_halt_start
        clock_source = HALT_START_SOURCE_NASDAQ

    elapsed = 0.0
    if clock_start is not None:
        elapsed = max(0.0, float(now) - float(clock_start))

    has_official = official_halt_start is not None
    badge = kind_badge(kind)

    if kind == KIND_LULD:
        label = luld_label(
            elapsed, start_late=start_late, has_official_start=has_official,
        )
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
        "badge": badge,
        "phase": phase,
        "label": label,
        "elapsed_sec": elapsed,
        "halt_type": halt_type,
        "reason": reason,
        "rule": rule,
        "halt_start_source": clock_source,
        "start_late": bool(start_late),
        "has_official_start": has_official,
    }
