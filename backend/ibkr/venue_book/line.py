"""The Nasdaq-only Level 2 request, the book kept from it, and its frames (ADR 072 Amendment 5).

maintainer: one-concern the one Nasdaq request is asked, read and let go under one lock, by the rule that never cancels an unanswered Level 2 request

Why its own request path: ib_async keeps one Level 2 subscription and one pooled ``Ticker`` per contract id, so
``ib.reqMktDepth`` on ``Stock(sym, "NASDAQ")`` hands back the all-exchange line's ticker and sends nothing when
that stock already has one. This module registers its request under a kind of its own (``_VenueDepthSub``) with
a ticker of its own, and sends ``client.reqMktDepth`` itself: IBKR serves both books of one stock at once
(measured 2026-11-18), and ib_async routes each request's rows to its own ticker by request id.

The book is rebuilt from the row operations (``ibkr.depth.book.DepthBook``, #540), never from ``domBids``. A row
is ``{price, size, side, mm}``: ``mm`` is ``NSDQ`` or empty for the book's own orders, else the market maker
quoting at that price, so a price level is its rows summed.

**Letting a request go follows ``ibkr/depth/release.py``'s rule** (a Level 2 request cancelled before IBKR
answered it can be granted afterwards and stay held inside IB Gateway until it restarts):

- granted (a row on the request, IBKR's 2152, a 317 reset): the cancel goes out now;
- refused (any other error on the request): forgotten without a cancel, IBKR holds nothing;
- not answered yet: held. The cancel goes out when IBKR answers, and no other Nasdaq request is made meanwhile.
  Wanting the same stock again takes the held request back.

**A line outlives a session only if IBKR kept it** (``line_session.fate``'s cases): the same socket restored with
its data kept (1102) is restamped; restored with data lost (1101) it is cancelled if IBKR had answered it, else
forgotten; a dropped socket's request is forgotten. While IBKR is not READY nothing is decided or sent.

One line at a time (the brain has one lane). Memory only. ``follow`` and ``close`` run on the loop the lanes
run on; IBKR's rows and errors arrive inside ib_async's callback: one lock covers each decision.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from constants_ibkr import (
    IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT,
    IBKR_ERROR_DEPTH_MAX_LINES,
    IBKR_ERROR_DEPTH_RESET,
    IBKR_MAX_DEPTH_SYMBOLS,
    IBKR_NOTICE_DEPTH_EXCHANGES,
)
from constants_venue_book import IBKR_VENUE_BOOK_EXCHANGE, IBKR_VENUE_BOOK_RETRY_SEC, IBKR_VENUE_BOOK_ROWS
from ibkr import line_session
from ibkr.depth.book import DepthBook, Level
from market_view.viewer_queues import BookVersion, LatestBookQueue

logger = logging.getLogger(__name__)

VENUE = IBKR_VENUE_BOOK_EXCHANGE
KIND = "mktDepthVenue"              # ib_async's registry key is (contract id, kind): "mktDepth" is the lane's own line
GRANTED, REFUSED = "granted", "refused"
GONE, KEPT, LOST, WAIT = "gone", "kept", "lost", "wait"
_GRANT_CODES = frozenset({IBKR_NOTICE_DEPTH_EXCHANGES, IBKR_ERROR_DEPTH_RESET})
NO_LINE_WORDS = "All {n} Level 2 lines are in use, so Nasdaq's own book of {symbol} waits for one."
REPLAY_WORDS = "The desk is replaying a recorded session: there is no live Nasdaq book."
NOT_READY_WORDS = "IBKR is not connected."
REFUSED_WORDS = "IBKR refused Nasdaq's own book of {symbol}: {why}"
HELD_WORDS = "Waiting for IBKR to answer the Nasdaq book request for {held} before asking for {symbol}'s."


@dataclass(eq=False)
class _Line:
    symbol: str
    ib: Any
    sub: Any
    ticker: Any
    generation: int
    handler: Any = None
    on_error: Any = None
    book: DepthBook = field(default_factory=lambda: DepthBook(IBKR_VENUE_BOOK_ROWS))
    seq: int = 0
    at: float | None = None
    data: dict | None = None
    answer: str | None = None       # IBKR's answer to the request so far: GRANTED, REFUSED, or None
    reset_in: Any = None            # the read (its ``domTicks`` list) IBKR's reset arrived in, and how many of its
    reset_at: int = 0               # row operations came before the reset: those belong to the book IBKR discarded


_lock = threading.RLock()
_line: _Line | None = None          # the request whose book is wanted
_held: list[_Line] = []             # requests no longer wanted that IBKR has not answered (or whose cancel failed)
_want: str | None = None
_error: str | None = None
_retry_at: float = 0.0
_viewers: dict[str, list[LatestBookQueue]] = {}
_VenueDepthSub: Any = None


def reset_for_tests() -> None:
    global _line, _want, _error, _retry_at
    _line, _want, _error, _retry_at = None, None, None, 0.0
    _held.clear()
    _viewers.clear()


def symbol() -> str | None:
    """The stock whose Nasdaq book is asked for on this IBKR session, or None."""
    line = _line
    return line.symbol if line is not None and not line_session.is_stale(line.generation) else None


def is_up(sym: str | None) -> bool:
    s = _sym(sym)
    return bool(s) and symbol() == s


def current(sym: str | None) -> dict | None:
    """The book's last frame data ``{bids, asks}``; None before its first row or for another stock."""
    line = _line
    return line.data if line is not None and is_up(sym) else None


def held() -> list[str]:
    """Stocks whose request Nova let go and IBKR has not answered yet (each still holds its request)."""
    return [h.symbol for h in list(_held)]


def status() -> dict[str, Any]:
    """``{venue, symbol, up, rows, seq, at, error}``: the stock wanted, whether its line is up and has rows."""
    up = _want is not None and is_up(_want)
    line = _line if up else None
    return {"venue": VENUE, "symbol": _want, "up": up, "rows": bool(line and line.data and (line.data["bids"] or line.data["asks"])),
            "seq": line.seq if line else 0, "at": line.at if line else None, "error": None if up else _error}


async def follow(sym: str | None, *, room: bool = True, now: float | None = None) -> dict[str, Any]:
    """Put the book on ``sym`` (None: on nothing). ``room`` False: no Level 2 line is free for it, so it waits."""
    global _want, _error, _retry_at
    from sim.mode import is_replay_desk

    want = _sym(sym) or None
    t = time.time() if now is None else float(now)
    if want != _want:
        _want, _retry_at, _error = want, 0.0, None
    _settle()
    replay = is_replay_desk()
    if _line is not None and (_line.symbol != want or not room or replay):
        close("the desk is replaying a recorded session" if replay else
              "the brain's lane left it" if _line.symbol != want else "a lane needs its Level 2 line")
    if want is None:
        _error = None
    elif replay:
        _error = REPLAY_WORDS
    elif not room:
        _error = NO_LINE_WORDS.format(n=IBKR_MAX_DEPTH_SYMBOLS, symbol=want)
    elif _line is None and t >= _retry_at:
        why = await _open(want)
        _error = why
        _retry_at = t + IBKR_VENUE_BOOK_RETRY_SEC if why else 0.0
    return status()


async def _open(sym: str) -> str | None:
    """Ask IBKR for ``sym``'s book on the exchange itself; why it could not be asked, or None."""
    global _line
    from ibkr import client as _client

    ib = _client.get_ib() if _client.is_ready() else None
    if ib is None:
        return NOT_READY_WORDS
    with _lock:
        back = next((h for h in _held if h.symbol == sym and h.ib is ib and h.answer is None
                     and not line_session.is_stale(h.generation)), None)
        if back is not None:                                # the request is still out: it carries on as this line
            _held.remove(back)
            _line = back
            logger.info("IBKR venue book: %s's unanswered request (reqId %s) taken back", sym, getattr(back.sub, "reqId", None))
            return None
        if _held:
            return HELD_WORDS.format(held=", ".join(h.symbol for h in _held), symbol=sym)
    try:
        contract = _stock(sym)
        qualified = await ib.qualifyContractsAsync(contract)
        if not qualified or qualified[0] is None:
            return REFUSED_WORDS.format(symbol=sym, why=f"it does not know the stock on {VENUE}")
        contract = qualified[0]
        with _lock:
            if _line is not None:                           # another caller asked while this one qualified
                return None if _line.symbol == sym else HELD_WORDS.format(held=_line.symbol, symbol=sym)
            if _held:
                return HELD_WORDS.format(held=", ".join(h.symbol for h in _held), symbol=sym)
            registry = ib.wrapper.subscriptions
            req_id = ib.client.getReqId()
            ticker = registry.new_snapshot_ticker(contract)    # a ticker of its own: the pooled one is the all-exchange line's
            sub = _sub_class()(reqId=req_id, contract=contract, ticker=ticker, isSmartDepth=False)
            registry.add(sub)
            line = _Line(sym, ib, sub, ticker, line_session.generation())
            line.handler = lambda t, _line_=line: _on_update(_line_, t)
            line.on_error = lambda reqId, code, text, c=None, _line_=line: _on_error(_line_, reqId, code, text)
            ticker.updateEvent += line.handler
            ib.errorEvent += line.on_error
            _line = line
            try:
                ib.client.reqMktDepth(req_id, contract, IBKR_VENUE_BOOK_ROWS, False, [])
            except Exception:
                _line = None
                _drop(line)                                 # never sent: IBKR holds nothing
                raise
        logger.info("IBKR venue book: asked %s's own book of %s (conId=%s, reqId=%s, rows=%s)", VENUE, sym,
                    getattr(contract, "conId", None), req_id, IBKR_VENUE_BOOK_ROWS)
        return None
    except Exception as exc:
        logger.exception("IBKR venue book: could not ask %s's own book of %s", VENUE, sym)
        return REFUSED_WORDS.format(symbol=sym, why=f"{type(exc).__name__}: {exc}")


def close(reason: str = "") -> None:
    """The book is no longer wanted: tell its viewers, and let its request go by the rule (module docstring)."""
    global _line
    with _lock:
        line, _line = _line, None
        if line is None:
            return
        _tell(line.symbol, {"type": "closed", "symbol": line.symbol, "venue": VENUE, "reason": reason})
        line.data = None
        how = _let_go(line)
    logger.info("IBKR venue book: %s's own book of %s ended (%s): its request was %s", VENUE, line.symbol,
                reason or "no reason given", how)


def _let_go(line: _Line) -> str:
    """Cancel, forget or hold ``line``'s request; what was done. Caller holds the lock."""
    if line_session.is_stale(line.generation):
        fate = _fate(line)
        if fate == WAIT:
            return _hold(line, "held until IBKR is READY")
        if fate == GONE:
            _drop(line)
            return "forgotten (its socket dropped)"
        if fate == LOST and _answer(line) != GRANTED:
            _drop(line)
            return "forgotten (IBKR lost it unanswered)"
        line.generation = line_session.generation()         # kept, or lost after its grant: decided as a live request
    answer = _answer(line)
    if answer == REFUSED:
        _drop(line)
        return "forgotten (IBKR refused it)"
    if answer == GRANTED:
        return "cancelled" if _cancel(line) else _hold(line, "held: its cancel could not be sent")
    return _hold(line, "held until IBKR answers it")


def _hold(line: _Line, how: str) -> str:
    if line not in _held:
        _held.append(line)
    return how


def _answer(line: _Line) -> str | None:
    """IBKR's answer so far: a refusal or a grant it said, else a grant if the request's book holds rows."""
    if line.answer is not None:
        return line.answer
    t = line.ticker
    return GRANTED if getattr(t, "domBidsDict", None) or getattr(t, "domAsksDict", None) or line.book.bids or line.book.asks else None


def _cancel(line: _Line) -> bool:
    """The only cancel this module sends, for a request IBKR has answered. False when it could not be sent."""
    from ibkr.depth import release      # every Level 2 cancel Nova sends lives there, and is remembered there

    if not release.cancel_answered(line.ib, getattr(line.sub, "reqId", None), line.sub, line.symbol, False):
        return False                    # not sent: ib_async still holds the request, and so does this module
    _drop(line)
    return True


def _drop(line: _Line) -> None:
    """ib_async lets the request go without sending anything; this module stops listening to it."""
    if line in _held:
        _held.remove(line)
    for event, handler in ((getattr(line.ticker, "updateEvent", None), line.handler), (getattr(line.ib, "errorEvent", None), line.on_error)):
        try:
            if event is not None and handler is not None:
                event -= handler
        except (AttributeError, ValueError, TypeError):
            logger.debug("IBKR venue book: a handler of %s was already detached", line.symbol)
    try:
        line.sub.close(send_cancel=False)
    except Exception:
        logger.warning("IBKR venue book: ib_async could not drop %s's request", line.symbol, exc_info=True)
    for name in ("domBids", "domAsks", "domBidsDict", "domAsksDict"):
        rows = getattr(line.ticker, name, None)
        if rows is not None:
            rows.clear()


def _fate(line: _Line) -> str:
    """What became of a request stamped on an earlier session: GONE, KEPT, LOST, or WAIT while IBKR is not READY."""
    from ibkr import client as _client
    from ibkr import session_errors

    ib = _client.get_ib() if _client.is_ready() else None
    if ib is None:
        return WAIT
    if ib is not line.ib:
        return GONE
    try:
        sub = ib.wrapper.subscriptions.find_market_data(getattr(line.sub.contract, "conId", None), KIND)
    except Exception:
        logger.warning("IBKR venue book: could not read ib_async's request for %s; taking it as gone", line.symbol, exc_info=True)
        return GONE
    if sub is not line.sub:
        return GONE                                         # ib_async's disconnect wiped its registry: the socket dropped
    return KEPT if session_errors.last_connectivity_code() == IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT else LOST


def _settle() -> None:
    """Requests of an earlier IBKR session, and held ones IBKR has since answered: decided now."""
    global _line
    with _lock:
        line = _line
        if line is not None and line_session.is_stale(line.generation):
            fate = _fate(line)
            if fate == KEPT:
                line.generation = line_session.generation()   # the same socket, its data kept: the line lives
            elif fate != WAIT:
                _line = None
                _tell(line.symbol, {"type": "closed", "symbol": line.symbol, "venue": VENUE, "reason": "its IBKR session ended"})
                line.data = None
                logger.info("IBKR venue book: %s's request of the last IBKR session was %s", line.symbol, _let_go(line))
        for h in list(_held):
            if line_session.is_stale(h.generation) or _answer(h) is not None:
                _held.remove(h)
                logger.info("IBKR venue book: %s's held request was %s", h.symbol, _let_go(h))


def open_viewer(sym: str) -> LatestBookQueue:
    """A viewer's own queue: the newest book (``BookVersion``) and control frames (``closed``)."""
    q = LatestBookQueue()
    _viewers.setdefault(_sym(sym), []).append(q)
    return q


def close_viewer(sym: str, q: LatestBookQueue) -> None:
    qs = _viewers.get(_sym(sym))
    if qs and q in qs:
        qs.remove(q)
        if not qs:
            _viewers.pop(_sym(sym), None)


def _on_update(line: _Line, ticker: Any) -> None:
    """IBKR's row operations since the last update -> the kept book -> one frame, when it changed (IB thread)."""
    ticks = getattr(ticker, "domTicks", None) or ()
    with _lock:
        if ticks and line.answer is None:
            line.answer = GRANTED                             # a row on the request: IBKR granted it
        if line is not _line:
            if line in _held and line.answer == GRANTED:      # let go before IBKR answered: now it has, so cancel
                _held.remove(line)
                logger.info("IBKR venue book: %s's held request was %s once IBKR answered", line.symbol, _let_go(line))
            return
        if line.reset_in is not None:
            if ticks is line.reset_in:
                ticks = ticks[line.reset_at:]
            line.reset_in, line.reset_at = None, 0
        line.book.apply(ticks)
        data = {"bids": _rows(line.book.bids, "bid"), "asks": _rows(line.book.asks, "ask")}
        if data == line.data:
            return
        line.seq += 1
        line.at = time.time()
        line.data = data
        _tell(line.symbol, BookVersion(line.seq, line.at, data))


def _on_error(line: _Line, req_id: int, code: int, text: str) -> None:
    """IBKR's word on this request alone: a grant, a reset that empties the book, or a refusal (IB thread)."""
    global _line, _error, _retry_at
    if req_id != getattr(line.sub, "reqId", None):
        return
    with _lock:
        if code in _GRANT_CODES:
            if line.answer is None:
                line.answer = GRANTED
            if code == IBKR_ERROR_DEPTH_RESET:
                line.book.reset()                             # IBKR resends the book from row 0
                line.reset_in = getattr(line.ticker, "domTicks", None)
                line.reset_at = len(line.reset_in or ())
        elif 2000 <= code < 3000:                             # IBKR's other notices (farm states)
            return
        else:
            line.answer = REFUSED                             # IBKR holds nothing for a refused request
            logger.warning("IBKR venue book: IBKR refused %s's own book of %s -- %s: %s", VENUE, line.symbol, code, text)
            if line is _line:
                _line = None
                _tell(line.symbol, {"type": "closed", "symbol": line.symbol, "venue": VENUE, "reason": f"IBKR error {code}"})
                line.data = None
                _error = NO_LINE_WORDS.format(n=IBKR_MAX_DEPTH_SYMBOLS, symbol=line.symbol) if code == IBKR_ERROR_DEPTH_MAX_LINES else \
                    REFUSED_WORDS.format(symbol=line.symbol, why=f"{code}: {text}")
                _retry_at = time.time() + IBKR_VENUE_BOOK_RETRY_SEC
            _drop(line)
            return
        if line in _held:                                     # let go before IBKR answered: now it has, so cancel
            _held.remove(line)
            logger.info("IBKR venue book: %s's held request was %s once IBKR answered", line.symbol, _let_go(line))


def _tell(sym: str, item: Any) -> None:
    for q in list(_viewers.get(sym, ())):
        q.put_nowait(item)


def _rows(levels: list[Level], side: str) -> list[dict[str, Any]]:
    return [{"price": lv.price, "size": lv.size, "side": side, "mm": lv.mm} for lv in levels]


def _stock(sym: str) -> Any:
    from ib_async import Stock

    return Stock(sym, VENUE, "USD")


def _sub_class() -> Any:
    """ib_async's Level 2 subscription under a kind of its own, so it never collides with the all-exchange line."""
    from ib_async._subscriptions import MktDepthSub

    global _VenueDepthSub
    if _VenueDepthSub is None:
        kind = KIND

        class VenueDepthSub(MktDepthSub):
            KIND = kind

        _VenueDepthSub = VenueDepthSub
    return _VenueDepthSub


def _sym(sym: str | None) -> str:
    return (sym or "").strip().upper()
