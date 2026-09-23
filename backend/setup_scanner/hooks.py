"""The setup scanner engine's default wiring to the rest of Nova (ADR 022).

Each hook is what ``SetupEngine`` calls in production; tests and replays pass
their own. Moved out of ``engine.py`` unchanged so the engine stays inside the
file-size budget. Owner: ``setup_scanner/engine.py`` (no state here).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from setup_scanner.bars import Bar, bar_from

logger = logging.getLogger(__name__)


def default_universe() -> Iterable[str]:
    from hod_momo_active import get_active_symbols

    return get_active_symbols()


def default_seed(symbol: str, from_ts: float) -> list[Bar]:
    import bars_store

    res = bars_store.read(symbol, "1Min", 960, from_ts=from_ts)
    return [b for b in (bar_from(r) for r in (res or {}).get("bars") or []) if b is not None]


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


def no_catalysts(symbols: Iterable[str]) -> None:
    """Tests and replays: no catalyst fetch (the live one is wired in ``get_engine``)."""


def live_catalysts(symbols: Iterable[str]) -> None:
    from catalysts import live as catalyst_live

    catalyst_live.request(symbols)
