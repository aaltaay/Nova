"""Per-symbol session record (right-click tab Record) — not a desk capsule mode.

Up to CAPTURE_MAX_CONCURRENT symbols record at once, each with its own IBKR
lines (capture.feed_hold) and its own recorder session; ``capture_symbol`` is
the first of them for callers that still think in one.
"""
from __future__ import annotations

import logging
from typing import Any

from capture.constants_capture import CAPTURE_MAX_CONCURRENT

logger = logging.getLogger(__name__)

# Symbols recording, in the order they started.
_symbols: list[str] = []


def reset_for_tests() -> None:
    _symbols.clear()


def is_capture_mode() -> bool:
    """True while any tab Record session is active (legacy name kept for guards)."""
    return bool(_symbols)


def capture_symbol() -> str | None:
    """The first recording symbol, for single-symbol callers."""
    return _symbols[0] if _symbols else None


def capture_symbols() -> list[str]:
    return list(_symbols)


def _waiting_error(symbol: str) -> str:
    return "IBKR AllLast waiting; no recent prints for " + symbol


def set_capture_mode(
    enabled: bool, *, symbol: str | None = None, protect_active: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    """Start/stop recording one symbol (or stop all); HTTP callers protect existing owners.

    Internal lifecycle callers may deliberately rotate sessions. Both paths run
    ownership checks on the writer after previously accepted batches drain.
    """
    from capture.bridge_ibkr import flush_book, flush_prints
    from capture.worker import transition

    requested = (symbol or "").strip().upper()
    # Before transition() closes ingress and fences the old sessions: the
    # bridge holds the prints buffered since its last batch. A print is an
    # event, so any lifecycle change must write them; orphaned, they would be
    # dropped in silence.
    for sym in list(_symbols):
        flush_prints(sym)
    if not enabled:
        # The book is a snapshot, not an event: only a stop needs the newest
        # coalesced one, which a burst that went quiet leaves unflushed.
        for sym in ([requested] if requested else list(_symbols)):
            if sym in _symbols:
                flush_book(sym)
    result = transition(lambda: _set_capture_mode(
        enabled, symbol=symbol, protect_active=protect_active, reason=reason,
    ))
    out = status_payload() | (result or {})
    if not (result or {}).get("error"):
        out = _own_reply_error(out, enabled=enabled, symbol=requested or capture_symbol() or "")
    return out


def _own_reply_error(out: dict[str, Any], *, enabled: bool, symbol: str) -> dict[str, Any]:
    """A command that went through answers only for its own symbol (QA 2026-09-22, C55).

    The status payload's top-level ``error`` is the first recording's trouble
    (or a sticky dispatch error), so starting or stopping B used to come back
    as a failure carrying A's tape error. The reply keeps just B's own error --
    minus the "waiting for the first print" state right after admission, which
    polls report, not the command -- and the writer's, which stops everything.
    """
    own = (out.get("errors") or {}).get(symbol) if enabled else None
    if own == _waiting_error(symbol):
        # Admission succeeded but the first write is pending. Report that on polls,
        # not as a failed command (the UI retains command errors until next action).
        own = None
    error = own or (out.get("writer") or {}).get("error")
    reply = dict(out)
    if error:
        reply["error"] = error
    else:
        reply.pop("error", None)
    return reply


def _set_capture_mode(
    enabled: bool, *, symbol: str | None = None, protect_active: bool = False,
    reason: str | None = None,
) -> dict[str, Any] | None:
    _reconcile()
    requested = (symbol or "").strip().upper()
    if enabled:
        sym = requested or (_symbols[0] if _symbols else "")
        if not sym:
            return {
                "capture": False,
                "error": "Pick a symbol tab before Record",
                "mode": None,
                "capture_symbol": None,
            }
        if sym in _symbols and protect_active:
            return None  # Idempotent: do not reopen files or reset the active segment.
        if sym not in _symbols and len(_symbols) >= CAPTURE_MAX_CONCURRENT:
            return {"error": _limit_error(), "conflict": True}
        from capture.bridge_ibkr import admission_error
        error = admission_error(sym)
        if error:
            return {"error": error}
        try:
            from capture.recorder import RecorderLimit, start_recorder

            start_recorder(sym, resume=True)
        except RecorderLimit as exc:
            return {"error": str(exc), "conflict": True}
        except Exception:
            logger.exception("RECORD: recorder start failed")
            return {"error": "Recorder start failed"}
        if sym not in _symbols:
            _symbols.append(sym)
    else:
        if requested and requested not in _symbols and protect_active:
            return {"error": f"{requested} is not recording", "conflict": True}
        from capture.recorder import stop_recorder

        for sym in ([requested] if requested else list(_symbols)):
            try:
                if reason:
                    stop_recorder(symbol=sym, reason=reason)
                else:
                    stop_recorder(symbol=sym)
            except Exception:
                logger.exception("RECORD: recorder stop failed")
                _reconcile()
                return {"error": "Recorder stop failed"}
            if sym in _symbols:
                _symbols.remove(sym)
    logger.info("RECORD: %s symbols=%s", "on" if _symbols else "off", _symbols)
    return None


def _limit_error() -> str:
    return (
        f"Already recording {', '.join(_symbols)} -- IBKR allows {CAPTURE_MAX_CONCURRENT} "
        "depth lines; stop one first"
    )


def _reconcile() -> str | None:
    """Follow the recorder, not our own list (D-068).

    The recorder stops a session itself when writes keep failing (disk full,
    drive unplugged, revoked handle).  Without this, the symbol stayed listed
    and ``/api/capture`` kept answering ``capture: true`` while nothing was
    being written — the operator only found out at replay time.  Returns the
    error to surface: a session that just dropped, else the primary session's.
    """
    try:
        from capture.recorder import is_recording, last_error
    except Exception:
        logger.exception("RECORD: recorder status unavailable")
        return None
    dropped: str | None = None
    for sym in list(_symbols):
        if is_recording(sym):
            continue
        err = last_error(sym)
        _symbols.remove(sym)
        logger.warning("RECORD: recorder stopped itself for %s (%s) — dropping it from record mode", sym, err or "unknown")
        dropped = dropped or err
    return dropped or last_error()


def status_payload() -> dict[str, Any]:
    err = _reconcile()
    symbols = list(_symbols)
    on = bool(symbols)
    out: dict[str, Any] = {
        "capture": on,
        "mode": "record" if on else None,
        "capture_symbol": symbols[0] if on else None,
        "capture_symbols": symbols,
        # Each recording symbol's own trouble, so no reader pins one symbol's
        # tape error on another (C55); ``error`` stays the legacy single value.
        "errors": {},
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

        sessions: dict[str, dict[str, Any]] = {}
        all_healthy = True
        first_error: str | None = None
        first_warning: str | None = None
        for sym in symbols:
            health = producer_health(sym)
            rec = recorder_status(sym)
            if health["healthy"] and not rec["segment_prints"]:
                health = health | {"state": "waiting", "healthy": False}
            # Prints and the book are separate subscriptions. A recording with no
            # depth line captures tape only, and the operator has to learn that
            # now rather than at replay time (D-064).
            books = book_health(sym)
            entry: dict[str, Any] = {
                "producer": health,
                "book": books,
                "recorder": rec,
                "healthy": bool(health["healthy"] and not worker["error"] and not rec["error"]),
            }
            if health["error"]:
                entry["error"] = health["error"]
            elif not health["healthy"]:
                entry["error"] = "IBKR AllLast " + health["state"] + "; no recent prints for " + sym
            if books["note"]:
                entry["warning"] = books["note"]
            sessions[sym] = entry
            own_error = entry.get("error") or rec["error"]
            if own_error:
                out["errors"][sym] = own_error
            all_healthy = all_healthy and entry["healthy"]
            first_error = first_error or entry.get("error")
            first_warning = first_warning or entry.get("warning")
        out["sessions"] = sessions
        # The first symbol's lines at the top level, for single-symbol readers.
        first = sessions[symbols[0]]
        out["producer"] = first["producer"]
        out["book"] = first["book"]
        if first_warning:
            out.setdefault("warning", first_warning)
        out["healthy"] = all_healthy and not err
        if first_error:
            out["error"] = first_error
        if dispatch_errors.get("capture"):
            out["error"] = dispatch_errors["capture"]
            out["healthy"] = False
    if worker["error"]:
        out["error"] = worker["error"]
    return out
