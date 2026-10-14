"""Time & Sales lines IBKR keeps printing after Nova cancelled them, cancelled again (operator report 2026-10-13).

On 2026-10-13 four Time & Sales lines Nova
had cancelled kept printing -- 47,749 prints on request ids Nova no longer knew --
and IBKR refused Time & Sales 74 times (10190).

Tick-by-tick has no grant message. Nova keeps the request id of every Time & Sales
line it cancels (``note_cancelled``, just before the cancel). A print on an id
ib_async does not hold is a line IBKR kept, unless it is within
``IBKR_STRAY_LINE_RECANCEL_SEC`` of Nova's own cancel (a print already on its way):
cancelled again, and the print dropped (ib_async would only log it, once per print).
At most once per id per ``IBKR_STRAY_LINE_RECANCEL_SEC``. Whether that second cancel
frees the line at IBKR is not proven: for Level 2 it does not (tested on the live
Gateway, 2026-10-13 17:57 ET), which is why ``ibkr/depth/release.py`` never sends a
Level 2 cancel before IBKR has answered.

The hooks run on the IB loop inside the socket callback (ADR 010): dict reads and
at most one ``client`` send, never a wait.
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

from constants_ibkr import IBKR_STRAY_LINE_KEEP, IBKR_STRAY_LINE_RECANCEL_SEC

logger = logging.getLogger(__name__)

TAPE = "tape"
_TICK_BY_TICK_METHODS = ("tickByTickAllLast", "tickByTickBidAsk", "tickByTickMidPoint")
# Set on a wrapper whose IB is watched (a new IB has a new wrapper, whatever its ``id``).
_INSTALLED = "_nova_cancels_stray_lines"
_WORDS = "IBKR kept printing %s's Time & Sales (reqId %s) after Nova cancelled it"


@dataclass
class _Note:
    symbol: str | None
    cancelled_at: float | None
    cancel_sent: bool | None = None
    cancel_error: str | None = None
    last_stray_at: float | None = None
    recancelled_at: float | None = None
    recancel_sent: bool | None = None
    recancel_error: str | None = None


# (connection, kind, request id) -> what Nova knows of the line, oldest first, bounded.
_notes: OrderedDict[tuple, _Note] = OrderedDict()
_counts: dict[str, int] = {TAPE: 0}
_last: dict[str, Any] | None = None


def reset_for_tests() -> None:
    global _last
    _notes.clear()
    _counts.update({TAPE: 0})
    _last = None


def request_id(ib: Any, contract: Any, kind: str) -> int | None:
    """The request id ib_async gave this contract's ``kind`` line (``mktDepth``, ``AllLast``), else None."""
    registry = getattr(getattr(ib, "wrapper", None), "subscriptions", None)
    find = getattr(registry, "find_market_data", None)
    con_id = getattr(contract, "conId", None)
    if find is None or not con_id:
        return None
    try:
        sub = find(con_id, kind)
    except Exception:
        logger.warning("IBKR: could not read the %s request id for conId %s", kind, con_id, exc_info=True)
        return None
    req_id = getattr(sub, "reqId", None)
    return req_id if isinstance(req_id, int) else None


def _connection(ib: Any) -> tuple:
    """Wrapper identity plus connection start: request ids and their cooldowns restart together."""
    wrapper = getattr(ib, "wrapper", ib)
    token = getattr(wrapper, "_nova_tape_connection_token", None)
    if token is None:
        token = object()
        wrapper._nova_tape_connection_token = token
    client = getattr(ib, "client", None)
    return token, getattr(client, "_startTime", None)


def _keep(key: tuple, note: _Note) -> None:
    _notes.pop(key, None)  # re-inserted last: the bound drops the oldest
    _notes[key] = note
    while len(_notes) > IBKR_STRAY_LINE_KEEP:
        _notes.popitem(last=False)


def note_cancelled(kind: str, req_id: int | None, symbol: str, *, ib: Any, now: float | None = None) -> None:
    """Nova is about to cancel this Time & Sales line: keep its id, so IBKR's late prints name it."""
    if req_id is None:
        return
    _keep((_connection(ib), kind, req_id), _Note(symbol.upper(), time.time() if now is None else now))


def note_cancel_result(ib: Any, req_id: int | None, *, error: str | None) -> None:
    """Dispatch outcome only. SDK removal and successful sends say nothing about IBKR slot release."""
    note = _notes.get((_connection(ib), TAPE, req_id))
    if note is not None:
        note.cancel_sent, note.cancel_error = error is None, error


def _recancel(key: tuple, note: _Note | None, send: Callable[[], None], now: float) -> bool:
    """Send ``send`` (the cancel) unless this id was cancelled again too recently."""
    global _last
    req_id = key[-1]
    if note is None:
        note = _Note(None, None)
        _keep(key, note)
    if note.recancelled_at is not None and now - note.recancelled_at < IBKR_STRAY_LINE_RECANCEL_SEC:
        return False
    first = note.recancelled_at is None
    note.recancelled_at = now
    symbol = note.symbol or "an unknown symbol"
    try:
        send()
    except Exception as exc:
        note.recancel_sent, note.recancel_error = False, str(exc)
        logger.warning("IBKR: could not cancel reqId %s (%s) again", req_id, symbol, exc_info=True)
        return False
    note.recancel_sent, note.recancel_error = True, None
    _counts[TAPE] += 1
    _last = {"kind": TAPE, "symbol": note.symbol, "req_id": req_id, "at": now}
    logger.log(logging.WARNING if first else logging.DEBUG, _WORDS + " -- cancelled it again", symbol, req_id)
    return True


def on_stray_print(ib: Any, req_id: int, now: float | None = None) -> bool:
    """A tick-by-tick print on an id ib_async does not hold. Cancel the line again; True when sent."""
    ts = time.time() if now is None else now
    key = (_connection(ib), TAPE, req_id)
    note = _notes.get(key)
    if note is None:
        note = _Note(None, None)
        _keep(key, note)
    note.last_stray_at = ts
    if note is not None and note.cancelled_at is not None and ts - note.cancelled_at < IBKR_STRAY_LINE_RECANCEL_SEC:
        return False  # already on its way when Nova cancelled
    client = getattr(ib, "client", None)
    if client is None:
        return False
    return _recancel(key, note, lambda: client.cancelTickByTickData(req_id), ts)


def _print_hook(ib: Any, wrapper: Any, original: Callable[..., Any]) -> Callable[..., Any]:
    def hook(reqId, *args, **kwargs):
        registry = getattr(wrapper, "subscriptions", None)
        if registry is None or registry.get_ticker(reqId) is not None:
            return original(reqId, *args, **kwargs)
        try:
            on_stray_print(ib, reqId)
        except Exception:
            logger.warning("IBKR tape: could not handle a print on unknown reqId %s", reqId, exc_info=True)
        return None
    return hook


def install(ib: Any) -> bool:
    """Watch this IB for Time & Sales lines printing after Nova cancelled them. True when installed."""
    wrapper = getattr(ib, "wrapper", None)
    if wrapper is not None and getattr(wrapper, _INSTALLED, False):
        return True
    if wrapper is None or not hasattr(wrapper, "subscriptions"):
        logger.warning("IBKR: this IB has no ib_async registry; Time & Sales lines IBKR keeps stay printing")
        return False
    for name in _TICK_BY_TICK_METHODS:
        original = getattr(wrapper, name, None)
        if callable(original):
            setattr(wrapper, name, _print_hook(ib, wrapper, original))
    setattr(wrapper, _INSTALLED, True)
    return True


def view() -> dict[str, Any]:
    """``stray_lines`` on ``/api/ibkr/status``: Time & Sales lines cancelled again, and the last one."""
    cancellations = [
        {"symbol": note.symbol, "req_id": key[-1], "cancelled_at": note.cancelled_at,
         "cancel_sent": note.cancel_sent, "cancel_error": note.cancel_error,
         "last_stray_at": note.last_stray_at, "recancelled_at": note.recancelled_at,
         "recancel_sent": note.recancel_sent, "recancel_error": note.recancel_error}
        for key, note in list(_notes.items())
    ]
    return {"recancelled": dict(_counts), "last": dict(_last) if _last else None,
            "cancellations": cancellations}
