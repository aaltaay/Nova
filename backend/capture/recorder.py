"""Capture writer: atomic manifest, serialized streams and explicit failures.

One session per symbol, up to CAPTURE_MAX_CONCURRENT at once -- IBKR allows
three depth lines and Record holds one per symbol (operator decision,
2026-09-21). The sessions share one non-reentrant lock on purpose: stop drains
buckets without callbacks; only public entrypoints acquire it. Storage and
timestamp policy are separate modules under ADR 001; this compatibility feeder
follows ADR 017.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO
from zoneinfo import ZoneInfo

from capture.constants_capture import (
    CAPTURE_FSYNC_INTERVAL_SEC,
    CAPTURE_L2_MAX_HZ,
    CAPTURE_MANIFEST_NAME,
    CAPTURE_MAX_CONCURRENT,
    CAPTURE_MAX_WRITE_FAILURES,
    CAPTURE_SCHEMA,
    CAPTURE_SCHEMA_VERSION,
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_RECORDING,
    CAPTURE_STATUS_STOPPED,
    CAPTURE_STOP_FAILURE,
    CAPTURE_STOP_OPERATOR,
    CAPTURE_STOP_ROTATION,
    CAPTURE_STREAM_NAMES,
)
from capture.storage import capture_root
from capture.schema import read_manifest
from capture.fidelity import Fidelity
from capture.timeframes import _normalize_timeframe

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

_lock = threading.Lock()
# symbol -> its session. A stopped session stays here, inactive, so status and
# last_error can still say how it ended -- until that symbol starts again.
_sessions: dict[str, "_Session"] = {}


class RecorderLimit(RuntimeError):
    """A fourth symbol: IBKR allows three depth lines, and Record holds one each."""


def _zero_counts() -> dict[str, int]:
    return {name: 0 for name in CAPTURE_STREAM_NAMES}


@dataclass
class _Session:
    symbol: str
    active: bool = False
    day: str | None = None
    dir: Path | None = None
    files: dict[str, TextIO] = field(default_factory=dict)
    fidelity: Fidelity = field(default_factory=Fidelity)
    last_fsync_mono: float = 0.0
    counts: dict[str, int] = field(default_factory=_zero_counts)
    # Counts already on disk when this segment started, so a segment's own
    # totals stay recoverable from the cumulative ones.
    segment_base: dict[str, int] = field(default_factory=_zero_counts)
    # This segment's start; the session's first start is carried across resumes.
    started_et: str | None = None
    session_started_et: str | None = None
    write_failures: int = 0
    error: str | None = None
    last_write_ts: float | None = None
    # Why the segment being closed ended; an unplanned stop sets it before the
    # locked stop path runs, an operator stop passes it in.
    stop_reason: str = CAPTURE_STOP_OPERATOR
    # Segments already in the manifest when this one started.
    prior_segments: int = 0


# ---------------------------------------------------------------------------
# Test seams


def reset_for_tests() -> None:
    stop_recorder()
    with _lock:
        _sessions.clear()


def _crash_for_tests(symbol: str | None = None) -> None:
    """Simulate SIGKILL: process state vanishes; nothing is flushed or finalized."""
    with _lock:
        for sym in (list(_sessions) if symbol is None else [symbol.strip().upper()]):
            _sessions.pop(sym, None)


def _hard_reset_for_tests() -> None:
    """Abandon a wedged lock so one deadlock does not hang every later test."""
    global _lock
    _lock = threading.Lock()
    _sessions.clear()


# ---------------------------------------------------------------------------
# Readers


def _primary() -> _Session | None:
    """The session ``status()`` / ``last_error()`` describe when no symbol is
    named: the first active one, else the most recently started."""
    sessions = list(_sessions.values())
    for s in sessions:
        if s.active:
            return s
    return sessions[-1] if sessions else None


def recording_symbols() -> list[str]:
    with _lock:
        return [s.symbol for s in _sessions.values() if s.active]


def is_recording(symbol: str | None = None) -> bool:
    """Read under the lock: a day rotation clears ``active`` while it swaps
    segments, and ``capture.mode._reconcile`` treats a False here as "the
    recorder stopped itself" -- an unlocked read mid-rotation dropped Record mode
    while the recorder kept writing, leaving a recording no Stop could reach.
    Safe: no caller holds ``_lock`` (the worker checks between operations)."""
    with _lock:
        if symbol is None:
            return any(s.active for s in _sessions.values())
        s = _sessions.get(symbol.strip().upper())
        return bool(s and s.active)


def last_error(symbol: str | None = None) -> str | None:
    """Why that recording stopped writing, or ``None`` while healthy."""
    with _lock:
        s = _sessions.get(symbol.strip().upper()) if symbol is not None else _primary()
        return s.error if s else None


def _session_dir(symbol: str, day: str | None = None) -> Path:
    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    return capture_root() / day / symbol.upper()


def _marker_rows() -> list[dict[str, Any]]:
    """What the crash marker names: every active session. Caller holds ``_lock``."""
    return [
        {"symbol": s.symbol, "dir": str(s.dir), "started_et": s.started_et}
        for s in _sessions.values()
        if s.active and s.dir is not None
    ]


# ---------------------------------------------------------------------------
# Lifecycle


def start_recorder(symbol: str | None, *, resume: bool = True, session_date: str | None = None) -> dict[str, Any]:
    """Begin (or resume) recording ``symbol`` for today, beside any other symbol recording.

    ``resume=True`` appends to whatever is already on disk for this symbol+day
    and carries the manifest forward; ``resume=False`` truncates the streams and
    starts a fresh manifest. Raises ``RecorderLimit`` for a fourth symbol.
    """
    from capture import manifest_io, session_state

    sym = (symbol or "PENDING").strip().upper()
    with _lock:
        previous = _sessions.get(sym)
        if previous is not None and (previous.active or previous.files):
            # Rotating to another Eastern day closes the previous segment; one that
            # never received a print is marked empty, which is not a failed recording.
            _stop_locked(previous, rotating=previous.active and session_date is not None)
        others = sum(1 for s in _sessions.values() if s.active and s.symbol != sym)
        if others >= CAPTURE_MAX_CONCURRENT:
            raise RecorderLimit(
                f"Already recording {CAPTURE_MAX_CONCURRENT} symbols -- IBKR allows "
                f"{CAPTURE_MAX_CONCURRENT} depth lines; stop one first"
            )
        from capture.bar_buckets import drain_open
        drain_open(sym)  # Discard buckets left by a failed previous batch/session.
        s = _Session(symbol=sym)
        _sessions[sym] = s
        s.dir = _session_dir(sym, session_date)
        s.dir.mkdir(parents=True, exist_ok=True)
        s.day = s.dir.parent.name
        man_path = s.dir / CAPTURE_MANIFEST_NAME
        prior = read_manifest(s.dir)[0] if resume else {}

        # Seed from what is already on disk so the manifest never understates
        # the jsonl files after a stop/start on the same symbol+day (D-067b).
        seeded = manifest_io.prior_counts(prior) if resume else {}
        s.counts = {name: int(seeded.get(name, 0)) for name in CAPTURE_STREAM_NAMES}
        s.segment_base = dict(s.counts)
        if resume:
            s.fidelity.seed(s.dir, prior)
        s.last_fsync_mono = time.monotonic()
        segments = prior.get("segments") if resume else None
        s.prior_segments = len(segments) if isinstance(segments, list) else 0

        mode = "a" if resume else "w"
        for name in CAPTURE_STREAM_NAMES:
            s.files[name] = (s.dir / f"{name}.jsonl").open(mode, encoding="utf-8")

        s.started_et = datetime.now(ET).isoformat()
        s.session_started_et = prior.get("started_et") or s.started_et
        manifest = dict(prior)
        manifest.update(
            {
                "symbol": sym,
                "session_date": s.day,
                "started_et": s.session_started_et,
                "segment_started_et": s.started_et,
                "stopped_et": None,
                "source": "ibkr",
                "schema": CAPTURE_SCHEMA,
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "l2_max_hz": CAPTURE_L2_MAX_HZ,
                "note": "Per-tab Record — partial days OK; append resume; compact whatever landed",
                "partial_ok": True,
                "resume": bool(resume),
                "status": CAPTURE_STATUS_RECORDING,
                "counts": dict(s.counts),
            }
        )
        manifest.pop("error", None)
        manifest_io.write_json_atomic(man_path, manifest)
        s.active = True
        session_state.mark_active(capture_root(), sessions=_marker_rows())
        logger.info("CAPTURE: recorder started %s (resume=%s)", s.dir, resume)
        return {"ok": True, "dir": str(s.dir), "manifest": manifest}


def stop_recorder(*, symbol: str | None = None, reason: str = CAPTURE_STOP_OPERATOR) -> None:
    """Stop one symbol, or every recording when none is named."""
    with _lock:
        targets = list(_sessions.values()) if symbol is None else [_sessions.get(symbol.strip().upper())]
        for s in targets:
            if s is None:
                continue
            s.stop_reason = reason
            _stop_locked(s)


def _stop_locked(s: _Session, *, rotating: bool = False) -> None:
    """Flush open bars, fsync, close, and finalize the manifest.

    Runs with ``_lock`` held and must never re-acquire it.  ``active`` is
    cleared *first* so a concurrent ``record_*`` that is queued on the lock
    no-ops the moment it gets in, and so the drained bars below take the
    already-locked write path rather than the public one.
    """
    if not s.active and not s.files:
        return
    s.active = False
    if s.counts["prints"] == s.segment_base["prints"]:
        s.error = s.error or "No IBKR prints received in this recording segment"

    pending = s.fidelity.drain_l2()
    if pending is not None:
        _write(s, "l2", pending)
    bars: list[tuple[str, dict[str, Any]]] = []
    try:
        from capture.bar_buckets import drain_open

        bars = drain_open(s.symbol)
    except Exception:
        logger.exception("CAPTURE: bar drain failed")
    for timeframe, bar in bars:
        _write_bar_locked(s, timeframe, bar)

    _finalize_locked(
        s,
        CAPTURE_STATUS_FAILED if s.error else CAPTURE_STATUS_STOPPED,
        rotating=rotating,
        reason=CAPTURE_STOP_ROTATION if rotating else s.stop_reason,
    )
    logger.info("CAPTURE: recorder stopped %s counts=%s", s.symbol, s.counts)


def _finalize_locked(
    s: _Session, status: str, *, rotating: bool = False, reason: str = CAPTURE_STOP_OPERATOR
) -> None:
    """fsync + close the streams and merge terminal state into the manifest."""
    s.active = False
    if not s.files and s.started_et is None:
        return
    if rotating:
        # The recording carries on in the new day's segment.
        logger.info("CAPTURE: %s day segment closed (%s) -- recording continues", s.symbol, status)
    elif status == CAPTURE_STATUS_FAILED:
        logger.error(
            "CAPTURE: giving up on the recording of %s after %d consecutive "
            "write failures — last error: %s",
            s.symbol,
            s.write_failures,
            s.error,
        )

    for fh in list(s.files.values()):
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except OSError:
            logger.exception("CAPTURE: fsync on close failed")
        try:
            fh.close()
        except OSError:
            logger.exception("CAPTURE: close failed")
    s.files.clear()

    if s.dir is not None and s.started_et is not None:
        from capture import manifest_io, session_state

        man_path = s.dir / CAPTURE_MANIFEST_NAME
        try:
            prior = manifest_io.read_json(man_path)
            # Drop the in-flight segment entry start_recorder never wrote, then
            # append this run's real one.
            segment = {
                name: int(s.counts.get(name, 0)) - int(s.segment_base.get(name, 0))
                for name in CAPTURE_STREAM_NAMES
            }
            man = manifest_io.merge(
                prior,
                base={
                    "symbol": s.symbol,
                    "session_date": s.day,
                    "source": "ibkr",
                    "schema": CAPTURE_SCHEMA,
                    "schema_version": CAPTURE_SCHEMA_VERSION,
                    "partial_ok": True,
                    "fidelity": s.fidelity.payload(),
                },
                started_et=s.started_et,
                stopped_et=datetime.now(ET).isoformat(),
                status=status,
                counts=dict(s.counts),
                segment_counts=segment,
                error=s.error,
                reason=reason,
            )
            manifest_io.write_json_atomic(man_path, man)
        except OSError:
            logger.exception("CAPTURE: manifest finalize failed")
        try:
            # The marker names what is still recording; nothing left clears it.
            session_state.mark_active(capture_root(), sessions=_marker_rows())
        except OSError:
            logger.exception("CAPTURE: could not update active-session marker")
    s.started_et = None


# ---------------------------------------------------------------------------
# Writes


def _write(s: _Session, kind: str, row: dict[str, Any]) -> None:
    """Append one row. Caller holds ``_lock``. Never raises to the tape path."""
    fh = s.files.get(kind)
    if fh is None:
        return
    try:
        fh.write(json.dumps({**row, "schema_version": CAPTURE_SCHEMA_VERSION}, separators=(",", ":")) + "\n")
        fh.flush()
        now = time.monotonic()
        if now - s.last_fsync_mono >= CAPTURE_FSYNC_INTERVAL_SEC:
            os.fsync(fh.fileno())
            s.last_fsync_mono = now
    except (OSError, ValueError) as exc:
        s.write_failures += 1
        s.error = f"{type(exc).__name__}: {exc}"
        logger.exception(
            "CAPTURE: write to %s failed (%d/%d consecutive) — recording of %s "
            "is losing data",
            kind,
            s.write_failures,
            CAPTURE_MAX_WRITE_FAILURES,
            s.symbol,
        )
        if s.write_failures >= CAPTURE_MAX_WRITE_FAILURES:
            # Give up rather than keep reporting a healthy recording that is
            # writing nothing (D-068). The traceback is already logged above.
            _finalize_locked(s, CAPTURE_STATUS_FAILED, reason=CAPTURE_STOP_FAILURE)
        return
    s.write_failures = 0
    s.last_write_ts = time.time()
    s.counts[kind] = s.counts.get(kind, 0) + 1


def _write_bar_locked(s: _Session, timeframe: str, payload: dict[str, Any]) -> None:
    """Write a drained bucket while ``_lock`` is held and ``active`` is False."""
    norm = _normalize_timeframe(timeframe)
    if norm is None:
        logger.warning("CAPTURE: unknown bar timeframe %r — skipped", timeframe)
        return
    kind, label = norm
    row = dict(payload)
    row.setdefault("timeframe", label)
    _write(s, kind, row)


def _session_for(payload: dict[str, Any]) -> _Session | None:
    sym = str(payload.get("symbol") or "").strip().upper()
    return _sessions.get(sym) if sym else None


def _record(kind: str, payload: dict[str, Any]) -> bool:
    s = _session_for(payload)
    if s is None or not s.active:
        return False
    with _lock:
        if not s.active:
            return False
        error = s.fidelity.admit(kind, payload)
        if error:
            s.error = error
            s.stop_reason = CAPTURE_STOP_FAILURE
            logger.error("CAPTURE: %s (%s)", error, kind)
            _stop_locked(s)
            return False
        row = s.fidelity.offer_l2(payload) if kind == "l2" else payload
        if row is not None:
            _write(s, kind, row)
        return s.active


def record_print(payload: dict[str, Any]) -> bool:
    return _record("prints", payload)


def record_quote(payload: dict[str, Any]) -> None:
    _record("quotes", payload)


def record_l2(payload: dict[str, Any]) -> None:
    """Coalesce in event time, preserving the final pending book on stop."""
    _record("l2", payload)


def ensure_event_day(symbol: str, ts: float) -> None:
    """Rotate accepted worker batches on Eastern date; refuse backward scrubs."""
    from capture.schema import valid_timestamp

    s = _sessions.get(symbol.strip().upper())
    if s is None or not s.active or not valid_timestamp(ts):
        return
    previous = s.fidelity.last_ts.get("prints")
    if previous is not None and ts < previous:
        return  # record_print diagnoses and fails before bar aggregation.
    day = datetime.fromtimestamp(ts, ET).strftime("%Y-%m-%d")
    if day != s.day:
        start_recorder(s.symbol, session_date=day)


def record_bar(timeframe: str, payload: dict[str, Any]) -> None:
    """Persist one bar. timeframes: 10s/10Sec, 1m/1Min, 5m/5Min, 1d/1Day."""
    s = _session_for(payload)
    if s is None or not s.active:
        return
    norm = _normalize_timeframe(timeframe)
    if norm is None:
        logger.warning("CAPTURE: unknown bar timeframe %r — skipped", timeframe)
        return
    kind, label = norm
    row = dict(payload)
    row.setdefault("timeframe", label)
    with _lock:
        if not s.active:
            return
        error = s.fidelity.admit(kind, row)
        if error:
            logger.warning("CAPTURE: skipped bar: %s", error)
            return
        _write(s, kind, row)


def fail_recorder(error: str, symbol: str | None = None) -> None:
    """Finalize an ingress/worker failure using the normal locked stop path."""
    with _lock:
        targets = list(_sessions.values()) if symbol is None else [_sessions.get(symbol.strip().upper())]
        for s in targets:
            if s is None:
                continue
            s.error = error
            s.stop_reason = CAPTURE_STOP_FAILURE
            _stop_locked(s)


# ---------------------------------------------------------------------------
# Status


def _session_status(s: _Session | None) -> dict[str, Any]:
    if s is None:
        return {
            "recording": False,
            "symbol": None,
            "session_date": None,
            "dir": None,
            "started_et": None,
            "segment_started_et": None,
            "segment": 0,
            "counts": _zero_counts(),
            "fidelity": Fidelity().payload(),
            "segment_prints": 0,
            "error": None,
            "write_failures": 0,
            "last_write_ts": None,
        }
    return {
        "recording": s.active,
        "symbol": s.symbol,
        "session_date": s.day,
        "dir": str(s.dir) if s.dir else None,
        "started_et": s.session_started_et,
        "segment_started_et": s.started_et,
        # This segment's ordinal (1-based) counting the ones already on disk.
        "segment": s.prior_segments + 1 if s.active else s.prior_segments,
        "counts": dict(s.counts),
        "fidelity": s.fidelity.payload(),
        "segment_prints": s.counts["prints"] - s.segment_base["prints"],
        "error": s.error,
        "write_failures": s.write_failures,
        "last_write_ts": s.last_write_ts,
    }


def status(symbol: str | None = None) -> dict[str, Any]:
    """One symbol's session, or -- with none named -- the primary one plus
    ``sessions`` for every symbol known this process. Lock-free, as before:
    a status poll must never wait behind a stop's disk I/O."""
    from capture import session_state

    sessions = dict(_sessions)
    if symbol is not None:
        out = _session_status(sessions.get(symbol.strip().upper()))
    else:
        active = [s for s in sessions.values() if s.active]
        primary = active[0] if active else (list(sessions.values())[-1] if sessions else None)
        out = _session_status(primary)
    out["recording_symbols"] = [s.symbol for s in sessions.values() if s.active]
    out["sessions"] = {sym: _session_status(s) for sym, s in sessions.items()}
    out["interrupted_session"] = session_state.last_interrupted()
    out["interrupted_sessions"] = session_state.interrupted_sessions()
    return out
