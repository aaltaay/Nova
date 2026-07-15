"""
Risk / discipline engine — a pure state machine, signal-only.

Tracks today's realized P&L and enforces the course's walk-away guardrails
(daily max loss, 3-losses-in-a-row, giving back half of the day's peak
profit). Also computes position size (100-share blocks, quarter size until
a profit cushion, cut size after a meaningful loss) and validates a proposed
trade plan's stop distance and profit/loss ratio.

This module NEVER places, modifies, or cancels an order — it only answers
"is it OK to trade right now, and how big." `backend/strategy/executor.py`
(Phase D paper execution) calls `can_trade()` and `position_size_shares()`
before sizing a bracket, and `record_trade_result()` after a fill closes.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    losses_today: int = 0
    trades_today: int = 0
    halted: bool = False
    halt_reason: str | None = None
    session_date: str = field(default_factory=lambda: datetime.now(_ET).strftime("%Y-%m-%d"))

    def reset_day(self) -> None:
        self.daily_realized_pnl = 0.0
        self.peak_daily_pnl = 0.0
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.losses_today = 0
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
            self.losses_today += 1
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
        try:
            # Lazy import — nova_os.events has no dependency back on
            # strategy, but importing it at module load time would still
            # add an avoidable load-order coupling for a rarely-hit path.
            from nova_os.events import KIND_SYSTEM, record_receipt

            record_receipt(
                kind=KIND_SYSTEM,
                payload={
                    "event": "risk_halt",
                    "reason": reason,
                    "daily_realized_pnl": round(self.daily_realized_pnl, 2),
                    "consecutive_losses": self.consecutive_losses,
                    "losses_today": self.losses_today,
                },
            )
        except Exception:
            logger.exception("Risk engine: failed to journal risk_halt event")

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
            "losses_today": self.losses_today,
            "trades_today": self.trades_today,
            "can_trade": can_trade,
            "halt_reason": None if can_trade else reason,
            "position_size_shares": self.position_size_shares(),
            "daily_goal_dollars": RISK_DAILY_GOAL_DOLLARS,
        }


def validate_trade_plan(entry_price: float, stop_price: float, target_price: float) -> tuple[bool, list[str]]:
    """Check a proposed long trade's stop distance and profit/loss ratio against
    the risk rules. Returns (ok, issues) — ok is False if any rule blocks the
    trade; issues includes both blocking problems and informational notes.

    Long-only: stop must be strictly below entry and target strictly above.
    Using abs() here would let inverted plans (stop above entry) slip through.
    """
    issues: list[str] = []
    blocking = False

    if stop_price >= entry_price:
        issues.append(
            f"Stop ${stop_price:.2f} must be below entry ${entry_price:.2f} for a long."
        )
        blocking = True
    if target_price <= entry_price:
        issues.append(
            f"Target ${target_price:.2f} must be above entry ${entry_price:.2f} for a long."
        )
        blocking = True

    stop_distance = round(entry_price - stop_price, 2)
    reward = round(target_price - entry_price, 2)

    if stop_distance <= 0:
        # Directional failure already recorded when stop >= entry; keep the
        # legacy zero-distance message when stop exactly equals entry.
        if stop_distance == 0:
            issues.append("Stop distance is zero — cannot size or validate this trade.")
        return False, issues

    if stop_distance > RISK_MAX_STOP_DOLLARS:
        issues.append(f"Stop of ${stop_distance:.2f} exceeds the ${RISK_MAX_STOP_DOLLARS:.2f} max.")
        blocking = True

    if reward > 0:
        ratio = reward / stop_distance
        if ratio < RISK_MIN_PROFIT_LOSS_RATIO:
            issues.append(
                f"Profit/loss ratio {ratio:.1f}:1 is below the {RISK_MIN_PROFIT_LOSS_RATIO:.0f}:1 floor."
            )
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


def _session_start_epoch(now_et: datetime | None = None) -> float:
    """Epoch seconds of the current trading session's start (today's — or
    yesterday's, before the reset hour — RISK_SESSION_RESET_HOUR_ET in ET)."""
    now_et = now_et or datetime.now(_ET)
    start = now_et.replace(hour=RISK_SESSION_RESET_HOUR_ET, minute=0, second=0, microsecond=0)
    if now_et.hour < RISK_SESSION_RESET_HOUR_ET:
        start -= timedelta(days=1)
    return start.timestamp()


def reconstruct_from_journal() -> dict:
    """Rebuild today's daily risk state from the trade journal after a
    process restart. RiskState is in-memory only and always starts fresh on
    boot; without this, a mid-session restart silently forgets losses/halts
    that were about to trip a walk-away guardrail — a trader could resume
    trading under a false "clean day" state. Replays every closed trade
    since the current session's reset boundary, in order, through the same
    record_trade_result() the live fill loop uses, so halts/loss-policy
    counters land exactly where they would have without the restart."""
    from journal.store import get_closed_trades

    _state.reset_day()
    session_start = _session_start_epoch()
    try:
        trades = get_closed_trades()
    except Exception:
        logger.exception("Risk engine: failed to reconstruct daily state from journal")
        return _state.to_dict()

    replayed = 0
    for row in trades:
        closed_ts = row.get("closed_ts")
        pnl = row.get("pnl")
        if closed_ts is None or pnl is None:
            continue
        try:
            if float(closed_ts) < session_start:
                continue
        except (TypeError, ValueError):
            continue
        _state.record_trade_result(float(pnl))
        replayed += 1

    if replayed:
        logger.warning(
            "Risk engine: reconstructed %s trade(s) for session %s — "
            "daily_pnl=%.2f consecutive_losses=%s losses_today=%s halted=%s (%s)",
            replayed,
            _state.session_date,
            _state.daily_realized_pnl,
            _state.consecutive_losses,
            _state.losses_today,
            _state.halted,
            _state.halt_reason,
        )
    else:
        logger.info("Risk engine: no trades to reconstruct for session %s", _state.session_date)
    return _state.to_dict()


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
