"""Selected capture session for Sim replay (day + ticker)."""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_date: str | None = None
_symbol: str | None = None
_load_info: dict[str, Any] | None = None
_generation = 0
_selection_lock = threading.RLock()


def clear_capture() -> None:
    """Drop the captured day/ticker (historical selection is owned elsewhere)."""
    global _date, _symbol, _load_info, _generation
    from sim import capture_player as _player
    with _selection_lock:
        _generation += 1
        _date = _symbol = _load_info = None
        _player.unload()


def reset_for_tests() -> None:
    from sim import history_playback
    history_playback.clear()
    clear_capture()


def status_payload() -> dict[str, Any]:
    from sim import history_playback
    historical = history_playback.status()
    if historical:
        return dict(replay_date=historical["date"], replay_symbol=historical["symbol"],
                    replay_source="historical", replay_load=historical,
                    replay_ok=True, replay_error=None)
    with _selection_lock:
        capture = is_capture_replay()
        out: dict[str, Any] = {
            "replay_date": _date,
            "replay_symbol": _symbol,
            "replay_source": "capture" if capture else "synthetic",
            "replay_ok": not _load_info or bool(_load_info.get("ok")),
            "replay_error": _load_info.get("error") if _load_info else None,
        }
        if _load_info:
            out["replay_load"] = _load_info
        return out


def is_capture_replay() -> bool:
    from sim import capture_player as _player
    with _selection_lock:
        return bool(_date and _symbol and _player.is_loaded())


def set_replay(date: str | None, symbol: str | None) -> dict[str, Any]:
    """Select a captured day/ticker, or clear both for synthetic SIM1."""
    global _date, _symbol, _load_info
    from sim import capture_player as _player
    from sim import session_clock as _clock
    from sim import history_playback
    d = (date or "").strip() or None
    s = (symbol or "").strip().upper() or None
    # Register source intent atomically in history -> capture lock order.
    # No disk load or notification fanout may run in this transition.
    with history_playback.capture_transition() as previous:
        left_historical = _clock.now_et() if previous else None
        with _selection_lock:
            clear_capture()
            generation = _generation
            _clock.set_window()
            if not d or not s:
                _clock.set_session_date(None)
                if left_historical is not None:
                    _clock.keep_time_of_day(left_historical, notify=False)
                player_generation = None
            else:
                _load_info = {"ok": False, "error": "Loading capture"}
                player_generation = _player.prepare_load()
    if not d or not s:
        _refresh_views(generation)
        return status_payload()
    try:
        info = _player.load(d, s, generation=player_generation)
    except Exception:
        logger.exception("CAPTURE PLAY: load failed for %s %s", d, s)
        info = {"ok": False, "error": f"Could not read capture {d} {s}"}
    with _selection_lock:
        if generation == _generation:
            if not info.get("ok"):
                _player.unload()
                _load_info = info
                _clock.set_session_date(None)
            else:
                _date, _symbol, _load_info = d, s, info
                _align_clock(d, info)
    _refresh_views(generation)
    # Never call historical status under the capture lock: history publication
    # owns its lock before it invalidates capture via clear_capture().
    return status_payload()


def generation_matches(expected: int) -> bool:
    with _selection_lock:
        return expected == _generation


def _refresh_views(generation: int) -> None:
    from sim import market
    if generation_matches(generation):
        market.rebuild_for_scrub(expected_capture_generation=generation)


def _align_clock(date: str, info: dict) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from sim import capture_player as player, session_clock as clock
    clock.set_session_date(date)
    clock.scrub_to_minute(0, notify=False)
    first = info.get("first_ts")
    if isinstance(first, (int, float)) and first > 0:
        start, _end = clock.session_bounds_on(datetime.fromtimestamp(first, ZoneInfo("America/New_York")))
        minute = int(max(0, min((first - start.timestamp()) // 60, clock.session_seconds() // 60)))
        clock.scrub_to_minute(minute, notify=False)
    player.seek_emit_cursor(clock.now_et().timestamp())



def fail_replay(error: str, load_info: dict | None = None) -> dict[str, Any]:
    """Drop the failed capture and expose a persistent, explicit failure."""
    global _load_info
    from sim import session_clock as _clock
    with _selection_lock:
        clear_capture()
        _load_info = {**(load_info or {}), "ok": False, "error": error}
        _clock.set_session_date(None)
    logger.warning("CAPTURE PLAY: %s", error)
    return status_payload()
