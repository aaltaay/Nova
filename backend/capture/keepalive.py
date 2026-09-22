"""Resume, then say so (operator decision, 2026-09-21).

A Session Record is owned by this process and nothing on the page can stop it.
What can: a process restart, a recorder that stops itself (disk, timestamp,
writer backlog), and an IBKR line that drops with the Gateway. The market only
happens once, so the policy for all three is the same -- get back up into a new
segment on your own, and tell the operator what happened -- bounded so a dead
disk cannot loop forever, never across a day boundary, never onto a different
symbol, and cancelled the moment the operator stops that symbol.

Every symbol is followed on its own: up to CAPTURE_MAX_CONCURRENT record at
once, and one dying must not touch the others. State here is process memory;
the manifest on disk is the durable record. This module only decides when to
call ``start`` again and what ``/api/ibkr/status`` says about it.
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

# Symbols the last tick saw recording; one that is gone without an operator
# stop in between has died.
_watched: set[str] = set()
# symbol -> a resume in flight: why, attempts so far, when next.
_resume: dict[str, dict[str, Any]] = {}
# symbol -> the last stop the operator did not ask for -- what the UI shouts about.
_stopped: dict[str, dict[str, Any]] = {}
# symbol -> IBKR lines re-acquired after a Gateway drop, this session.
_reacquired: dict[str, int] = {}


def reset_for_tests() -> None:
    _watched.clear()
    _resume.clear()
    _stopped.clear()
    _reacquired.clear()


def _today_et(now: float) -> str:
    return datetime.fromtimestamp(now, ET).strftime("%Y-%m-%d")


def _sym(symbol: str | None) -> str | None:
    sym = (symbol or "").strip().upper()
    return sym or None


# ---------------------------------------------------------------------------
# Operator intent


def operator_stopped(symbol: str | None) -> None:
    """The operator asked for the stop: nothing to resume, nothing to shout.
    With no symbol, every recording is being stopped."""
    sym = _sym(symbol)
    for store in (_resume, _stopped):
        if sym is None:
            store.clear()
        else:
            store.pop(sym, None)
    if sym is None:
        _watched.clear()
    else:
        _watched.discard(sym)


def operator_started(symbol: str) -> None:
    """A recording the operator started supersedes that symbol's pending resume or old stop."""
    sym = _sym(symbol)
    if sym is None:
        return
    _resume.pop(sym, None)
    _stopped.pop(sym, None)


# ---------------------------------------------------------------------------
# Restart


def note_restart(summary: dict[str, Any] | None, *, now: float | None = None) -> bool:
    """A recording the previous process died during: resume it if it is today's and recent."""
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
    _stopped[symbol] = {
        "symbol": symbol,
        "at": float(last_write),
        "reason": CAPTURE_STOP_RESTART,
        "error": None,
        "dir": summary.get("dir"),
        "counts": dict(summary.get("counts") or {}),
        "resumed": False,
    }
    _resume[symbol] = _new_resume(symbol, CAPTURE_STOP_RESTART, None, summary.get("session_date"), now,
                                  first_delay=0.0)
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
    """Observe every recording once; resume or re-acquire where the policy says so.

    ``payload`` is ``capture.mode.status_payload()`` and ``recorder_status`` is
    ``capture.recorder.status()``, both taken by the caller off the loop.
    """
    recording = [str(s).upper() for s in (payload.get("capture_symbols") or []) if s]
    if not recording and payload.get("capture") and payload.get("capture_symbol"):
        recording = [str(payload["capture_symbol"]).upper()]
    sessions = payload.get("sessions") or {}

    for symbol in recording:
        if symbol in _resume:
            _resume.pop(symbol)  # whoever started it, the resume is done
            if symbol in _stopped:
                _stopped[symbol]["resumed"] = True
        _watched.add(symbol)
        producer = (sessions.get(symbol) or {}).get("producer") or payload.get("producer") or {}
        # Gateway drop: the tape line is gone but the client is back. Take the
        # lines again; the recorder never stopped, so this is a gap, not a segment.
        if producer.get("state") == "disconnected" and ready():
            await release(symbol)
            error = await acquire(symbol)
            if error:
                logger.warning("CAPTURE: re-acquire of IBKR lines for %s failed: %s", symbol, error)
            else:
                _reacquired[symbol] = _reacquired.get(symbol, 0) + 1
                logger.warning("CAPTURE: IBKR lines re-acquired for %s after a Gateway drop", symbol)

    for died in sorted(_watched - set(recording)):
        # Nothing records it and the operator did not stop it: it died.
        _watched.discard(died)
        rec = (recorder_status.get("sessions") or {}).get(died) or recorder_status
        error = rec.get("error") or payload.get("error")
        _stopped[died] = {
            "symbol": died,
            "at": now,
            "reason": CAPTURE_STOP_FAILURE,
            "error": error,
            "dir": rec.get("dir"),
            "counts": dict(rec.get("counts") or {}),
            "resumed": False,
        }
        _resume[died] = _new_resume(died, CAPTURE_STOP_FAILURE, error, rec.get("session_date"), now,
                                    first_delay=CAPTURE_RESUME_BACKOFF_SEC[0])
        logger.error("CAPTURE: recording of %s stopped on its own (%s) -- will resume", died, error)

    for symbol in list(_resume):
        await _attempt(symbol, now=now, ready=ready, acquire=acquire, start=start)


async def _attempt(symbol: str, *, now: float, ready, acquire, start) -> None:
    resume = _resume.get(symbol)
    if not resume or resume["gave_up"] or now < resume["next_at"]:
        return
    if resume["session_date"] != _today_et(now):
        _give_up(resume, "the session day ended")
        return
    if not ready():
        # IBKR is not usable; that is not the recorder's fault, so it costs no
        # attempt. Try again next tick.
        resume["next_at"] = now + CAPTURE_KEEPALIVE_INTERVAL_SEC
        return
    resume["attempt"] += 1
    error = await acquire(symbol)
    if not error:
        out = await start(symbol)
        started = [str(s).upper() for s in (out.get("capture_symbols") or [])]
        if not started and out.get("capture") and out.get("capture_symbol"):
            started = [str(out["capture_symbol"]).upper()]
        error = None if symbol in started else (out.get("error") or out.get("detail") or "Recorder did not start")
    if error is None:
        logger.warning("CAPTURE: resumed recording %s (attempt %d, after %s)",
                       symbol, resume["attempt"], resume["reason"])
        _resume.pop(symbol, None)
        if symbol in _stopped:
            _stopped[symbol]["resumed"] = True
        _watched.add(symbol)
        return
    logger.warning("CAPTURE: resume of %s failed (attempt %d/%d): %s", symbol, resume["attempt"],
                   resume["max_attempts"], error)
    if resume["attempt"] >= resume["max_attempts"]:
        _give_up(resume, f"{resume['max_attempts']} attempts failed; last: {error}")
    else:
        step = min(resume["attempt"], len(CAPTURE_RESUME_BACKOFF_SEC) - 1)
        resume["next_at"] = now + CAPTURE_RESUME_BACKOFF_SEC[step]


def _give_up(resume: dict[str, Any], reason: str) -> None:
    resume["gave_up"] = True
    resume["gave_up_reason"] = reason
    resume["pending"] = False
    logger.error("CAPTURE: giving up on resuming %s: %s", resume["symbol"], reason)


# ---------------------------------------------------------------------------
# Status


def status_fields(recorder_status: dict[str, Any], recording: list[str]) -> dict[str, Any]:
    """The three ``/api/ibkr/status`` lists (AGENTS.md section 3, recording persistence)."""
    sessions = recorder_status.get("sessions") or {}
    out_sessions = []
    for symbol in recording:
        rec = sessions.get(symbol) or (recorder_status if recorder_status.get("symbol") == symbol else {})
        out_sessions.append({
            "symbol": symbol,
            "session_date": rec.get("session_date"),
            "started_et": rec.get("started_et"),
            "segment_started_et": rec.get("segment_started_et"),
            "segment": rec.get("segment"),
            "counts": dict(rec.get("counts") or {}),
            "last_write_ts": rec.get("last_write_ts"),
            "dir": rec.get("dir"),
            "reacquired": _reacquired.get(symbol, 0),
        })
    return {
        "capture_sessions": out_sessions,
        "capture_resume": [dict(row) for row in _resume.values()],
        "capture_stopped": [dict(row) for row in _stopped.values()],
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
