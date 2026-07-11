"""
Bull Flag setup detection — signal-only.

Pattern (SS101 Ch.5): a flagpole of 3+ consecutive green candles, followed by
a shallow pullback of 2+ candles that hold above the 9 EMA and don't retrace
more than half the flagpole's move, with entry on a break back above the
flagpole high.

Like gap_and_go.py, this module never places an order. `would_execute` is
hard-coded to False.
"""

from __future__ import annotations

from dataclasses import dataclass

from constants import (
    BULL_FLAG_EMA_PERIOD,
    BULL_FLAG_MAX_RETRACE_PCT,
    BULL_FLAG_MIN_FLAGPOLE_CANDLES,
    BULL_FLAG_MIN_PROFIT_LOSS_RATIO,
    BULL_FLAG_MIN_PULLBACK_CANDLES,
)
from strategy.five_pillars import FivePillarsResult, evaluate_five_pillars
from strategy.indicators import closes, ema, is_green, is_red


@dataclass(frozen=True)
class BullFlagSignal:
    symbol: str
    five_pillars: FivePillarsResult
    pattern_found: bool
    holds_9ema: bool
    retrace_pct: float | None
    flagpole_high: float | None
    pullback_low: float | None
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
            "retrace_pct": self.retrace_pct,
            "flagpole_high": self.flagpole_high,
            "pullback_low": self.pullback_low,
            "current_price": self.current_price,
            "triggered": self.triggered,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "five_pillars": self.five_pillars.to_dict(),
            "notes": list(self.notes),
        }


def _find_flagpole_and_pullback(bars: list[dict]) -> tuple[list[dict], list[dict]] | tuple[None, None]:
    """Scan trailing bars for a pullback run preceded by a flagpole run."""
    n = len(bars)
    i = n - 1
    pullback_idx: list[int] = []
    while i >= 0 and is_red(bars[i]):
        pullback_idx.append(i)
        i -= 1
    pullback_idx.reverse()
    if len(pullback_idx) < BULL_FLAG_MIN_PULLBACK_CANDLES:
        return None, None

    j = i
    flagpole_idx: list[int] = []
    while j >= 0 and is_green(bars[j]):
        flagpole_idx.append(j)
        j -= 1
    flagpole_idx.reverse()
    if len(flagpole_idx) < BULL_FLAG_MIN_FLAGPOLE_CANDLES:
        return None, None

    return [bars[k] for k in flagpole_idx], [bars[k] for k in pullback_idx]


def evaluate_bull_flag(candidate: dict, bars: list[dict]) -> BullFlagSignal:
    """Evaluate the Bull Flag setup using recent 1-min bars (ascending order)."""
    symbol = candidate.get("symbol", "?")
    pillars = evaluate_five_pillars(candidate)
    current_price = candidate.get("price", candidate.get("current_price"))

    flagpole, pullback = _find_flagpole_and_pullback(bars)
    notes: list[str] = []

    if flagpole is None or pullback is None:
        if not pillars.all_pass:
            notes.append(f"Five Pillars not all met ({pillars.pass_count}/5) — no signal.")
        notes.append(
            f"No flagpole ({BULL_FLAG_MIN_FLAGPOLE_CANDLES}+ green) + pullback "
            f"({BULL_FLAG_MIN_PULLBACK_CANDLES}+ red) pattern in recent bars."
        )
        return BullFlagSignal(
            symbol=symbol, five_pillars=pillars, pattern_found=False, holds_9ema=False,
            retrace_pct=None, flagpole_high=None, pullback_low=None, current_price=current_price,
            triggered=False, entry_price=None, stop_price=None, target_price=None,
            would_execute=False, notes=tuple(notes),
        )

    flagpole_low = min(b["l"] for b in flagpole)
    flagpole_high = max(b["h"] for b in flagpole)
    pullback_low = min(b["l"] for b in pullback)
    broke_prior_high = any(b["h"] > flagpole_high for b in pullback)

    denom = flagpole_high - flagpole_low
    retrace_pct = (flagpole_high - pullback_low) / denom if denom > 0 else 1.0

    ema_series = ema(closes(bars), BULL_FLAG_EMA_PERIOD)
    last_pullback_close = pullback[-1]["c"]
    last_pullback_ema = ema_series[-1]
    holds_9ema = last_pullback_ema is not None and last_pullback_close >= last_pullback_ema

    triggered = bool(current_price is not None and current_price > flagpole_high)

    if broke_prior_high:
        notes.append("Pullback candle broke back above the flagpole high — pattern invalidated.")
    if retrace_pct >= BULL_FLAG_MAX_RETRACE_PCT:
        notes.append(f"Pullback retraced {retrace_pct * 100:.0f}% of the pole (max {BULL_FLAG_MAX_RETRACE_PCT * 100:.0f}%).")
    if not holds_9ema:
        notes.append(f"Pullback close did not hold the {BULL_FLAG_EMA_PERIOD} EMA.")
    if not pillars.all_pass:
        notes.append(f"Five Pillars not all met ({pillars.pass_count}/5) — no signal.")
    if not triggered:
        notes.append(f"Price has not yet broken back above the flagpole high (${flagpole_high:.2f}).")

    pattern_found = not broke_prior_high and retrace_pct < BULL_FLAG_MAX_RETRACE_PCT

    entry_price = stop_price = target_price = None
    if pillars.all_pass and pattern_found and holds_9ema and triggered and current_price is not None:
        entry_price = round(current_price, 2)
        stop_price = round(pullback_low, 2)
        if stop_price < entry_price:
            risk = entry_price - stop_price
            target_price = round(entry_price + risk * BULL_FLAG_MIN_PROFIT_LOSS_RATIO, 2)
            notes.append(
                f"Signal only — entry ${entry_price:.2f}, stop ${stop_price:.2f}, "
                f"target ${target_price:.2f} ({BULL_FLAG_MIN_PROFIT_LOSS_RATIO:.0f}:1). No order has been placed."
            )
        else:
            entry_price = stop_price = None
            notes.append("Pullback low is not below current price — cannot compute a valid stop.")

    return BullFlagSignal(
        symbol=symbol,
        five_pillars=pillars,
        pattern_found=pattern_found,
        holds_9ema=holds_9ema,
        retrace_pct=round(retrace_pct, 3),
        flagpole_high=round(flagpole_high, 2),
        pullback_low=round(pullback_low, 2),
        current_price=current_price,
        triggered=triggered,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        would_execute=False,
        notes=tuple(notes),
    )
