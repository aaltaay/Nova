"""Resume, then say so (operator decision, 2026-09-21).

A Session Record is owned by this process and nothing on the page can stop it.
What can: a process restart, a recorder that stops itself (disk, timestamp,
writer backlog), and an IBKR line that drops with the Gateway. The market only
happens once, so the policy for all three is the same -- get back up into a new
segment on your own, and tell the operator what happened -- bounded so a dead
disk cannot loop forever, never across a day boundary, never onto a different
symbol, and cancelled the moment the operator stops that symbol. A tape line
that dies while the recording runs (#525) is the same policy without a new
segment: ``capture.tape_watch`` decides, this module asks IBKR again and says so.

Every symbol is followed on its own: up to CAPTURE_MAX_CONCURRENT record at
once, and one dying must not touch the others. State here is process memory;
the manifest on disk is the durable record. This module only decides when to
call ``start`` again and what ``/api/ibkr/status`` says about it.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from capture import tape_watch
from capture.constants_capture import (
    CAPTURE_KEEPALIVE_INTERVAL_SEC,
    CAPTURE_RESUME_BACKOFF_SEC,
    CAPTURE_RESUME_MAX_ATTEMPTS,
    CAPTURE_RESUME_RESTART_WINDOW_SEC,
    CAPTURE_STOP_FAILURE,
    CAPTURE_STOP_RESTART,
    CAPTURE_TAPE_LOST,
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
# symbol -> IBKR lines re-acquired after a Gateway drop or a lost tape, this session.
_reacquired: dict[str, int] = {}


@dataclass
class TapeOps:
    """The IBKR side of bringing a recording's tape back (#525), injected so tests fake it."""

    end: Callable[[str, str], Any]                 # drop the line; viewers keep their queues
    renew: Callable[[str], Awaitable[str | None]]  # ask for the tape again; an error or None
    note: Callable[..., Awaitable[None]]           # the manifest's fidelity: loss= / resubscribed=


def reset_for_tests() -> None:
    _watched.clear()
    _resume.clear()
    _stopped.clear()
    _reacquired.clear()
    tape_watch.reset_for_tests()


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
    tape_watch.forget(sym)


def operator_started(symbol: str) -> None:
    """A recording the operator started supersedes that symbol's pending resume or old stop."""
    sym = _sym(symbol)
    if sym is None:
        return
    _resume.pop(sym, None)
    _stopped.pop(sym, None)
    tape_watch.forget(sym)


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
    tape: TapeOps | None = None,
) -> None:
    """Observe every recording once; resume or re-acquire where the policy says so.

    ``payload`` is ``capture.mode.status_payload()`` and ``recorder_status`` is
    ``capture.recorder.status()``, both taken by the caller off the loop.
    ``tape`` watches each recording's tape line (#525); without it, it is not watched.
    """
    recording = [str(s).upper() for s in (payload.get("capture_symbols") or []) if s]
    if not recording and payload.get("capture") and payload.get("capture_symbol"):
        recording = [str(payload["capture_symbol"]).upper()]
    sessions = payload.get("sessions") or {}
    tape_watch.keep_only(recording)

    for symbol in recording:
        if symbol in _resume:
            _resume.pop(symbol)  # whoever started it, the resume is done
            if symbol in _stopped:
                _stopped[symbol]["resumed"] = True
        _watched.add(symbol)
        entry = sessions.get(symbol) or {"producer": payload.get("producer"), "book": payload.get("book")}
        producer = entry.get("producer") or payload.get("producer") or {}
        if tape is not None:
            rec = (recorder_status.get("sessions") or {}).get(symbol) or recorder_status
            await _watch_tape(symbol, now=now, entry=entry, rec=rec, ready=ready, tape=tape)
        if tape_watch.in_outage(symbol):
            continue  # the tape alone is being brought back; the depth line is fine
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
# The tape line (#525)


async def _watch_tape(symbol: str, *, now: float, entry: dict[str, Any], rec: dict[str, Any],
                      ready: Callable[[], bool], tape: TapeOps) -> None:
    """Act on ``tape_watch``'s verdict: drop, ask again, and say so."""
    verdict = tape_watch.observe(symbol, now=now, entry=entry)
    if verdict is None:
        return
    row = _stopped.get(symbol)
    if verdict.kind in (tape_watch.LOST, tape_watch.END):
        if verdict.end:
            tape.end(symbol, verdict.detail)
        logger.warning("CAPTURE: %s is recording without its tape (%s) -- %s", symbol, verdict.cause, verdict.detail)
        if (verdict.kind == tape_watch.END or verdict.repeat) and row and row["reason"] == CAPTURE_TAPE_LOST:
            # The same streak (a quiet name, or IBKR refusing again): one shout, brought up to date.
            row["error"], row["resumed"] = verdict.detail, False
            if verdict.kind == tape_watch.LOST:
                await tape.note(symbol, loss={"at": now, "cause": verdict.cause, "detail": verdict.detail})
            return
        if row is None or row["resumed"] or row["reason"] == CAPTURE_TAPE_LOST:
            # A stop the recorder never made: prints stopped, the recording did not.
            _stopped[symbol] = {"symbol": symbol, "at": now, "reason": CAPTURE_TAPE_LOST, "error": verdict.detail,
                                "dir": rec.get("dir"), "counts": dict(rec.get("counts") or {}), "resumed": False}
        await tape.note(symbol, loss={"at": now, "cause": verdict.cause, "detail": verdict.detail})
        return
    if verdict.kind == tape_watch.RESUMED:
        if row and row["reason"] == CAPTURE_TAPE_LOST:
            row["resumed"] = True
        logger.warning("CAPTURE: prints are back on %s's tape line", symbol)
        return
    if not ready():
        return  # IBKR is not usable: not the tape's fault, and it costs no attempt
    error = await tape.renew(symbol)
    retry_at = tape_watch.renewed(symbol, now=now, error=error)
    if error:
        logger.warning("CAPTURE: asking IBKR again for %s's tape failed: %s (next try in %.0fs)",
                       symbol, error, (retry_at or now) - now)
        if row and row["reason"] == CAPTURE_TAPE_LOST:
            row["error"] = f"{(tape_watch.status(symbol) or {}).get('detail')}; asking again failed: {error}"
        return
    _reacquired[symbol] = _reacquired.get(symbol, 0) + 1
    await tape.note(symbol, resubscribed=True)
    logger.warning("CAPTURE: asked IBKR again for %s's tape line", symbol)


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
    from ibkr import client, tape_stream

    async def start(symbol: str) -> dict[str, Any]:
        return await asyncio.to_thread(mode.set_capture_mode, True, symbol=symbol, protect_active=True)

    async def note(symbol: str, **kwargs: Any) -> None:
        await asyncio.to_thread(recorder.note_tape, symbol, **kwargs)  # the recorder lock can wait on disk

    tape = TapeOps(end=lambda symbol, why: tape_stream.end_line(symbol, why, notify=False),
                   renew=feed_hold.renew_tape, note=note)
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
                tape=tape,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("CAPTURE: keepalive tick failed")
