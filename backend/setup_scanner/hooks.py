"""The setup scanner engine's default wiring to the rest of Nova (ADR 022).

Each hook is what ``SetupEngine`` calls in production; tests and replays pass
their own. Moved out of ``engine.py`` unchanged so the engine stays inside the
file-size budget. Owner: ``setup_scanner/engine.py`` (no state here).
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any, Iterable

from constants_setups import (
    SETUPS_BAR_SEC,
    SETUPS_SEED_HISTORY_TIMEOUT_SEC,
    SETUPS_SEED_LATE_START_SEC,
)
from setup_scanner.bars import MAX_BARS_PER_SYMBOL, Bar, minute_start, stored_bars
from setup_scanner.seeder import SEED_COVERED, SEED_FAILED, SEED_FILLED, SEED_SHED, late_start, send_wait

logger = logging.getLogger(__name__)


def default_universe() -> Iterable[str]:
    from hod_momo_active import get_active_symbols

    return get_active_symbols()


def default_seed(symbol: str, from_ts: float) -> list[Bar]:
    """The session's stored minutes from ``from_ts`` (its 04:00) through its last closed one (19:59 ET at most).

    The read keeps the newest rows, so minutes the store holds past the close (built from IBKR's
    overnight session until those were kept out) pushed a busy day's morning out of the seed:
    QTEX's at the 2026-10-01 23:32 restart began at 07:27, 207 overnight minutes in. The minute now
    forming is left out: IBKR's history holds it half-made, and the Level 1 line's own bar for it
    must win (``MinuteBars.append`` ignores a minute it already has)."""
    import bars_store
    from market import trading_session_bounds

    bounds = trading_session_bounds(from_ts)
    through = min(bounds[1] if bounds else math.inf, minute_start(time.time())) - SETUPS_BAR_SEC
    return stored_bars(bars_store.read(symbol, "1Min", MAX_BARS_PER_SYMBOL, from_ts=from_ts, through_ts=through))


_last_history_send = -math.inf     # the scanner's last history request (monotonic; the IB loop's)


async def live_history(symbol: str, from_ts: float) -> tuple[str, str | None]:
    """Today's 1-minute history from IBKR into the bar store, for a seed that came back short (``seeder``).

    ``covered`` with no request when IBKR filled today's minutes and the stored ones start by then
    (within ``SETUPS_SEED_LATE_START_SEC`` of the fill): a stock that first traded at 07:25 has nothing
    before then. Otherwise one background request through the paced historical service -- the charts'
    own path (``request_bars``), which writes the store and pushes the chart -- sent only when
    ``seeder.send_wait`` allows; ``shed`` when it does not, and the seeder asks again.
    """
    import bars_store
    from ibkr import client
    from ibkr.loop_supervisor import on_ib

    sym = symbol.strip().upper()
    stored = await asyncio.to_thread(bars_store.read, sym, "1Min", MAX_BARS_PER_SYMBOL, from_ts=from_ts)
    fetched = float(((stored or {}).get("coverage") or {}).get("fetched_ts") or 0.0)
    if fetched >= from_ts and late_start(stored_bars(stored), fetched, time.time()) <= SETUPS_SEED_LATE_START_SEC:
        return SEED_COVERED, None
    if not client.is_ready():
        return SEED_SHED, "IBKR is not ready"
    try:
        return await on_ib(_ask_history(sym), SETUPS_SEED_HISTORY_TIMEOUT_SEC, label=f"setups.seed.{sym}")
    except asyncio.TimeoutError:
        return SEED_FAILED, f"no answer within {SETUPS_SEED_HISTORY_TIMEOUT_SEC:.0f}s"


async def _ask_history(sym: str) -> tuple[str, str | None]:
    """On the IB loop: one paced background request for today's 1-minute bars (``historical_service``)."""
    global _last_history_send
    from fastapi import HTTPException

    from ibkr import historical_service as hist

    now = time.monotonic()
    wait = send_wait(now, _last_history_send, int(hist.pacing_snapshot().get("window_used") or 0),
                     hist.open_chart_busy())
    if wait is not None:
        return SEED_SHED, wait
    _last_history_send = now
    try:
        await hist.request_bars(sym, "1Min", MAX_BARS_PER_SYMBOL, priority="background")
    except hist.HistoricalShed as exc:
        return SEED_SHED, str(exc)
    except HTTPException as exc:
        return SEED_FAILED, str(exc.detail)
    return SEED_FILLED, None


def default_replay_desk() -> bool:
    try:
        from sim.mode import is_replay_desk

        return bool(is_replay_desk())
    except Exception:
        logger.debug("setup scanner: venue check failed", exc_info=True)
        return False


def default_audit(**kw: Any) -> None:
    try:
        from bot.audit import record

        record(**kw)
    except Exception:
        logger.warning("setup scanner: bot audit write failed", exc_info=True)


def default_templates() -> Any:
    """The operator's templates (ADR 029): ``setup_templates.store``."""
    from setup_templates.store import get_store

    return get_store()


def default_journal(event: dict) -> None:
    """Every observation to the eyes' journal (ADR 029); it never blocks."""
    from eyes import journal

    journal.record(event)


_BOT_STATE_TTL_SEC = 2.0
_bot_state_cache: tuple[float, dict] | None = None


def default_bot_state() -> dict:
    """The stamp on a journal line: the bot's level and Activate, and the venue (cached briefly)."""
    global _bot_state_cache
    import time

    now = time.monotonic()
    if _bot_state_cache is not None and now - _bot_state_cache[0] < _BOT_STATE_TTL_SEC:
        return _bot_state_cache[1]
    state: dict[str, Any] = {"level": None, "active": None, "venue": None}
    try:
        from bot.arming import is_desk_active
        from bot.persist import load_session

        row = load_session()
        state["level"] = int(row.get("level") or 0)
        state["active"] = bool(is_desk_active(row))
    except Exception:
        logger.debug("setup scanner: bot state unread for the journal", exc_info=True)
    try:
        from sim.mode import venue

        state["venue"] = venue()
    except Exception:
        logger.debug("setup scanner: venue unread for the journal", exc_info=True)
    _bot_state_cache = (now, state)
    return state


_LEVELS_TTL_SEC = 1.0
_levels_cache: tuple[float, dict] | None = None


def default_levels() -> dict:
    """``{"chosen": SETUP, "levels": {SETUP: 0 | 1 | 2}}`` from the bot session (ADR 031), cached briefly.

    The chosen setup's level is the session's; every other setup with a scanner has
    its own (``setup_levels``), Off when unset. An unreadable session reads every
    setup Off: no proposal is ever raised on a guess.
    """
    global _levels_cache
    import time

    now = time.monotonic()
    if _levels_cache is not None and now - _levels_cache[0] < _LEVELS_TTL_SEC:
        return _levels_cache[1]
    try:
        from bot.persist import load_session
        from bot.setup_levels import levels_of

        out = levels_of(load_session())
    except Exception:
        logger.warning("setup scanner: bot levels unread -- every setup proposes nothing", exc_info=True)
        out = {"chosen": None, "levels": {}}
    _levels_cache = (now, out)
    return out


def reset_levels_cache() -> None:
    global _levels_cache
    _levels_cache = None


def default_sim_eyes() -> Any:
    """The Sim eyes over a loaded Session Record, when the desk shows one (ADR 029)."""
    from eyes.sim_eyes import get_sim_eyes

    return get_sim_eyes()


def no_catalysts(symbols: Iterable[str]) -> None:
    """Tests and replays: no catalyst fetch (the live one is wired in ``get_engine``)."""


def live_catalysts(symbols: Iterable[str]) -> None:
    from catalysts import live as catalyst_live

    catalyst_live.request(symbols)
