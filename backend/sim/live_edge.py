"""Leaving the live edge selects today's recording (ADR 020 live-edge amendment).

At the live edge a Sim tab is live and nothing needs to be loaded. The moment
the operator scrubs or pauses off it, the tab must show the past -- and the
past of a symbol Session Record is writing today is on disk. So a clock move
that leaves the edge with nothing loaded loads that symbol's usable recording
for today underneath the playhead the operator just placed, keeping the
scratch account (the recording is the tape it already traded). With no
recording the scrubbed stretch stays a stated absence: nothing is invented.

The symbol comes from the request (the tab the operator scrubbed from,
``POST /api/sim/clock {symbol}``); the backend cannot see UI tabs. A still-
recording capture already loaded is re-read on the next leave so the prints
that landed while the desk sat at the edge fold in.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def today_et() -> str:
    from sim import session_clock

    return session_clock._wall_et_now().date().isoformat()


def own_recording_today(symbol: str) -> dict[str, Any] | None:
    """The usable Session Record row of ``symbol`` for today's Eastern date, or ``None``."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    try:
        from capture.sessions import list_sessions

        rows = list_sessions().get("tickers_by_day", {}).get(today_et(), [])
    except Exception:
        logger.warning("SIM edge: capture archive unreadable, no recording selected", exc_info=True)
        return None
    for row in rows:
        if str(row.get("symbol") or "").upper() == sym and row.get("usable") and not row.get("empty"):
            return row
    return None


def _recording_now(symbol: str) -> bool:
    try:
        from capture.mode import status_payload

        return symbol in {str(s).upper() for s in status_payload().get("capture_symbols") or []}
    except Exception:
        return False


def select_recording_after_leaving(symbol: str | None, *, was_edge: bool) -> bool:
    """After a clock move: load today's recording of ``symbol`` if the desk just left the edge.

    Returns whether a recording was (re)loaded. Never raises -- the clock move
    it follows already happened and must stand.
    """
    sym = (symbol or "").strip().upper()
    if not was_edge or not sym:
        return False
    try:
        from sim import practice, replay, session_clock

        if session_clock.live_edge():
            return False
        active = practice.loaded()
        if active is not None:
            # Today's own recording of this symbol, still being written: re-read
            # it so the stretch recorded while the desk sat at the edge is there.
            same = active.source == practice.CAPTURE and active.symbol == sym and active.key[2] == today_et()
            if not (same and _recording_now(sym)):
                return False
        row = own_recording_today(sym)
        if row is None:
            return False
        result = replay.set_replay(today_et(), sym, keep_account=True, keep_playhead=True)
    except Exception:
        logger.warning("SIM edge: selecting today's recording of %s failed", sym, exc_info=True)
        return False
    ok = bool(result.get("replay_ok"))
    if ok:
        logger.info("SIM edge: left the edge -- today's recording of %s loaded under the playhead", sym)
    else:
        logger.warning("SIM edge: today's recording of %s did not load: %s", sym, result.get("replay_error"))
    return ok
