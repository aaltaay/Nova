"""Resume, then say so (operator decision, 2026-09-21).

A Session Record is owned by this process and nothing on the page can stop it.
What can: a process restart, a recorder that stops itself (disk, timestamp,
writer backlog), and an IBKR line that drops with the Gateway. The market only
happens once, so the policy for all three is the same -- get back up into a new
segment on your own, and tell the operator what happened -- bounded so a dead
disk cannot loop forever, never across a day boundary, never onto a different
symbol, and cancelled the moment the operator stops or starts something else.

State here is process memory. The manifest on disk is the durable record; this
module only decides when to call ``start`` again and what ``/api/ibkr/status``
says about it.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from capture.constants_capture import (
    CAPTURE_KEEPALIVE_INTERVAL_SEC,
    CAPTURE_RESUME_BACKOFF_SEC,
    CAPTURE_RESUME_MAX_ATTEMPTS,
    CAPTURE_RESUME_RESTART_WINDOW_SEC,
    CAPTURE_STOP_FAILURE,
    CAPTURE_STOP_RESTART,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

# The symbol the last tick saw recording; a tick that finds nothing recording
# without an operator stop in between has found an unplanned stop.
_watched: str | None = None
# A resume in flight: symbol, why, attempts so far, when next.
_resume: dict[str, Any] | None = None
# The last stop the operator did not ask for -- what the UI shouts about.
_stopped: dict[str, Any] | None = None
# IBKR lines re-acquired after a Gateway drop, for the running session's status.
_reacquired = 0


def reset_for_tests() -> None:
    global _watched, _resume, _stopped, _reacquired
    _watched = None
    _resume = None
    _stopped = None
    _reacquired = 0


def _today_et(now: float) -> str:
    return datetime.fromtimestamp(now, ET).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Operator intent


def operator_stopped(symbol: str | None) -> None:
    """The operator asked for the stop: nothing to resume, nothing to shout."""
    global _watched, _resume, _stopped
    _watched = None
    _resume = None
    _stopped = None


def operator_started(symbol: str) -> None:
    """A recording the operator started supersedes any pending resume or old stop."""
    global _resume, _stopped
    _resume = None
    _stopped = None


# ---------------------------------------------------------------------------
# Restart


def note_restart(summary: dict[str, Any] | None, *, now: float | None = None) -> bool:
    """A recording the previous process died during: resume it if it is today's and recent."""
    global _resume, _stopped
    if not summary or not summary.get("symbol"):
        return False
    now = time.time() if now is None else now
    symbol = str(summary["symbol"]).upper()
    last_write = summary.get("last_write_ts")
    recent = isinstance(last_write, (int, float)) and now - last_write <= CAPTURE_RESUME_RESTART_WINDOW_SEC
    today = summary.get("session_date") == _today_et(now)
    if not (recent and today):
        logger.info("CAPTURE: not resuming %s after restart (today=%s recent=%s)", symbol, today, recent)
        return False
    _stopped = {
        "symbol": symbol,
        "at": float(last_write),
        "reason": CAPTURE_STOP_RESTART,
        "error": None,
        "dir": summary.get("dir"),
        "counts": dict(summary.get("counts") or {}),
        "resumed": False,
    }
    _resume = _new_resume(symbol, CAPTURE_STOP_RESTART, None, summary.get("session_date"), now, first_delay=0.0)
    logger.warning("CAPTURE: %s was recording when the previous process died -- resuming", symbol)
    return True


def _new_resume(symbol: str, reason: str, error: str | None, session_date: Any, now: float,
                *, first_delay: float) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "reason": reason,
        "error": error,
        "session_date": str(session_date or _today_et(now)),
        "attempt": 0,
        "max_attempts": CAPTURE_RESUME_MAX_ATTEMPTS,
        "next_at": now + first_delay,
        "gave_up": False,
        "gave_up_reason": None,
        "pending": True,
    }


# ---------------------------------------------------------------------------
# One tick


async def tick(
    *,
    now: float,
    payload: dict[str, Any],
    recorder_status: dict[str, Any],
    ready: Callable[[], bool],
    acquire: Callable[[str], Awaitable[str | None]],
    release: Callable[[str], Awaitable[None]],
    start: Callable[[str], Awaitable[dict[str, Any]]],
) -> None:
    """Observe the recording once; resume or re-acquire where the policy says so.

    ``payload`` is ``capture.mode.status_payload()`` and ``recorder_status`` is
    ``capture.recorder.status()``, both taken by the caller off the loop.
    """
    global _watched, _resume, _stopped, _reacquired
    recording = bool(payload.get("capture"))
    symbol = payload.get("capture_symbol")
    if recording and symbol:
        if _resume and _resume["symbol"] == symbol:
            _resume = None  # whoever started it, the resume is done
            if _stopped and _stopped["symbol"] == symbol:
                _stopped["resumed"] = True
        _watched = symbol
        producer = payload.get("producer") or {}
        # Gateway drop: the tape line is gone but the client is back. Take the
        # lines again; the recorder never stopped, so this is a gap, not a segment.
        if producer.get("state") == "disconnected" and ready():
            await release(symbol)
            error = await acquire(symbol)
            if error:
                logger.warning("CAPTURE: re-acquire of IBKR lines for %s failed: %s", symbol, error)
            else:
                _reacquired += 1
                logger.warning("CAPTURE: IBKR lines re-acquired for %s after a Gateway drop", symbol)
        return

    if _watched:
        # Nothing is recording and the operator did not stop it: it died.
        died = _watched
        _watched = None
        error = payload.get("error") or recorder_status.get("error")
        _stopped = {
            "symbol": died,
            "at": now,
            "reason": CAPTURE_STOP_FAILURE,
            "error": error,
            "dir": recorder_status.get("dir"),
            "counts": dict(recorder_status.get("counts") or {}),
            "resumed": False,
        }
        _resume = _new_resume(died, CAPTURE_STOP_FAILURE, error, recorder_status.get("session_date"), now,
                              first_delay=CAPTURE_RESUME_BACKOFF_SEC[0])
        logger.error("CAPTURE: recording of %s stopped on its own (%s) -- will resume", died, error)

    if not _resume or _resume["gave_up"] or now < _resume["next_at"]:
        return
    if _resume["session_date"] != _today_et(now):
        _give_up("the session day ended")
        return
    if not ready():
        # IBKR is not usable; that is not the recorder's fault, so it costs no
        # attempt. Try again next tick.
        _resume["next_at"] = now + CAPTURE_KEEPALIVE_INTERVAL_SEC
        return
    sym = _resume["symbol"]
    _resume["attempt"] += 1
    error = await acquire(sym)
    if not error:
        out = await start(sym)
        error = None if out.get("capture") and out.get("capture_symbol") == sym else (
            out.get("error") or out.get("detail") or "Recorder did not start")
    if error is None:
        logger.warning("CAPTURE: resumed recording %s (attempt %d, after %s)",
                       sym, _resume["attempt"], _resume["reason"])
        _resume = None
        if _stopped and _stopped["symbol"] == sym:
            _stopped["resumed"] = True
        _watched = sym
        return
    logger.warning("CAPTURE: resume of %s failed (attempt %d/%d): %s", sym, _resume["attempt"],
                   _resume["max_attempts"], error)
    if _resume["attempt"] >= _resume["max_attempts"]:
        _give_up(f"{_resume['max_attempts']} attempts failed; last: {error}")
    else:
        step = min(_resume["attempt"], len(CAPTURE_RESUME_BACKOFF_SEC) - 1)
        _resume["next_at"] = now + CAPTURE_RESUME_BACKOFF_SEC[step]


def _give_up(reason: str) -> None:
    assert _resume is not None
    _resume["gave_up"] = True
    _resume["gave_up_reason"] = reason
    _resume["pending"] = False
    logger.error("CAPTURE: giving up on resuming %s: %s", _resume["symbol"], reason)


# ---------------------------------------------------------------------------
# Status


def status_fields(recorder_status: dict[str, Any], recording: bool) -> dict[str, Any]:
    """The three ``/api/ibkr/status`` fields (AGENTS.md section 3, recording persistence)."""
    session = None
    if recording:
        session = {
            "symbol": recorder_status.get("symbol"),
            "session_date": recorder_status.get("session_date"),
            "started_et": recorder_status.get("started_et"),
            "segment_started_et": recorder_status.get("segment_started_et"),
            "segment": recorder_status.get("segment"),
            "counts": dict(recorder_status.get("counts") or {}),
            "last_write_ts": recorder_status.get("last_write_ts"),
            "dir": recorder_status.get("dir"),
            "reacquired": _reacquired,
        }
    return {
        "capture_session": session,
        "capture_resume": dict(_resume) if _resume else None,
        "capture_stopped": dict(_stopped) if _stopped else None,
    }


# ---------------------------------------------------------------------------
# Loop


async def run() -> None:
    """Background loop on the HTTP loop (feed_hold's lines live there)."""
    from capture import feed_hold, mode, recorder
    from ibkr import client

    async def start(symbol: str) -> dict[str, Any]:
        return await asyncio.to_thread(mode.set_capture_mode, True, symbol=symbol, protect_active=True)

    while True:
        try:
            await asyncio.sleep(CAPTURE_KEEPALIVE_INTERVAL_SEC)
            payload = await asyncio.to_thread(mode.status_payload)
            await tick(
                now=time.time(),
                payload=payload,
                recorder_status=recorder.status(),
                ready=client.is_ready,
                acquire=feed_hold.acquire,
                release=feed_hold.release,
                start=start,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("CAPTURE: keepalive tick failed")
