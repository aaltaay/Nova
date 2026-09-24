"""Session, risk, and halt adapters."""
from __future__ import annotations

import logging
import time
from typing import Any

from constants_ibkr import RISK_DAILY_GOAL_DOLLARS, RISK_MAX_CONSECUTIVE_LOSSES
from sensors.envelope import build_envelope
from sensors.session_phase import snapshot as phase_snapshot

logger = logging.getLogger(__name__)


def read_session_phase() -> dict[str, Any]:
    return build_envelope(sensor="session-phase", status="live", data=phase_snapshot())


def read_risk(symbol: str | None = None) -> dict[str, Any]:
    from strategy import risk as risk_mod

    state = risk_mod.get_state()
    row = state.to_dict()
    remaining = round(RISK_DAILY_GOAL_DOLLARS + float(state.daily_realized_pnl), 2)
    daily_hit = bool(state.halted) and "Daily max loss" in str(state.halt_reason or "")
    if float(state.daily_realized_pnl) <= -RISK_DAILY_GOAL_DOLLARS:
        daily_hit = True
    cooldown = bool(state.halted) or state.consecutive_losses >= RISK_MAX_CONSECUTIVE_LOSSES
    bot_row: dict[str, Any] = {}
    try:
        from bot.persist import load_session

        session = load_session()
        bot_row = {
            "soft_breaker_fired": bool(session.get("soft_breaker_fired")),
            "hard_lock_until_date": session.get("hard_lock_until_date"),
            "bot_level": session.get("level"),
        }
    except Exception:
        bot_row = {}
    data = {
        "daily_realized_pnl": row["daily_realized_pnl"],
        "daily_loss_limit_dollars": RISK_DAILY_GOAL_DOLLARS,
        "daily_loss_limit_remaining": remaining,
        "daily_loss_limit_hit": daily_hit,
        "cooldown_active": cooldown,
        "consecutive_losses": state.consecutive_losses,
        "consecutive_wins": state.consecutive_wins,
        "can_trade": row["can_trade"],
        "halt_reason": row["halt_reason"],
        "session_date": row["session_date"],
        **bot_row,
        "note": "Wired to strategy.risk + bot breaker session. No second risk engine.",
    }
    if symbol:
        data["symbol"] = symbol
    return build_envelope(sensor="risk", symbol=symbol, status="live", data=data)


def read_halt(symbol: str) -> dict[str, Any]:
    now = time.time()
    snap = None
    try:
        from ibkr.halt_status import snapshot

        snap = snapshot(symbol, now=now)
    except Exception:
        snap = None
    if not snap:
        # No open halt on record is "not halted" only when IBKR's halt tick or the Nasdaq halt
        # feed says so; otherwise it is unknown (ADR 035: it used to read False).
        halted = None
        try:
            from ibkr.halt_status import halted_now

            halted = halted_now([symbol], now=now).get((symbol or "").strip().upper())
        except Exception:
            logger.warning("halt sensor: halted_now failed for %s", symbol, exc_info=True)
        return build_envelope(
            sensor="halt",
            symbol=symbol,
            status="live",
            data={
                "halted": halted,
                "kind": None,
                "elapsed_sec": None,
                "source": None,
                "note": ("Not halted: IBKR's halt tick or the Nasdaq halt feed says it is trading." if halted is False
                         else "Unknown: no IBKR line has reported a halt state and the Nasdaq halt feed is not "
                              "answering -- never read as not halted."),
            },
        )
    start = snap.get("halt_start")
    elapsed = None
    if isinstance(start, (int, float)):
        elapsed = round(now - float(start), 3)
    return build_envelope(
        sensor="halt",
        symbol=symbol,
        status="live",
        data={
            "halted": True,
            "kind": snap.get("kind"),
            "halt_code": snap.get("halt_code"),
            "halt_start": start,
            "elapsed_sec": elapsed,
            "reason": snap.get("reason"),
            "rule": snap.get("rule"),
            "source": snap.get("source"),
            "start_late": snap.get("start_late"),
            "exchange": snap.get("exchange"),
        },
    )
