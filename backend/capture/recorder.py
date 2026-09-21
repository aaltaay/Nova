"""Capture writer: atomic manifest, serialized streams and explicit failures.

The non-reentrant lock is intentional. Stop drains buckets without callbacks;
only public entrypoints acquire it. Storage and timestamp policy are separate
modules under ADR 001; this compatibility feeder follows ADR 017.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO
from zoneinfo import ZoneInfo

from capture.constants_capture import (
    CAPTURE_FSYNC_INTERVAL_SEC,
    CAPTURE_L2_MAX_HZ,
    CAPTURE_MANIFEST_NAME,
    CAPTURE_MAX_WRITE_FAILURES,
    CAPTURE_SCHEMA,
    CAPTURE_SCHEMA_VERSION,
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_RECORDING,
    CAPTURE_STATUS_STOPPED,
    CAPTURE_STREAM_NAMES,
)
from capture.storage import capture_root
from capture.schema import read_manifest
from capture.fidelity import Fidelity
from capture.timeframes import _normalize_timeframe

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

_lock = threading.Lock()
_active = False
_symbol: str | None = None
_day: str | None = None
_dir: Path | None = None
_files: dict[str, TextIO] = {}
_fidelity = Fidelity()
_last_fsync_mono = 0.0
_counts = {name: 0 for name in CAPTURE_STREAM_NAMES}
# Counts already on disk when this segment started, so a segment's own totals
# stay recoverable from the cumulative ones.
_segment_base: dict[str, int] = {name: 0 for name in CAPTURE_STREAM_NAMES}
_started_et: str | None = None
_write_failures = 0
_error: str | None = None
_last_write_ts: float | None = None


def reset_for_tests() -> None:
    global _write_failures, _error, _last_write_ts
    stop_recorder()
    _write_failures = 0
    _error = None
    _last_write_ts = None


def is_recording() -> bool:
    return _active


def last_error() -> str | None:
    """Why the recording stopped writing, or ``None`` while healthy."""
    return _error


def _session_dir(symbol: str, day: str | None = None) -> Path:
    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    return capture_root() / day / symbol.upper()


def start_recorder(symbol: str | None, *, resume: bool = True, session_date: str | None = None) -> dict[str, Any]:
    """Begin (or resume) recording ``symbol`` for today.

    ``resume=True`` appends to whatever is already on disk for this symbol+day
    and carries the manifest forward; ``resume=False`` truncates the streams and
    starts a fresh manifest.
    """
    global _active, _symbol, _day, _dir, _fidelity, _last_fsync_mono
    global _counts, _segment_base, _started_et, _write_failures, _error, _last_write_ts
    from capture import manifest_io, session_state

    with _lock:
        _stop_locked()
        from capture.bar_buckets import drain_open
        drain_open()  # Discard buckets left by a failed previous batch/session.
        sym = (symbol or "PENDING").strip().upper()
        _symbol = sym
        _dir = _session_dir(sym, session_date)
        _dir.mkdir(parents=True, exist_ok=True)
        _day = _dir.parent.name
        man_path = _dir / CAPTURE_MANIFEST_NAME
        prior = read_manifest(_dir)[0] if resume else {}

        # Seed from what is already on disk so the manifest never understates
        # the jsonl files after a stop/start on the same symbol+day (D-067b).
        seeded = manifest_io.prior_counts(prior) if resume else {}
        _counts = {name: int(seeded.get(name, 0)) for name in CAPTURE_STREAM_NAMES}
        _segment_base = dict(_counts)
        _fidelity = Fidelity()
        if resume:
            _fidelity.seed(_dir, prior)
        _last_fsync_mono = time.monotonic()
        _write_failures = 0
        _error = None
        _last_write_ts = None

        mode = "a" if resume else "w"
        for name in CAPTURE_STREAM_NAMES:
            _files[name] = (_dir / f"{name}.jsonl").open(mode, encoding="utf-8")

        _started_et = datetime.now(ET).isoformat()
        manifest = dict(prior)
        manifest.update(
            {
                "symbol": sym,
                "session_date": _day,
                "started_et": prior.get("started_et") or _started_et,
                "segment_started_et": _started_et,
                "stopped_et": None,
                "source": "ibkr",
                "schema": CAPTURE_SCHEMA,
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "l2_max_hz": CAPTURE_L2_MAX_HZ,
                "note": "Per-tab Record — partial days OK; append resume; compact whatever landed",
                "partial_ok": True,
                "resume": bool(resume),
                "status": CAPTURE_STATUS_RECORDING,
                "counts": dict(_counts),
            }
        )
        manifest.pop("error", None)
        manifest_io.write_json_atomic(man_path, manifest)
        session_state.mark_active(
            capture_root(), symbol=sym, session_dir=_dir, started_et=_started_et
        )
        _active = True
        logger.info("CAPTURE: recorder started %s (resume=%s)", _dir, resume)
        return {"ok": True, "dir": str(_dir), "manifest": manifest}


def stop_recorder() -> None:
    with _lock:
        _stop_locked()


def _stop_locked() -> None:
    """Flush open bars, fsync, close, and finalize the manifest.

    Runs with ``_lock`` held and must never re-acquire it.  ``_active`` is
    cleared *first* so a concurrent ``record_*`` that is queued on the lock
    no-ops the moment it gets in, and so the drained bars below take the
    already-locked write path rather than the public one.
    """
    global _active, _error
    if not _active and not _files:
        return
    _active = False
    if _counts["prints"] == _segment_base["prints"]:
        _error = _error or "No IBKR prints received in this recording segment"

    pending = _fidelity.drain_l2()
    if pending is not None:
        _write("l2", pending)
    bars: list[tuple[str, dict[str, Any]]] = []
    try:
        from capture.bar_buckets import drain_open

        bars = drain_open(_symbol)
    except Exception:
        logger.exception("CAPTURE: bar drain failed")
    for timeframe, bar in bars:
        _write_bar_locked(timeframe, bar)

    _finalize_locked(CAPTURE_STATUS_FAILED if _error else CAPTURE_STATUS_STOPPED)
    logger.info("CAPTURE: recorder stopped counts=%s", _counts)


def _finalize_locked(status: str) -> None:
    """fsync + close the streams and merge terminal state into the manifest."""
    global _active, _started_et
    _active = False
    if not _files and _started_et is None:
        return
    if status == CAPTURE_STATUS_FAILED:
        logger.error(
            "CAPTURE: giving up on the recording of %s after %d consecutive "
            "write failures — last error: %s",
            _symbol,
            _write_failures,
            _error,
        )

    for fh in list(_files.values()):
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except OSError:
            logger.exception("CAPTURE: fsync on close failed")
        try:
            fh.close()
        except OSError:
            logger.exception("CAPTURE: close failed")
    _files.clear()

    if _dir is not None and _started_et is not None:
        from capture import manifest_io, session_state

        man_path = _dir / CAPTURE_MANIFEST_NAME
        try:
            prior = manifest_io.read_json(man_path)
            # Drop the in-flight segment entry start_recorder never wrote, then
            # append this run's real one.
            segment = {
                name: int(_counts.get(name, 0)) - int(_segment_base.get(name, 0))
                for name in CAPTURE_STREAM_NAMES
            }
            man = manifest_io.merge(
                prior,
                base={
                    "symbol": _symbol,
                    "session_date": _day,
                    "source": "ibkr",
                    "schema": CAPTURE_SCHEMA,
                    "schema_version": CAPTURE_SCHEMA_VERSION,
                    "partial_ok": True,
                    "fidelity": _fidelity.payload(),
                },
                started_et=_started_et,
                stopped_et=datetime.now(ET).isoformat(),
                status=status,
                counts=dict(_counts),
                segment_counts=segment,
                error=_error,
            )
            manifest_io.write_json_atomic(man_path, man)
        except OSError:
            logger.exception("CAPTURE: manifest finalize failed")
        try:
            session_state.clear_active(capture_root())
        except OSError:
            logger.exception("CAPTURE: could not clear active-session marker")
    _started_et = None


def _write(kind: str, row: dict[str, Any]) -> None:
    """Append one row. Caller holds ``_lock``. Never raises to the tape path."""
    global _write_failures, _error, _last_write_ts, _last_fsync_mono
    fh = _files.get(kind)
    if fh is None:
        return
    try:
        fh.write(json.dumps({**row, "schema_version": CAPTURE_SCHEMA_VERSION}, separators=(",", ":")) + "\n")
        fh.flush()
        now = time.monotonic()
        if now - _last_fsync_mono >= CAPTURE_FSYNC_INTERVAL_SEC:
            os.fsync(fh.fileno())
            _last_fsync_mono = now
    except (OSError, ValueError) as exc:
        _write_failures += 1
        _error = f"{type(exc).__name__}: {exc}"
        logger.exception(
            "CAPTURE: write to %s failed (%d/%d consecutive) — recording of %s "
            "is losing data",
            kind,
            _write_failures,
            CAPTURE_MAX_WRITE_FAILURES,
            _symbol,
        )
        if _write_failures >= CAPTURE_MAX_WRITE_FAILURES:
            # Give up rather than keep reporting a healthy recording that is
            # writing nothing (D-068). The traceback is already logged above.
            _finalize_locked(CAPTURE_STATUS_FAILED)
        return
    _write_failures = 0
    _last_write_ts = time.time()
    _counts[kind] = _counts.get(kind, 0) + 1


def _write_bar_locked(timeframe: str, payload: dict[str, Any]) -> None:
    """Write a drained bucket while ``_lock`` is held and ``_active`` is False."""
    norm = _normalize_timeframe(timeframe)
    if norm is None:
        logger.warning("CAPTURE: unknown bar timeframe %r — skipped", timeframe)
        return
    kind, label = norm
    row = dict(payload)
    row.setdefault("timeframe", label)
    _write(kind, row)


def _record(kind: str, payload: dict[str, Any]) -> bool:
    global _error
    if not _active:
        return False
    with _lock:
        if not _active:
            return False
        error = _fidelity.admit(kind, payload)
        if error:
            _error = error
            logger.error("CAPTURE: %s (%s)", error, kind)
            _stop_locked()
            return False
        row = _fidelity.offer_l2(payload) if kind == "l2" else payload
        if row is not None:
            _write(kind, row)
        return _active


def record_print(payload: dict[str, Any]) -> bool:
    return _record("prints", payload)


def record_quote(payload: dict[str, Any]) -> None:
    _record("quotes", payload)


def record_l2(payload: dict[str, Any]) -> None:
    """Coalesce in event time, preserving the final pending book on stop."""
    _record("l2", payload)


def ensure_event_day(ts: float) -> None:
    """Rotate accepted worker batches on Eastern date; refuse backward scrubs."""
    from capture.schema import valid_timestamp
    if not _active or not valid_timestamp(ts):
        return
    previous = _fidelity.last_ts.get("prints")
    if previous is not None and ts < previous:
        return  # record_print diagnoses and fails before bar aggregation.
    day = datetime.fromtimestamp(ts, ET).strftime("%Y-%m-%d")
    if day != _day:
        start_recorder(_symbol, session_date=day)


def record_bar(timeframe: str, payload: dict[str, Any]) -> None:
    """Persist one bar. timeframes: 10s/10Sec, 1m/1Min, 5m/5Min, 1d/1Day."""
    if not _active:
        return
    norm = _normalize_timeframe(timeframe)
    if norm is None:
        logger.warning("CAPTURE: unknown bar timeframe %r — skipped", timeframe)
        return
    kind, label = norm
    row = dict(payload)
    row.setdefault("timeframe", label)
    with _lock:
        if not _active:
            return
        error = _fidelity.admit(kind, row)
        if error:
            logger.warning("CAPTURE: skipped bar: %s", error)
            return
        _write(kind, row)


def fail_recorder(error: str) -> None:
    """Finalize an ingress/worker failure using the normal locked stop path."""
    global _error
    with _lock:
        _error = error
        _stop_locked()


def status() -> dict[str, Any]:
    from capture import session_state

    return {
        "recording": _active,
        "symbol": _symbol,
        "session_date": _day,
        "dir": str(_dir) if _dir else None,
        "counts": dict(_counts),
        "fidelity": _fidelity.payload(),
        "segment_prints": _counts["prints"] - _segment_base["prints"],
        "error": _error,
        "write_failures": _write_failures,
        "last_write_ts": _last_write_ts,
        "interrupted_session": session_state.last_interrupted(),
    }
