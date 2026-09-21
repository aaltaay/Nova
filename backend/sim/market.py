"""Sim venue market projections for a loaded capture replay.

There is no synthetic instrument: with no capture loaded every view is empty,
and a historical window serves its own snapshots (ADR 017, #315). Bar
timestamps are UTC ISO strings (frontend RawBar.t / isoToEtTime).
"""
from __future__ import annotations

import logging
from datetime import timezone
from typing import Any

from sim import session_clock as _clock
from sim.market_views import book, last_quotes, quote, ticker_snapshot  # noqa: F401 - public compatibility API

logger = logging.getLogger(__name__)


def rebuild_for_scrub(*, expected_capture_generation: int | None = None) -> None:
    """Reseed tape/depth outside selection locks; reject superseded selections."""
    from sim import capture_player as player, replay
    def current() -> bool:
        return (expected_capture_generation is None
                or replay.generation_matches(expected_capture_generation))
    if not current():
        return
    if not replay.is_capture_replay():
        return
    selection = player.snapshot()
    if selection is None:
        return
    def selected() -> bool:
        return current() and player.snapshot() is selection
    try:
        from ibkr.tape_stream import _push_queue
        from ibkr.depth import state as depth_state
        now_ts = _clock.now_et().timestamp()
        if not selected():
            return
        player.seek_emit_cursor(now_ts, state=selection)
        _push_queue(selection.symbol, {"type": "scrub_reset", "symbol": selection.symbol})
        rows = player.recent_prints(40, state=selection)
        for row in rows:
            if not selected():
                return
            _push_queue(selection.symbol, {**row, "type": "print", "symbol": selection.symbol})
        if rows:
            player.mark_emitted(now_ts, state=selection)
        book = player.book_at(state=selection)
        if book is not None and selected():
            depth_state.push_book(selection.symbol, {**book, "symbol": selection.symbol})
    except Exception:
        logger.warning("CAPTURE: scrub projection failed", exc_info=True)


def recent_prints(limit: int = 20) -> list[dict[str, Any]]:
    from sim import capture_player, replay

    if replay.is_capture_replay():
        return capture_player.recent_prints(limit)
    return []


def _now_iso() -> str:
    # Sim clock, so a scrub moves print times and chart as_of together.
    return _clock.now_et().astimezone(timezone.utc).isoformat()
