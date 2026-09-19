"""Selected capture session for Sim replay (day + ticker)."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_date: str | None = None
_symbol: str | None = None
_load_info: dict[str, Any] | None = None


def clear_capture() -> None:
    """Drop the captured day/ticker (historical selection is owned elsewhere)."""
    global _date, _symbol, _load_info
    _date = None
    _symbol = None
    _load_info = None
    try:
        from sim import capture_player as _player
        _player.unload()
    except Exception:
        logger.warning("CAPTURE PLAY: unload failed", exc_info=True)


def reset_for_tests() -> None:
    from sim import history_playback
    history_playback.clear()
    clear_capture()


def status_payload() -> dict[str, Any]:
    from sim import history_playback
    historical = history_playback.status()
    if historical:
        return dict(replay_date=historical["date"], replay_symbol=historical["symbol"],
                    replay_source="historical", replay_load=historical)
    capture = bool(_date and _symbol)
    out: dict[str, Any] = {
        "replay_date": _date,
        "replay_symbol": _symbol,
        "replay_source": "capture" if capture else "synthetic",
    }
    if _load_info:
        out["replay_load"] = _load_info
    return out


def is_capture_replay() -> bool:
    if not (_date and _symbol):
        return False
    try:
        from sim import capture_player as _player
        return _player.is_loaded()
    except Exception:
        return False


def set_replay(date: str | None, symbol: str | None) -> dict[str, Any]:
    """Select a captured day/ticker, or clear both for synthetic SIM1."""
    global _date, _symbol, _load_info
    from sim import capture_player as _player
    from sim import session_clock as _clock
    from sim import history_playback
    # Leaving historical replay keeps pause and the Eastern time of day (sim-clock.md).
    left_historical = _clock.now_et() if history_playback.status() else None
    history_playback.clear()
    _clock.set_window()

    d = (date or "").strip() or None
    s = (symbol or "").strip().upper() or None
    if not d or not s:
        _date = None
        _symbol = None
        _load_info = None
        _player.unload()
        _clock.set_session_date(None)
        if left_historical is not None:
            _clock.keep_time_of_day(left_historical)
        return status_payload()

    _date = d
    _symbol = s
    info = _player.load(d, s)
    _load_info = info
    _clock.set_session_date(d)
    # Scrub to session open so user can slide into the capture; seek emit cursor
    _clock.scrub_to_minute(0)
    try:
        _player.seek_emit_cursor(_clock.now_et().timestamp())
    except Exception:
        pass
    # If capture has prints, jump scrub near first print's session minute
    first = info.get("first_ts") if isinstance(info, dict) else None
    if isinstance(first, (int, float)) and first > 0:
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            ET = ZoneInfo("America/New_York")
            start, _end = _clock.session_bounds_on(datetime.fromtimestamp(float(first), tz=ET))
            minute = int(max(0, min((float(first) - start.timestamp()) // 60,
                                     _clock.session_seconds() // 60)))
            _clock.scrub_to_minute(minute)
            _player.seek_emit_cursor(_clock.now_et().timestamp())
        except Exception:
            logger.exception("CAPTURE PLAY: could not align scrub to first print")
    logger.info("CAPTURE PLAY: set_replay %s %s ok=%s", d, s, info.get("ok") if info else None)
    return status_payload()
