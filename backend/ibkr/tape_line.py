"""One AllLast line's end: which IB request it is, why it ended, said out loud (#525).

A tick-by-tick line can end without Nova asking: IB answers an error on its
request id (10189 failed, 10190 the tick-by-tick cap, 354 / 10089 not
entitled, ...). ib_async 2.1.0 (the pinned commit) keeps the line's
subscription registered after such an error, and its ``reqTickByTickData`` is
idempotent per (conId, tick type) -- so a dead line stays "subscribed" and
asking for it again sends nothing to IB. Nova used to match three codes, by
conId only (a Level 1 or depth error on the same contract read as the tape's),
and never let go of the line, so a recording could keep a dead tape while
``is_subscribed`` said all was well.

Here every AllLast request id Nova makes is remembered with its symbol when the
line opens, so an error names its line even when it carries no contract. An
error on a live line's own request id ends that line
(``tape_stream.end_line`` cancels it, so the next request is a real one), and
every end -- IB's, or Nova cancelling a line a recording still uses -- is
logged at WARNING with its reason and kept for the recording's status.

Error callbacks run on the IB loop; ending the line runs on the HTTP loop,
where the viewers' queues live (``loop_supervisor``).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from constants import (
    IBKR_ERROR_TICK_BY_TICK_CODES,
    IBKR_TAPE_LINE_REQ_KEEP,
    IBKR_TAPE_TICK_TYPE,
    IBKR_WARNING_CODE_RANGE,
    IBKR_WARNING_CODES,
)

logger = logging.getLogger(__name__)

# The cause stamped on a line IBKR ended (``ended()``).
TAPE_END_IB_ERROR = "ib_error"

# symbol -> request id of its live line (None: ib_async did not say).
_line_req: dict[str, int | None] = {}
# Every AllLast request id Nova made -> (symbol, IBKR session generation), oldest
# first, bounded. Request ids restart with each connection, so an id only names
# a line within the session that issued it.
_req_symbol: dict[int, tuple[str, int]] = {}
# symbol -> how IBKR ended its last line; cleared when a new line opens.
_ended: dict[str, dict[str, Any]] = {}


def reset_for_tests() -> None:
    _line_req.clear()
    _req_symbol.clear()
    _ended.clear()


def _generation() -> int:
    from ibkr import client

    return client.current_generation()


def _request_id(ib: Any, contract: Any) -> int | None:
    """The request id ib_async gave this contract's AllLast line, from its registry."""
    registry = getattr(getattr(ib, "wrapper", None), "subscriptions", None)
    find = getattr(registry, "find_market_data", None)
    con_id = getattr(contract, "conId", None)
    if find is None or not con_id:
        return None
    try:
        sub = find(con_id, IBKR_TAPE_TICK_TYPE)
    except Exception:
        logger.warning("IBKR tape: could not read the AllLast request id for conId %s", con_id, exc_info=True)
        return None
    req_id = getattr(sub, "reqId", None)
    return req_id if isinstance(req_id, int) else None


def note_subscribed(symbol: str, ib: Any, contract: Any) -> int | None:
    """A new line is open: remember its request id; its predecessor's end is history."""
    sym = symbol.upper()
    req_id = _request_id(ib, contract)
    _line_req[sym] = req_id
    _ended.pop(sym, None)
    if req_id is not None:
        _req_symbol.pop(req_id, None)  # re-inserted last: the bound drops the oldest
        _req_symbol[req_id] = (sym, _generation())
        while len(_req_symbol) > IBKR_TAPE_LINE_REQ_KEEP:
            _req_symbol.pop(next(iter(_req_symbol)))
    return req_id


def note_dropped(symbol: str, why: str) -> None:
    """Nova cancelled a line. Loud when a recording still records that symbol."""
    sym = symbol.upper()
    req_id = _line_req.pop(sym, None)
    from capture.mode import capture_symbols

    if sym in capture_symbols():
        logger.warning("IBKR tape: cancelled the AllLast line of %s (reqId %s) while it is recording -- %s",
                       sym, req_id, why)
    else:
        logger.info("IBKR tape: unsubscribed %s (reqId %s) -- %s", sym, req_id, why)


def ended(symbol: str) -> dict[str, Any] | None:
    """``{at, cause, code, message, req_id}`` of the line IBKR ended, else None."""
    row = _ended.get(symbol.upper())
    return dict(row) if row else None


def line_req(symbol: str) -> int | None:
    return _line_req.get(symbol.upper())


def is_warning(code: int) -> bool:
    low, high = IBKR_WARNING_CODE_RANGE
    return code in IBKR_WARNING_CODES or low <= code < high


def _line_for(req_id: int, code: int, contract: Any) -> tuple[str | None, bool]:
    """(symbol, whether the error is on that symbol's live line) -- or (None, False)."""
    from ibkr import tape_stream

    hit = _req_symbol.get(req_id)
    if hit is not None:
        sym, generation = hit
        if generation != _generation():
            return None, False  # an id from an earlier connection: it names nothing now
        return sym, _line_req.get(sym) == req_id and tape_stream.is_subscribed(sym)
    # Request id unknown: ib_async would not say which id the line got. Match by
    # contract, but only a line whose own id is unknown -- otherwise this error
    # belongs to another request on the same contract (Level 1, depth).
    con_id = getattr(contract, "conId", None) if contract is not None else None
    if con_id is None or code not in IBKR_ERROR_TICK_BY_TICK_CODES:
        return None, False
    for sym, c in list(tape_stream._contracts.items()):
        if getattr(c, "conId", None) == con_id and _line_req.get(sym) is None:
            return sym, True
    return None, False


def on_ib_error(reqId: int, errorCode: int, errorString: str, contract: Any = None) -> None:
    """errorEvent hook: name the AllLast line an error belongs to; end it when it is live."""
    code = int(errorCode)
    sym, live = _line_for(reqId, code, contract)
    if sym is None:
        return
    message = (errorString or "").strip() or f"Tick-by-tick rejected (IB error {code})"
    if is_warning(code):
        logger.warning("IBKR tape: IB notice on %s's AllLast line (reqId %s) -- %s: %s", sym, reqId, code, message)
        return
    if not live:
        # After Nova cancelled the line (IB often answers 300 to the cancel).
        logger.info("IBKR tape: IB error %s arrived for an ended AllLast line of %s (reqId %s): %s",
                    code, sym, reqId, message)
        return
    _ended[sym] = {"at": time.time(), "cause": TAPE_END_IB_ERROR, "code": code, "message": message,
                   "req_id": reqId if reqId in _req_symbol else None}
    why = f"IB error {code}: {message}"
    logger.warning("IBKR tape: IBKR ended the AllLast line of %s (reqId %s) -- %s", sym, reqId, why)
    from ibkr import tape_stream

    _on_http_loop(tape_stream.end_line, sym, why)


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:  # maintainer: allow-swallow no running loop means a plain thread
        return None


def _on_http_loop(fn: Callable[..., Any], *args: Any) -> None:
    """Run ``fn`` where the tape's viewer queues live; inline without a separate HTTP loop."""
    from ibkr import loop_supervisor

    loop = loop_supervisor.get_http_loop()
    if loop is None or not loop.is_running() or _running_loop() is loop:
        fn(*args)
        return
    loop.call_soon_threadsafe(lambda: fn(*args))
