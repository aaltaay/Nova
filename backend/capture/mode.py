"""Per-symbol session record (right-click tab Record) — not a desk capsule mode."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_recording: bool = False
_symbol: str | None = None


def reset_for_tests() -> None:
    global _recording, _symbol
    _recording = False
    _symbol = None


def is_capture_mode() -> bool:
    """True while a tab Record session is active (legacy name kept for guards)."""
    return _recording


def capture_symbol() -> str | None:
    return _symbol if _recording else None


def set_capture_mode(
    enabled: bool, *, symbol: str | None = None, protect_active: bool = False,
) -> dict[str, Any]:
    """Start/stop recording; HTTP callers protect the existing owner.

    Internal lifecycle callers may deliberately rotate sessions. Both paths run
    ownership checks on the writer after previously accepted batches drain.
    """
    from capture.worker import transition

    if _recording and _symbol:
        # Before transition() closes ingress and fences the old session: the
        # bridge holds the prints buffered since its last batch. A print is an
        # event, so any lifecycle change -- stop OR rotation to another symbol
        # -- must write them; orphaned, they would be dropped in silence.
        from capture.bridge_ibkr import flush_prints

        flush_prints(_symbol)
    if not enabled and _recording and _symbol:
        # The book is a snapshot, not an event: only a stop needs the newest
        # coalesced one, which a burst that went quiet leaves unflushed.
        from capture.bridge_ibkr import flush_book

        flush_book(_symbol)
    result = transition(lambda: _set_capture_mode(enabled, symbol=symbol, protect_active=protect_active))
    out = status_payload() | (result or {})
    # Admission succeeded but the first write is pending. Report that on polls,
    # not as a failed command (the UI retains command errors until next action).
    if (enabled and result is None
            and out.get("error") == "IBKR AllLast waiting; no recent prints for " + str(_symbol)):
        out.pop("error", None)
    return out


def _set_capture_mode(
    enabled: bool, *, symbol: str | None = None, protect_active: bool = False,
) -> dict[str, Any] | None:
    global _recording, _symbol
    _reconcile()
    requested = (symbol or "").strip().upper()
    if protect_active and _recording and requested and requested != _symbol:
        return {"error": f"Already recording {_symbol}; stop it first", "conflict": True}
    if protect_active and enabled and _recording:
        return None  # Idempotent: do not reopen files or reset the active segment.
    if enabled:
        sym = (symbol or _symbol or "").strip().upper()
        if not sym:
            return {
                "capture": False,
                "error": "Pick a symbol tab before Record",
                "mode": None,
                "capture_symbol": None,
            }
        from capture.bridge_ibkr import admission_error
        error = admission_error(sym)
        if error:
            return {"error": error}
        try:
            from capture.recorder import start_recorder

            start_recorder(sym, resume=True)
        except Exception:
            logger.exception("RECORD: recorder start failed")
            _recording = False
            _symbol = None
            return {"error": "Recorder start failed"}
        _symbol = sym
        _recording = True
    else:
        try:
            from capture.recorder import stop_recorder

            stop_recorder()
        except Exception:
            logger.exception("RECORD: recorder stop failed")
            _reconcile()
            return {"error": "Recorder stop failed"}
        _recording = False
        _symbol = None
    logger.info("RECORD: %s symbol=%s", "on" if _recording else "off", _symbol)
    return None


def _reconcile() -> str | None:
    """Follow the recorder, not our own flag (D-068).

    The recorder stops itself when writes keep failing (disk full, drive
    unplugged, revoked handle).  Without this, ``_recording`` stayed True and
    ``/api/capture`` kept answering ``capture: true`` while nothing was being
    written — the operator only found out at replay time.  Returns the
    recorder's error so the caller can surface it.
    """
    global _recording
    try:
        from capture.recorder import is_recording, last_error
    except Exception:
        logger.exception("RECORD: recorder status unavailable")
        return None
    if not _recording or is_recording():
        return last_error()
    err = last_error()
    _recording = False
    logger.warning("RECORD: recorder stopped itself (%s) — clearing record mode", err or "unknown")
    return err


def status_payload() -> dict[str, Any]:
    err = _reconcile()
    on = _recording
    out: dict[str, Any] = {
        "capture": on,
        "mode": "record" if on else None,
        "capture_symbol": _symbol if on else None,
    }
    if err:
        out["error"] = err
    from capture.worker import status as worker_status

    worker = worker_status()
    out["writer"] = worker
    if on:
        from capture.bridge_ibkr import book_health, producer_health
        from capture.recorder import status as recorder_status
        from ibkr.tape_recording import dispatch_errors
        health = producer_health(_symbol)
        if health["healthy"] and not recorder_status()["segment_prints"]:
            health = health | {"state": "waiting", "healthy": False}
        out["producer"] = health
        # Prints and the book are separate subscriptions. A recording with no
        # depth line captures tape only, and the operator has to learn that
        # now rather than at replay time (D-064).
        out["book"] = books = book_health(_symbol)
        if books["note"]:
            out.setdefault("warning", books["note"])
        out["healthy"] = health["healthy"] and not worker["error"] and not err
        if health["error"]:
            out["error"] = health["error"]
        elif not health["healthy"]:
            out["error"] = "IBKR AllLast " + health["state"] + "; no recent prints for " + _symbol
        if dispatch_errors.get("capture"):
            out["error"] = dispatch_errors["capture"]
            out["healthy"] = False
    if worker["error"]:
        out["error"] = worker["error"]
    return out
