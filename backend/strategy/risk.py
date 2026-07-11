"""
Risk / discipline engine — a pure state machine, signal-only.

Tracks today's realized P&L and enforces the course's walk-away guardrails
(daily max loss, 3-losses-in-a-row, giving back half of the day's peak
profit). Also computes position size (100-share blocks, quarter size until
a profit cushion, cut size after a meaningful loss) and validates a proposed
trade plan's stop distance and profit/loss ratio.

This module NEVER places, modifies, or cancels an order — it only answers
"is it OK to trade right now, and how big." Phase D (paper execution) is
expected to call `can_trade()` and `position_size_shares()` before sizing an
order, and `record_trade_result()` after a fill closes, but no such wiring
exists yet.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from constants import (
    RISK_BASE_SHARE_BLOCK,
    RISK_DAILY_GOAL_DOLLARS,
    RISK_MAX_CONSECUTIVE_LOSSES,
    RISK_MAX_GIVEBACK_FRACTION_OF_PEAK,
    RISK_MAX_STOP_DOLLARS,
    RISK_MIN_PROFIT_LOSS_RATIO,
    RISK_PROFIT_CUSHION_FRACTION,
    RISK_QUARTER_SIZE_MULTIPLIER,
    RISK_SESSION_RESET_HOUR_ET,
    RISK_SIZE_CUT_LOSS_FRACTION_OF_GOAL,
    RISK_SIZE_CUT_MULTIPLIER,
)

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")


@dataclass
class RiskState:
    """Mutable daily discipline state. One instance per trading day."""

    daily_realized_pnl: float = 0.0
    peak_daily_pnl: float = 0.0
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    trades_today: int = 0
    halted: bool = False
    halt_reason: str | None = None
    session_date: str = field(default_factory=lambda: datetime.now(_ET).strftime("%Y-%m-%d"))

    def reset_day(self) -> None:
        self.daily_realized_pnl = 0.0
        self.peak_daily_pnl = 0.0
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.trades_today = 0
        self.halted = False
        self.halt_reason = None
        self.session_date = datetime.now(_ET).strftime("%Y-%m-%d")

    def record_trade_result(self, pnl: float) -> None:
        """Record a closed trade's realized P&L and re-check the guardrails.
        Once halted for the day, stays halted until reset_day()."""
        self.trades_today += 1
        self.daily_realized_pnl += pnl
        self.peak_daily_pnl = max(self.peak_daily_pnl, self.daily_realized_pnl)

        if pnl < 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        elif pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0

        if not self.halted:
            self._check_halt_conditions()

    def _check_halt_conditions(self) -> None:
        if self.daily_realized_pnl <= -RISK_DAILY_GOAL_DOLLARS:
            self._halt("Daily max loss reached — walk away for the day.")
        elif self.consecutive_losses >= RISK_MAX_CONSECUTIVE_LOSSES:
            self._halt(f"{self.consecutive_losses} losses in a row — walk away guardrail.")
        elif self.peak_daily_pnl > 0:
            giveback = self.peak_daily_pnl - self.daily_realized_pnl
            if giveback >= self.peak_daily_pnl * RISK_MAX_GIVEBACK_FRACTION_OF_PEAK:
                self._halt(
                    f"Gave back {giveback / self.peak_daily_pnl * 100:.0f}% of today's peak "
                    "profit — walk away guardrail."
                )

    def _halt(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason

    def can_trade(self) -> tuple[bool, str]:
        if self.halted:
            return False, self.halt_reason or "Halted."
        return True, "OK"

    def _lost_more_than_cut_threshold(self) -> bool:
        return self.daily_realized_pnl <= -(RISK_DAILY_GOAL_DOLLARS * RISK_SIZE_CUT_LOSS_FRACTION_OF_GOAL)

    def _reached_profit_cushion(self) -> bool:
        return self.daily_realized_pnl >= RISK_DAILY_GOAL_DOLLARS * RISK_PROFIT_CUSHION_FRACTION

    def position_size_shares(self) -> int:
        """100-share blocks; quarter size until a profit cushion, then full
        size; cut size after losing more than the cut threshold of the day."""
        if self._reached_profit_cushion():
            size = RISK_BASE_SHARE_BLOCK
        else:
            size = RISK_BASE_SHARE_BLOCK * RISK_QUARTER_SIZE_MULTIPLIER
        if self._lost_more_than_cut_threshold():
            size *= RISK_SIZE_CUT_MULTIPLIER
        return int(size)

    def to_dict(self) -> dict:
        can_trade, reason = self.can_trade()
        return {
            "session_date": self.session_date,
            "daily_realized_pnl": round(self.daily_realized_pnl, 2),
            "peak_daily_pnl": round(self.peak_daily_pnl, 2),
            "consecutive_losses": self.consecutive_losses,
            "consecutive_wins": self.consecutive_wins,
            "trades_today": self.trades_today,
            "can_trade": can_trade,
            "halt_reason": None if can_trade else reason,
            "position_size_shares": self.position_size_shares(),
            "daily_goal_dollars": RISK_DAILY_GOAL_DOLLARS,
        }


def validate_trade_plan(entry_price: float, stop_price: float, target_price: float) -> tuple[bool, list[str]]:
    """Check a proposed trade's stop distance and profit/loss ratio against
    the risk rules. Returns (ok, issues) — ok is False if any rule blocks the
    trade; issues includes both blocking problems and informational notes."""
    issues: list[str] = []
    stop_distance = abs(entry_price - stop_price)
    reward = abs(target_price - entry_price)

    if stop_distance <= 0:
        return False, ["Stop distance is zero — cannot size or validate this trade."]

    blocking = False
    if stop_distance > RISK_MAX_STOP_DOLLARS:
        issues.append(f"Stop of ${stop_distance:.2f} exceeds the ${RISK_MAX_STOP_DOLLARS:.2f} max.")
        blocking = True

    ratio = reward / stop_distance
    if ratio < RISK_MIN_PROFIT_LOSS_RATIO:
        issues.append(f"Profit/loss ratio {ratio:.1f}:1 is below the {RISK_MIN_PROFIT_LOSS_RATIO:.0f}:1 floor.")
        blocking = True

    return not blocking, issues


# ── Module-level singleton — mirrors hod_momo.py's session-state pattern ────

_state = RiskState()


def get_state() -> RiskState:
    return _state


def reset_day() -> None:
    _state.reset_day()


def record_trade_result(pnl: float) -> None:
    _state.record_trade_result(pnl)


def can_trade() -> tuple[bool, str]:
    return _state.can_trade()


def position_size_shares() -> int:
    return _state.position_size_shares()


def _check_and_reset_session() -> bool:
    now_et = datetime.now(_ET)
    if now_et.hour < RISK_SESSION_RESET_HOUR_ET:
        return False
    current = now_et.strftime("%Y-%m-%d")
    if current == _state.session_date:
        return False
    logger.info("Risk engine: session rollover -> %s (was %s)", current, _state.session_date)
    _state.reset_day()
    return True


async def session_reset_loop() -> None:
    """Background asyncio task: checks for session rollover every 30 seconds."""
    while True:
        try:
            await asyncio.sleep(30.0)
            _check_and_reset_session()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Risk engine session reset loop error")
