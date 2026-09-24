"""The setup scanner engine's default wiring to the rest of Nova (ADR 022).

Each hook is what ``SetupEngine`` calls in production; tests and replays pass
their own. Moved out of ``engine.py`` unchanged so the engine stays inside the
file-size budget. Owner: ``setup_scanner/engine.py`` (no state here).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from setup_scanner.bars import Bar, stored_bars

logger = logging.getLogger(__name__)


def default_universe() -> Iterable[str]:
    from hod_momo_active import get_active_symbols

    return get_active_symbols()


def default_seed(symbol: str, from_ts: float) -> list[Bar]:
    import bars_store

    return stored_bars(bars_store.read(symbol, "1Min", 960, from_ts=from_ts))


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


def default_sim_eyes() -> Any:
    """The Sim eyes over a loaded Session Record, when the desk shows one (ADR 029)."""
    from eyes.sim_eyes import get_sim_eyes

    return get_sim_eyes()


def no_catalysts(symbols: Iterable[str]) -> None:
    """Tests and replays: no catalyst fetch (the live one is wired in ``get_engine``)."""


def live_catalysts(symbols: Iterable[str]) -> None:
    from catalysts import live as catalyst_live

    catalyst_live.request(symbols)
