"""Lines IBKR answers after Nova cancelled them, cancelled again (operator report 2026-10-13).

A cancel that reaches IBKR before IBKR has answered the request does not end the
line: IBKR answers later and holds it. A Level 2 line held that way counts against
the login's 3 until IB Gateway logs in again -- a Nova restart does not free it --
and a Time & Sales line keeps printing to a request id Nova forgot. On 2026-10-13
the desk's link answered in 2-10 s while auto-record let lines go 0.75 s after
asking; by 11:44 ET all 3 Level 2 lines were held this way and every Level 2 the
operator opened was refused (309).

Nova keeps the request id of every Level 2 and Time & Sales line it cancels
(``note_cancelled``, just before the cancel). IBKR's answer to a Level 2 request is
its 2152 notice (the exchanges the line carries): one on a kept id ib_async no
longer holds is the line granted after the cancel, so Nova cancels it again -- IBKR
holds it now, and a held line takes a cancel. A tick-by-tick print on an id
ib_async does not hold is a line IBKR kept, unless it is within
``IBKR_STRAY_LINE_RECANCEL_SEC`` of Nova's own cancel (a print already on its way):
cancelled again too, and the print dropped (ib_async would only log it, once per
print). At most once per id per ``IBKR_STRAY_LINE_RECANCEL_SEC``.

A Level 2 grant that brings no 2152 is not caught here: ib_async binds its depth
handlers when the IB is built and drops depth for an unknown id without a word.
Every late grant on 2026-10-13 came with its 2152 (the login lacks some exchanges'
depth, so IBKR names them on each grant).

The hooks run on the IB loop inside the socket callback (ADR 010): dict reads and
at most one ``client`` send, never a wait.
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Any, Callable

from constants_ibkr import (
    IBKR_NOTICE_DEPTH_EXCHANGES,
    IBKR_STRAY_LINE_KEEP,
    IBKR_STRAY_LINE_RECANCEL_SEC,
)

logger = logging.getLogger(__name__)

DEPTH = "depth"
TAPE = "tape"
# ib_async's registry kind for a Level 2 line (``find_market_data``).
_DEPTH_KIND = "mktDepth"
_TICK_BY_TICK_METHODS = ("tickByTickAllLast", "tickByTickBidAsk", "tickByTickMidPoint")
# Set on a wrapper whose IB is watched (a new IB has a new wrapper, whatever its ``id``).
_INSTALLED = "_nova_cancels_stray_lines"
_WORDS = {
    DEPTH: "IBKR granted %s's Level 2 line (reqId %s) after Nova cancelled it",
    TAPE: "IBKR kept printing %s's Time & Sales (reqId %s) after Nova cancelled it",
}


class _Note:
    __slots__ = ("symbol", "smart", "cancelled_at", "recancelled_at")

    def __init__(self, symbol: str | None, smart: bool, cancelled_at: float | None) -> None:
        self.symbol = symbol
        self.smart = smart
        self.cancelled_at = cancelled_at
        self.recancelled_at: float | None = None


# (kind, request id) -> what Nova knows of the line, oldest first, bounded.
_notes: OrderedDict[tuple[str, int], _Note] = OrderedDict()
_counts: dict[str, int] = {DEPTH: 0, TAPE: 0}
_last: dict[str, Any] | None = None


def reset_for_tests() -> None:
    global _last
    _notes.clear()
    _counts.update({DEPTH: 0, TAPE: 0})
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


def _keep(key: tuple[str, int], note: _Note) -> None:
    _notes.pop(key, None)  # re-inserted last: the bound drops the oldest
    _notes[key] = note
    while len(_notes) > IBKR_STRAY_LINE_KEEP:
        _notes.popitem(last=False)


def note_cancelled(kind: str, req_id: int | None, symbol: str, *, smart: bool = False,
                   now: float | None = None) -> None:
    """Nova is about to cancel this line: keep its id, so IBKR's late answer names it."""
    if req_id is None:
        return
    _keep((kind, req_id), _Note(symbol.upper(), smart, time.time() if now is None else now))


def note_depth_cancel(ib: Any, contract: Any, symbol: str, smart: bool) -> None:
    """Keep the id of the Level 2 line ``cancelMktDepth`` is about to end (call it first)."""
    note_cancelled(DEPTH, request_id(ib, contract, _DEPTH_KIND), symbol, smart=smart)


def _held(ib: Any, req_id: int) -> bool:
    """ib_async still holds a request with this id (a live line of this connection)."""
    registry = getattr(getattr(ib, "wrapper", None), "subscriptions", None)
    try:
        return registry is not None and req_id in registry
    except Exception:
        logger.debug("IBKR: could not ask ib_async about reqId %s", req_id, exc_info=True)
        return True  # unsure: never cancel what may be a live line


def _recancel(kind: str, req_id: int, note: _Note | None, send: Callable[[], None], now: float) -> bool:
    """Send ``send`` (the cancel) unless this id was cancelled again too recently."""
    global _last
    key = (kind, req_id)
    if note is None:
        note = _Note(None, False, None)
        _keep(key, note)
    if note.recancelled_at is not None and now - note.recancelled_at < IBKR_STRAY_LINE_RECANCEL_SEC:
        return False
    first = note.recancelled_at is None
    note.recancelled_at = now
    symbol = note.symbol or "an unknown symbol"
    try:
        send()
    except Exception:
        logger.warning("IBKR: could not cancel reqId %s (%s, %s) again", req_id, kind, symbol, exc_info=True)
        return False
    _counts[kind] += 1
    _last = {"kind": kind, "symbol": note.symbol, "req_id": req_id, "at": now}
    logger.log(logging.WARNING if first else logging.DEBUG,
               _WORDS[kind] + " -- cancelled it again so IBKR frees the line", symbol, req_id)
    return True


def on_depth_notice(ib: Any, req_id: int, code: int, now: float | None = None) -> bool:
    """A 2152 on a Level 2 line Nova cancelled: IBKR granted it late. Cancel again; True when sent."""
    if int(code) != IBKR_NOTICE_DEPTH_EXCHANGES:
        return False
    note = _notes.get((DEPTH, req_id))
    if note is None or _held(ib, req_id):
        return False
    client = getattr(ib, "client", None)
    if client is None:
        return False
    return _recancel(DEPTH, req_id, note, lambda: client.cancelMktDepth(req_id, note.smart),
                     time.time() if now is None else now)


def on_stray_print(ib: Any, req_id: int, now: float | None = None) -> bool:
    """A tick-by-tick print on an id ib_async does not hold. Cancel the line again; True when sent."""
    ts = time.time() if now is None else now
    note = _notes.get((TAPE, req_id))
    if note is not None and note.cancelled_at is not None and ts - note.cancelled_at < IBKR_STRAY_LINE_RECANCEL_SEC:
        return False  # already on its way when Nova cancelled
    client = getattr(ib, "client", None)
    if client is None:
        return False
    return _recancel(TAPE, req_id, note, lambda: client.cancelTickByTickData(req_id), ts)


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
    """Watch this IB for lines answered after Nova cancelled them. True when installed (now or before)."""
    wrapper = getattr(ib, "wrapper", None)
    if wrapper is not None and getattr(wrapper, _INSTALLED, False):
        return True
    if wrapper is None or not hasattr(wrapper, "subscriptions"):
        logger.warning("IBKR: this IB has no ib_async registry; lines IBKR answers after a cancel stay held")
        return False

    def on_error(reqId, errorCode, errorString, contract=None):
        try:
            on_depth_notice(ib, reqId, errorCode)
        except Exception:
            logger.warning("IBKR depth: could not read notice %s on reqId %s", errorCode, reqId, exc_info=True)

    ib.errorEvent += on_error
    for name in _TICK_BY_TICK_METHODS:
        original = getattr(wrapper, name, None)
        if callable(original):
            setattr(wrapper, name, _print_hook(ib, wrapper, original))
    setattr(wrapper, _INSTALLED, True)
    return True


def view() -> dict[str, Any]:
    """``stray_lines`` on ``/api/ibkr/status``: lines cancelled again, by kind, and the last one."""
    return {"recancelled": dict(_counts), "last": dict(_last) if _last else None}
