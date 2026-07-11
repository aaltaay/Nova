"""
ABCD setup detection — signal-only.

Pattern (SS101 Ch.5): an impulsive A-to-B move of at least ABCD_MIN_AB_MOVE_PCT,
a pullback to point C that holds the 9 EMA and doesn't retrace more than half
the A-B move, with entry D on a break back above point B. Stop is the course's
documented ~20 cent risk (see ABCD_MAX_STOP_DOLLARS).

Like gap_and_go.py and bull_flag.py, this module never places an order.
`would_execute` is hard-coded to False.
"""

from __future__ import annotations

from dataclasses import dataclass

from constants import (
    ABCD_EMA_PERIOD,
    ABCD_MAX_RETRACE_PCT,
    ABCD_MAX_STOP_DOLLARS,
    ABCD_MIN_AB_MOVE_PCT,
    ABCD_MIN_PROFIT_LOSS_RATIO,
)
from strategy.five_pillars import FivePillarsResult, evaluate_five_pillars
from strategy.indicators import closes, ema


@dataclass(frozen=True)
class ABCDSignal:
    symbol: str
    five_pillars: FivePillarsResult
    pattern_found: bool
    holds_9ema: bool
    ab_move_pct: float | None
    retrace_pct: float | None
    point_b_high: float | None
    point_c_low: float | None
    current_price: float | None
    triggered: bool
    entry_price: float | None
    stop_price: float | None
    target_price: float | None
    would_execute: bool = False
    notes: tuple[str, ...] = ()

    @property
    def eligible(self) -> bool:
        return self.five_pillars.all_pass and self.pattern_found and self.holds_9ema and self.triggered

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "eligible": self.eligible,
            "would_execute": self.would_execute,
            "pattern_found": self.pattern_found,
            "holds_9ema": self.holds_9ema,
            "ab_move_pct": self.ab_move_pct,
            "retrace_pct": self.retrace_pct,
            "point_b_high": self.point_b_high,
            "point_c_low": self.point_c_low,
            "current_price": self.current_price,
            "triggered": self.triggered,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "five_pillars": self.five_pillars.to_dict(),
            "notes": list(self.notes),
        }


def _find_abc_points(bars: list[dict]) -> tuple[int, int, int] | None:
    """Locate (A, B, C) bar indices: A = swing low, B = swing high after A,
    C = pullback low after B. Returns None if the structure isn't present yet
    (e.g. the peak is still forming, or there's no pullback after it)."""
    n = len(bars)
    if n < 3:
        return None

    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]

    b_idx = max(range(n), key=lambda i: highs[i])
    if b_idx == 0 or b_idx == n - 1:
        return None  # no room for A before B, or no bars after B for a pullback

    a_idx = min(range(0, b_idx + 1), key=lambda i: lows[i])
    if a_idx >= b_idx:
        return None

    c_slice = bars[b_idx + 1:]
    c_idx = b_idx + 1 + min(range(len(c_slice)), key=lambda i: c_slice[i]["l"])
    return a_idx, b_idx, c_idx


def evaluate_abcd(candidate: dict, bars: list[dict]) -> ABCDSignal:
    """Evaluate the ABCD setup using recent 1-min bars (ascending order)."""
    symbol = candidate.get("symbol", "?")
    pillars = evaluate_five_pillars(candidate)
    current_price = candidate.get("price", candidate.get("current_price"))
    notes: list[str] = []

    points = _find_abc_points(bars)
    if points is None:
        if not pillars.all_pass:
            notes.append(f"Five Pillars not all met ({pillars.pass_count}/5) — no signal.")
        notes.append("No A-B-C structure (impulsive move + pullback) found in recent bars.")
        return ABCDSignal(
            symbol=symbol, five_pillars=pillars, pattern_found=False, holds_9ema=False,
            ab_move_pct=None, retrace_pct=None, point_b_high=None, point_c_low=None,
            current_price=current_price, triggered=False, entry_price=None, stop_price=None,
            target_price=None, would_execute=False, notes=tuple(notes),
        )

    a_idx, b_idx, c_idx = points
    a_low = bars[a_idx]["l"]
    b_high = bars[b_idx]["h"]
    c_low = bars[c_idx]["l"]

    ab_move_pct = (b_high - a_low) / a_low * 100 if a_low > 0 else 0.0
    denom = b_high - a_low
    retrace_pct = (b_high - c_low) / denom if denom > 0 else 1.0
    broke_prior_high = any(bar["h"] > b_high for bar in bars[b_idx + 1: c_idx + 1])

    ema_series = ema(closes(bars), ABCD_EMA_PERIOD)
    c_close = bars[c_idx]["c"]
    c_ema = ema_series[c_idx]
    holds_9ema = c_ema is not None and c_close >= c_ema

    triggered = bool(current_price is not None and current_price > b_high)

    if ab_move_pct < ABCD_MIN_AB_MOVE_PCT:
        notes.append(f"A-B move was only {ab_move_pct:.1f}% (need >= {ABCD_MIN_AB_MOVE_PCT:.0f}%).")
    if broke_prior_high:
        notes.append("A pullback candle broke back above point B — pattern invalidated.")
    if retrace_pct >= ABCD_MAX_RETRACE_PCT:
        notes.append(f"Pullback retraced {retrace_pct * 100:.0f}% of the A-B move (max {ABCD_MAX_RETRACE_PCT * 100:.0f}%).")
    if not holds_9ema:
        notes.append(f"Pullback (point C) close did not hold the {ABCD_EMA_PERIOD} EMA.")
    if not pillars.all_pass:
        notes.append(f"Five Pillars not all met ({pillars.pass_count}/5) — no signal.")
    if not triggered:
        notes.append(f"Price has not yet broken back above point B (${b_high:.2f}).")

    pattern_found = (
        ab_move_pct >= ABCD_MIN_AB_MOVE_PCT
        and not broke_prior_high
        and retrace_pct < ABCD_MAX_RETRACE_PCT
    )

    entry_price = stop_price = target_price = None
    if pillars.all_pass and pattern_found and holds_9ema and triggered and current_price is not None:
        entry_price = round(current_price, 2)
        stop_price = round(entry_price - ABCD_MAX_STOP_DOLLARS, 2)
        risk = entry_price - stop_price
        target_price = round(entry_price + risk * ABCD_MIN_PROFIT_LOSS_RATIO, 2)
        notes.append(
            f"Signal only — entry ${entry_price:.2f}, stop ${stop_price:.2f}, "
            f"target ${target_price:.2f} ({ABCD_MIN_PROFIT_LOSS_RATIO:.0f}:1). No order has been placed."
        )

    return ABCDSignal(
        symbol=symbol,
        five_pillars=pillars,
        pattern_found=pattern_found,
        holds_9ema=holds_9ema,
        ab_move_pct=round(ab_move_pct, 2),
        retrace_pct=round(retrace_pct, 3),
        point_b_high=round(b_high, 2),
        point_c_low=round(c_low, 2),
        current_price=current_price,
        triggered=triggered,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        would_execute=False,
        notes=tuple(notes),
    )
