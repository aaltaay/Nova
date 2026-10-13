"""Nova never cancels a Level 2 request IBKR has not answered (operator ask, 2026-10-13).

maintainer: one-concern every Level 2 cancel Nova sends lives here, behind the one rule that keeps IBKR's 3 lines free

"Create software where it's impossible for this to happen again": all 3 of the login's Level 2 lines were
held inside IB Gateway, and every Level 2 the operator opened was refused (309) until the Gateway restarted.

Tested on the live Gateway, 2026-10-13 ET, from a read-only client of its own (depth requests only):

- 17:57:01 AMD's request, cancelled in the same instant, was granted 302 ms after the cancel (IBKR's 2152),
  and its line stayed held. A second cancel on the same connection (17:57:19) and a disconnect (17:57:26)
  left it held: each later probe got one line fewer. Only the Gateway restart at 17:58:34 freed it.
- Every line cancelled after its grant was freed: MSFT, NVDA, TSLA, GOOGL, NFLX, and AMD at 18:00:30
  (granted at 288 ms, cancelled at 515 ms).
- Grants took 232-1654 ms that evening, on a healthy link. Nova let go of a line 0.75 s after asking for it
  (``IBKR_DEPTH_RELEASE_GRACE_SEC``), and auto-record did that all morning.

The rule:

- **Granted** (IBKR's 2152, a 317 reset, or depth rows on the request): cancelled now.
- **Refused** (309, 10092): forgotten without a cancel. IBKR holds nothing.
- **Not answered yet**: held. The cancel goes out when IBKR answers, however late that is. Nova never sends
  the first message of the race, so IBKR can never answer a request Nova already cancelled. Asking for the
  stock again takes the held request back (``take_back``), and ib_async reuses the registered request rather
  than asking twice.
- **IBKR's connection lost** (the session is not READY): nothing is cancelled. Held requests wait for READY.
  At READY (``on_session_ready``):
  - a request whose socket dropped is forgotten (IB Gateway ends a gone client's requests);
  - one IBKR lost with its data (1101) is cancelled only if IBKR had answered it;
  - one IBKR kept (1102) waits on as before.

Request ids restart with every connection (ib_async's ``Client.reset``; after the Gateway restart at 17:49
that evening they went from 291481 back to 291175), so an id alone never names a request. An answer is kept
with ib_async's request object and counts only while that object is the request; a cancel is kept with its
connection (the IB's client and that connection's start time).

Held requests are on ``/api/ibkr/status`` (``depth_release``) and in the 309 message. Every cancel sent here
is remembered. IBKR granting one of those requests afterwards would mean the rule failed and a line is held
inside IB Gateway: logged as an ERROR that names the stock, and counted (``late_grants``). Nothing more is
sent, since a second cancel does not free the line (tested above).

Threads: ``release`` and ``take_back`` run where a viewer lets go or asks (the HTTP loop). The answer hooks
run on the IB loop, inside ib_async's callback (ADR 010): dict work and at most one cancel, never a wait.
One lock guards the maps.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from constants_ibkr import (
    IBKR_DEPTH_ANSWERS_KEEP,
    IBKR_DEPTH_REGISTRY_KIND,
    IBKR_ERROR_DEPTH_MAX_LINES,
    IBKR_ERROR_DEPTH_NOT_SUPPORTED,
    IBKR_ERROR_DEPTH_RESET,
    IBKR_NOTICE_DEPTH_EXCHANGES,
)
from ibkr import client as _client
from ibkr import line_session

logger = logging.getLogger(__name__)

GRANTED = "granted"
REFUSED = "refused"
_GRANT_CODES = frozenset({IBKR_NOTICE_DEPTH_EXCHANGES, IBKR_ERROR_DEPTH_RESET})
_REFUSAL_CODES = frozenset({IBKR_ERROR_DEPTH_MAX_LINES, IBKR_ERROR_DEPTH_NOT_SUPPORTED})
# Set on a wrapper whose IB is watched (a new IB has a new wrapper).
_INSTALLED = "_nova_depth_release"

# What ``release`` did.
CANCELLED = "cancelled"   # IBKR had answered: the cancel went out
FORGOTTEN = "forgotten"   # IBKR refused it, or lost it unanswered: ib_async let go, no cancel
HELD = "held"             # waiting for IBKR's answer, or its connection, before the cancel
NOTHING = "nothing"       # no request registered: nothing to cancel


@dataclass
class _Held:
    symbol: str
    contract: Any
    smart: bool
    since: float
    sub: Any
    ticker: Any = None
    handler: Any = None


_lock = threading.RLock()
_answers: OrderedDict[int, tuple[Any, str]] = OrderedDict()  # request id -> (ib_async request, answer)
_held: dict[int, _Held] = {}
_sent: OrderedDict[int, tuple[tuple, str, float]] = OrderedDict()  # id -> (connection, symbol, cancelled at)
_reported: set[tuple[tuple, int]] = set()
_counts = {"cancelled": 0, "held": 0, "cancelled_on_answer": 0, "forgotten": 0, "taken_back": 0}
_late: dict[str, Any] = {"count": 0, "last": None}


def reset_for_tests() -> None:
    with _lock:
        _answers.clear()
        _held.clear()
        _sent.clear()
        _reported.clear()
        for key in _counts:
            _counts[key] = 0
        _late.update({"count": 0, "last": None})


def _bounded(d: OrderedDict, key: Any, value: Any) -> None:
    d.pop(key, None)  # re-inserted last: the bound drops the oldest
    d[key] = value
    while len(d) > IBKR_DEPTH_ANSWERS_KEEP:
        d.popitem(last=False)


def _registry(ib: Any) -> Any | None:
    return getattr(getattr(ib, "wrapper", None), "subscriptions", None)


def _registered(ib: Any, contract: Any) -> Any | None:
    """ib_async's registered Level 2 request for the contract, else None."""
    registry = _registry(ib)
    con_id = getattr(contract, "conId", None)
    if registry is None or not con_id:
        return None
    try:
        return registry.find_market_data(con_id, IBKR_DEPTH_REGISTRY_KIND)
    except Exception:
        logger.warning("IBKR depth: could not read ib_async's Level 2 request for conId %s", con_id, exc_info=True)
        return None


def _request_of(ib: Any, req_id: int) -> Any | None:
    """ib_async's live request with this id on this IB, else None (never made, or cancelled / dropped)."""
    get_sub = getattr(_registry(ib), "get_sub", None)
    if get_sub is None:
        return None
    try:
        return get_sub(req_id)
    except Exception:
        logger.warning("IBKR depth: could not read ib_async's request %s", req_id, exc_info=True)
        return None


def _connection(ib: Any) -> tuple:
    """This IB's connection: its client, and when that connection started (ib_async resets ids and clock)."""
    client = getattr(ib, "client", None)
    try:
        started = client.connectionStats().startTime
    except Exception:
        started = None  # not connected: no answer arrives on it either
    return (id(client), started)


def _rows_arrived(ticker: Any) -> bool:
    """The request's book holds rows: IBKR granted it, whatever notice it did or did not send.

    ``cancelMktDepth`` clears these dicts, so rows of an earlier request on the same Ticker are not counted.
    """
    return bool(getattr(ticker, "domBidsDict", None) or getattr(ticker, "domAsksDict", None))


def answer_of(req_id: int, sub: Any) -> str | None:
    """IBKR's answer to ib_async's request ``sub`` so far: GRANTED, REFUSED, or None while it has not answered."""
    with _lock:
        known = _answers.get(req_id)
    if known is not None and known[0] is sub:
        return known[1]
    ticker = getattr(sub, "ticker", None)
    return GRANTED if ticker is not None and _rows_arrived(ticker) else None


def _note(sub: Any, req_id: int, answer: str) -> None:
    with _lock:
        known = _answers.get(req_id)
        if known is not None and known[0] is sub and known[1] == REFUSED:
            return  # a refused request never becomes a line
        _bounded(_answers, req_id, (sub, answer))


def _cancel(ib: Any, req_id: int, contract: Any, symbol: str, smart: bool) -> None:
    """The only ``cancelMktDepth`` Nova sends. Only for a request IBKR has answered."""
    with _lock:
        _bounded(_sent, req_id, (_connection(ib), symbol.upper(), time.time()))
    try:
        ib.cancelMktDepth(contract, isSmartDepth=smart)
    except Exception:
        logger.warning("IBKR depth: the cancel of %s's Level 2 line could not be sent", symbol, exc_info=True)


def _late_grant(ib: Any, req_id: int, now: float) -> bool:
    """IBKR granted a request Nova had cancelled on this connection: the rule failed. True when it was one."""
    connection = _connection(ib)
    with _lock:
        cancelled = _sent.get(req_id)
        if cancelled is None or cancelled[0] != connection:
            return False
        if (connection, req_id) in _reported:
            return True  # reported once per request
        _reported.add((connection, req_id))
        _, symbol, at = cancelled
        _late["count"] += 1
        _late["last"] = {"symbol": symbol, "req_id": req_id, "at": now, "cancelled_at": at}
    logger.error("IBKR depth: IBKR granted %s's Level 2 line (reqId %s) %.1f s after Nova cancelled it -- that line "
                 "is now held inside IB Gateway until it restarts. Nova cancels only answered requests "
                 "(ibkr/depth/release.py), so this is that rule failing.", symbol, req_id, now - at)
    return True


def _forget(ib: Any, contract: Any) -> None:
    """Drop the request from ib_async's registry without a cancel, so the next ask is a real one.

    ib_async keeps a refused request registered, and its ``reqMktDepth`` hands it back instead of asking again.
    """
    sub = _registered(ib, contract)
    if sub is None:
        return
    try:
        sub.close(send_cancel=False)
    except Exception:
        logger.warning("IBKR depth: could not drop the request for conId %s", getattr(contract, "conId", None),
                       exc_info=True)


def forget(ib: Any, contract: Any) -> None:
    """IBKR refused the request (309, 10092): it holds nothing, so ib_async lets it go and no cancel is sent."""
    sub = _registered(ib, contract)
    req_id = getattr(sub, "reqId", None)
    if isinstance(req_id, int):
        _note(sub, req_id, REFUSED)
        with _lock:
            held = _held.pop(req_id, None)
        if held is not None:
            _unwatch(held)
    _forget(ib, contract)
    with _lock:
        _counts["forgotten"] += 1


def _unwatch(held: _Held) -> None:
    if held.ticker is None or held.handler is None:
        return
    try:
        held.ticker.updateEvent -= held.handler
    except (AttributeError, ValueError, TypeError):
        logger.debug("IBKR depth: the rows watch on %s was already gone", held.symbol)


def _hold(ib: Any, req_id: int, sub: Any, contract: Any, symbol: str, smart: bool, now: float) -> None:
    ticker = getattr(sub, "ticker", None)
    held = _Held(symbol=symbol.upper(), contract=contract, smart=smart, since=now, sub=sub, ticker=ticker)
    if ticker is not None:
        def on_rows(t: Any) -> None:
            if getattr(t, "domTicks", None):  # rows in this packet: ib_async clears the list per packet
                on_answer(ib, req_id, GRANTED)
        held.handler = on_rows
        ticker.updateEvent += on_rows
    with _lock:
        previous = _held.pop(req_id, None)
        _held[req_id] = held
        _counts["held"] += 1
    if previous is not None:
        _unwatch(previous)


def release(ib: Any, contract: Any, symbol: str, smart: bool, *, lost: bool = False,
            now: float | None = None) -> str:
    """Let go of the contract's Level 2 request: cancelled only once IBKR has answered it (module docstring).

    ``lost``: the line belongs to a session IBKR restored with its data lost (1101). An unanswered request is
    then gone at IBKR and is forgotten. An answered one is cancelled, which is the safe order.
    """
    sub = _registered(ib, contract)
    req_id = getattr(sub, "reqId", None)
    if sub is None or not isinstance(req_id, int):
        return NOTHING
    answer = answer_of(req_id, sub)
    if answer == REFUSED or (answer is None and lost):
        _forget(ib, contract)
        with _lock:
            _counts["forgotten"] += 1
        return FORGOTTEN
    if answer == GRANTED and _client.is_ready():
        _cancel(ib, req_id, contract, symbol, smart)
        with _lock:
            _counts["cancelled"] += 1
        return CANCELLED
    _hold(ib, req_id, sub, contract, symbol, smart, time.time() if now is None else now)
    why = "IBKR's connection is lost" if answer == GRANTED else "IBKR has not answered it yet"
    logger.info("IBKR depth: holding %s's Level 2 request (reqId %s) -- %s; the cancel goes out when it does",
                symbol, req_id, why)
    return HELD


def _resolve(ib: Any, req_id: int, held: _Held, answer: str, now: float) -> None:
    if _registered(ib, held.contract) is not held.sub:
        return  # ib_async no longer holds this request (its socket dropped): nothing of ours to cancel
    if answer == REFUSED:
        _forget(ib, held.contract)
        with _lock:
            _counts["forgotten"] += 1
        return
    _cancel(ib, req_id, held.contract, held.symbol, held.smart)
    with _lock:
        _counts["cancelled_on_answer"] += 1
    logger.info("IBKR depth: IBKR answered %s's Level 2 request (reqId %s) %.1f s after Nova let it go -- "
                "cancelled it now", held.symbol, req_id, now - held.since)


def on_answer(ib: Any, req_id: int, answer: str, now: float | None = None) -> None:
    """IBKR answered a Level 2 request (IB loop). A held one is cancelled or forgotten now, if IBKR is reachable."""
    ts = time.time() if now is None else now
    sub = _request_of(ib, req_id)
    if sub is None:
        if answer == GRANTED:
            _late_grant(ib, req_id, ts)  # no live request has this id: a grant after Nova's cancel?
        return
    _note(sub, req_id, answer)
    if not _client.is_ready():
        return  # READY settles it
    with _lock:
        held = _held.get(req_id)
        if held is None or held.sub is not sub:
            return
        _held.pop(req_id, None)
    _unwatch(held)
    _resolve(ib, req_id, held, answer, ts)


def take_back(ib: Any, contract: Any) -> bool:
    """The stock is asked for again: a held request carries on as the line. False if there was none to take.

    A held request IBKR refused is forgotten instead, so the new ask is a real one.
    """
    sub = _registered(ib, contract)
    req_id = getattr(sub, "reqId", None)
    if not isinstance(req_id, int):
        return False
    with _lock:
        held = _held.get(req_id)
        if held is None or held.sub is not sub:
            return False
        _held.pop(req_id, None)
    _unwatch(held)
    if answer_of(req_id, sub) == REFUSED:
        _forget(ib, contract)
        with _lock:
            _counts["forgotten"] += 1
        return False
    with _lock:
        _counts["taken_back"] += 1
    logger.info("IBKR depth: %s asked for again while its last request (reqId %s) was held -- it carries on as "
                "the line", held.symbol, req_id)
    return True


def on_session_ready(ib: Any, now: float | None = None) -> None:
    """Every READY (IB loop): settle the requests held while IBKR was unreachable (module docstring)."""
    ts = time.time() if now is None else now
    with _lock:
        pending = list(_held.items())
    for req_id, held in pending:
        fate = line_session.fate(ib, held.contract, IBKR_DEPTH_REGISTRY_KIND, held.ticker)
        if fate == line_session.GONE or _registered(ib, held.contract) is not held.sub:
            with _lock:
                _held.pop(req_id, None)
            _unwatch(held)
            logger.info("IBKR depth: %s's held Level 2 request (reqId %s) ended with its socket", held.symbol, req_id)
            continue
        answer = answer_of(req_id, held.sub)
        if answer is None and fate == line_session.LOST:
            with _lock:
                _held.pop(req_id, None)
            _unwatch(held)
            _forget(ib, held.contract)
            with _lock:
                _counts["forgotten"] += 1
            continue
        if answer is not None:
            with _lock:
                _held.pop(req_id, None)
            _unwatch(held)
            _resolve(ib, req_id, held, answer, ts)


def install(ib: Any) -> bool:
    """Hear IBKR's answers to Level 2 requests on this IB. True when installed (now or before)."""
    wrapper = getattr(ib, "wrapper", None)
    if wrapper is not None and getattr(wrapper, _INSTALLED, False):
        return True
    if wrapper is None:
        logger.warning("IBKR depth: this IB has no wrapper; IBKR's answers to Level 2 requests go unheard")
        return False

    def on_error(reqId, errorCode, errorString, contract=None):
        code = int(errorCode)
        if code in _GRANT_CODES:
            on_answer(ib, int(reqId), GRANTED)
        elif code in _REFUSAL_CODES:
            on_answer(ib, int(reqId), REFUSED)

    ib.errorEvent += on_error
    setattr(wrapper, _INSTALLED, True)
    return True


def held_lines(now: float | None = None) -> list[dict[str, Any]]:
    """The requests Nova let go and still holds for IBKR's answer, oldest first."""
    ts = time.time() if now is None else now
    with _lock:
        rows = sorted(_held.items(), key=lambda item: item[1].since)
    return [{"symbol": h.symbol, "req_id": req_id, "since": h.since, "age_sec": round(ts - h.since, 1),
             "answered": answer_of(req_id, h.sub) is not None} for req_id, h in rows]


def view(now: float | None = None) -> dict[str, Any]:
    """``depth_release`` on ``/api/ibkr/status``."""
    with _lock:
        counts = dict(_counts)
        last = dict(_late["last"]) if _late["last"] else None
        late = {"count": _late["count"], "last": last}
    return {"held": held_lines(now), "counts": counts, "late_grants": late}
