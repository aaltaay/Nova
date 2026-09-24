"""Independent bounded recording sinks for immutable normalized AllLast prints.

Each print fans out to the Session Record (``capture.bridge_ibkr``) and, for a
watched symbol, the L2 tape archive writer (``ibkr.tape_sink.Sink``).
"""

from __future__ import annotations

import logging
import time

from ibkr.constants_tape_recording import TAPE_RECORD_STALE_SEC
from ibkr.tape_sink import Sink

logger = logging.getLogger(__name__)
_last: dict[str, float] = {}
_since: dict[str, float] = {}
_errors: dict[str, str] = {}
dispatch_errors: dict[str, str] = {}


def _write_l2(payload):
    from l2.tape import persist_print

    persist_print(payload)


def _write_l2_many(payloads):
    from l2.tape import persist_prints

    persist_prints(payloads)


def new_l2_sink() -> Sink:
    """The L2 archive writer: one transaction per batch of prints."""
    return Sink(_write_l2, write_many=_write_l2_many)


l2_sink = new_l2_sink()


def dispatch(payload) -> None:
    """No disk I/O or waiting for sink completion on the IB loop."""
    from capture.bridge_ibkr import enqueue_print

    _last[payload["symbol"]] = payload["receive_ts"]
    for name, enqueue in (("capture", enqueue_print), ("l2", _enqueue_l2)):
        try:
            enqueue(payload)
        except Exception:
            logger.exception("IBKR %s recording dispatch failed", name)
            dispatch_errors[name] = f"{name} recording dispatch failed"
        else:
            # A later print that dispatches cleanly clears the sticky error, so
            # one bad print does not mark every recording failed forever (QA C55).
            dispatch_errors.pop(name, None)


def _enqueue_l2(payload):
    from l2 import tape

    if tape.is_watched(payload["symbol"]):
        # Snapshot ownership before enqueue so delayed rows cannot enter a new session.
        l2_sink.submit(
            dict(payload)
            | {
                "session_id": tape.session_id(payload["symbol"]),
                "watch_started": tape.watch_started(payload["symbol"]),
            }
        )


def rejected(symbol: str, error: str) -> None:
    _errors[symbol] = error


def subscribed(symbol: str) -> None:
    _errors.pop(symbol, None)
    _last.pop(symbol, None)
    _since[symbol] = time.time()


def producer_status(symbol: str) -> dict:
    """``line_since``: when the current line opened -- a line's silence counts from
    its last print, or from this before its first (the tape watch, #525)."""
    last = _last.get(symbol)
    error = _errors.get(symbol)
    stale = time.time() - (last or _since.get(symbol, time.time())) > TAPE_RECORD_STALE_SEC
    state = "error" if error else "stale" if stale else "waiting" if last is None else "receiving"
    return {"state": state, "healthy": state == "receiving", "last_print_ts": last, "error": error,
            "line_since": _since.get(symbol)}
