"""The LULD worker (ADR 047): the IBKR callbacks enqueue, one thread keeps every stock's bands.

``enqueue_print`` (the AllLast handler) and ``note_l1`` (the Level 1 handler) run inside
ib_async socket callbacks, so they only stamp the arrival and put a tuple on a bounded queue
(ADR 010); a full queue drops the item and counts it. One daemon thread feeds each symbol's
``Tracker`` in arrival order and, every ``LULD_TICK_SEC``, reads what the tape cannot say: the
halt state (``ibkr.halt_status``), whether Nova still holds the stock's tape line, IBKR feed gaps
(``ibkr.feed_pulse``) and the day's facts (previous close, tier, coverage).

A tracker starts with a stock's first live print, so the bands exist only where Nova holds an
AllLast line (a Trader tab's Time & Sales, a Session Record, auto-record). It is exact once it
has seen the stock open or reopen with its tape unbroken since; before that, approximate.

Owner: this module's in-memory trackers, forgotten ``LULD_FORGET_SEC`` after their last print.
Not persisted (schema_version n/a): a restart starts every stock over. ``NOVA_LULD=0`` turns the
worker off.
"""
from __future__ import annotations

import logging
import math
import os
import queue
import threading
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from luld import rules, views
from luld.constants_luld import (
    LULD_ENV,
    LULD_FORGET_SEC,
    LULD_QUEUE_MAX,
    LULD_TICK_SEC,
)
from luld.track_record import TRACK_RECORD
from luld.tracker import DEFAULT_OPTIONS, Facts, Tracker

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
FACTS_EVERY_SEC = 5.0

_q: queue.Queue = queue.Queue(maxsize=LULD_QUEUE_MAX)
_lock = threading.Lock()
_thread_lock = threading.Lock()
_thread: threading.Thread | None = None
_trackers: dict[str, Tracker] = {}
# Read by ``note_l1`` on the IB thread without the lock: a set lookup is atomic.
_tracked: set[str] = set()
_last_l1: dict[str, tuple] = {}            # IB thread only: the last quote enqueued per symbol
_close: dict[str, float] = {}              # IBKR tick 9 per symbol, as the L1 line last said
_facts_at: dict[str, float] = {}
_line: dict[str, dict[str, Any]] = {}      # per symbol: {"held": bool, "lost_at": float | None}
_gaps_seen: set[float] = set()
_board_close: dict[tuple[str, str], float | None] = {}   # (symbol, day) -> the leaderboard's previous close
_counts = {"queued": 0, "dropped": 0, "processed": 0, "errors": 0}


def enabled() -> bool:
    return (os.environ.get(LULD_ENV) or "1").strip() != "0"


def _put(item: tuple) -> None:
    try:
        _q.put_nowait(item)
    except queue.Full:
        _counts["dropped"] += 1
        return
    _counts["queued"] += 1
    _ensure_thread()


def enqueue_print(payload: Any) -> None:
    """A live AllLast print (``ibkr/tape_events.py``), stamped with its arrival (``receive_ts``)."""
    if not enabled():
        return
    try:
        _put(("print", str(payload["symbol"]).upper(), float(payload.get("receive_ts") or time.time()),
              float(payload["price"]), bool(payload.get("sets_price")), payload.get("conditions") or "",
              payload.get("exchange") or ""))
    except (KeyError, TypeError, ValueError):
        _counts["dropped"] += 1


def _num(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def note_l1(symbol: str, ticker: Any, arrival: float) -> None:
    """A Level 1 update (``ibkr/ticks_handler.py``): the best bid / offer and tick 9, for a tracked stock."""
    if symbol not in _tracked:
        return
    key = (_num(getattr(ticker, "bid", None)), _num(getattr(ticker, "ask", None)),
           _num(getattr(ticker, "close", None)))
    if _last_l1.get(symbol) == key:
        return
    _last_l1[symbol] = key
    _put(("quote", symbol, arrival, *key))


def _ensure_thread() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=_run, name="luld", daemon=True)
        _thread.start()


def _run() -> None:
    last_tick = 0.0
    while True:
        try:
            item = _q.get(timeout=LULD_TICK_SEC)
        except queue.Empty:
            item = None
        try:
            if item is not None:
                process(item)
            now = time.time()
            if now - last_tick >= LULD_TICK_SEC and _q.empty():
                tick(now)
                last_tick = now
        except Exception:
            _counts["errors"] += 1
            logger.exception("LULD: could not process %s", item[:2] if item else "a tick")


def process(item: tuple) -> None:
    """Apply one queued item (the worker's step; tests call it directly)."""
    with _lock:
        _counts["processed"] += 1
        kind, symbol, ts = item[0], item[1], item[2]
        tracker = _trackers.get(symbol)
        if kind == "print":
            if tracker is None:
                tracker = _trackers[symbol] = Tracker(symbol, started_at=ts, facts=_facts(symbol, ts),
                                                      options=DEFAULT_OPTIONS)
                _tracked.add(symbol)
                _facts_at[symbol] = ts
            tracker.on_print(ts, item[3], eligible=item[4], conditions=item[5], exchange=item[6])
        elif kind == "quote" and tracker is not None:
            if item[5] is not None and _close.get(symbol) != item[5]:
                _close[symbol] = item[5]
                tracker.set_facts(_facts(symbol, ts))     # the band's percentage, the moment tick 9 says
                _facts_at[symbol] = ts
            tracker.on_quote(ts, item[3], item[4])


def _today(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%Y-%m-%d")


def _facts(symbol: str, now: float) -> Facts:
    """The previous close (IBKR tick 9, else the leaderboard's), the tier and coverage."""
    prev_close = _close.get(symbol)
    if prev_close is None:
        key = (symbol, _today(now))
        if key not in _board_close:
            try:
                from sim.prior_close import previous_close

                _board_close[key] = previous_close(symbol, key[1])
            except Exception:
                logger.debug("LULD: no previous close for %s", symbol, exc_info=True)
                _board_close[key] = None
        prev_close = _board_close[key]
    covered, covered_reason = rules.covered(symbol)
    tier, basis, sure = None, None, True
    if rules.tier_needed(prev_close):
        cap = None
        try:
            import fundamentals

            cap = (fundamentals.peek_cached(symbol) or {}).get("market_cap")
        except Exception:
            logger.debug("LULD: no market cap for %s", symbol, exc_info=True)
        tier, basis, sure = rules.tier_from_size(cap)
    elif prev_close is not None:
        basis = "at or under $3.00 both tiers share one band"
    return Facts(prev_close=prev_close, tier=tier, tier_basis=basis, tier_sure=sure, covered=covered, covered_reason=covered_reason)


def _halted(symbols: list[str], now: float) -> dict[str, bool | None]:
    try:
        from ibkr.halt_status import halted_now

        return halted_now(symbols, now=now)
    except Exception:  # maintainer: allow-swallow no halt reading: the trackers change nothing, as for an unknown
        logger.debug("LULD: halt state unread", exc_info=True)
        return {}


def _line_held(symbol: str) -> bool:
    try:
        from ibkr import tape_stream

        return tape_stream.is_subscribed(symbol)
    except Exception:  # maintainer: allow-swallow an unread line state is not a lost line
        logger.debug("LULD: tape line state unread for %s", symbol, exc_info=True)
        return True


def _feed_gaps(now: float) -> list[dict[str, Any]]:
    try:
        from ibkr import feed_pulse

        return feed_pulse.gaps_for_tape(now)
    except Exception:  # maintainer: allow-swallow the feed pulse is down: the tape itself still decides
        logger.warning("LULD: feed gaps unread", exc_info=True)
        return []


def tick(now: float | None = None) -> None:
    """Halts, tape lines, feed gaps and facts; time moves on; idle trackers are forgotten."""
    now = time.time() if now is None else now
    with _lock:
        symbols = list(_trackers)
    if not symbols:
        return
    halted = _halted(symbols, now)
    gaps = [g for g in _feed_gaps(now) if g.get("start") not in _gaps_seen]
    with _lock:
        for gap in gaps:
            _gaps_seen.add(gap["start"])
        for symbol in symbols:
            tracker = _trackers.get(symbol)
            if tracker is None:
                continue
            if now - _facts_at.get(symbol, 0.0) >= FACTS_EVERY_SEC:
                tracker.set_facts(_facts(symbol, now))
                _facts_at[symbol] = now
            state = halted.get(symbol)
            if state is not None:
                tracker.on_halt(now, state)
            line = _line.setdefault(symbol, {"held": True, "lost_at": None})
            held = _line_held(symbol)
            if line["held"] and not held:
                line["lost_at"] = now
            elif held and not line["held"] and line["lost_at"] is not None:
                tracker.on_gap(now, f"Nova did not hold this stock's tape from {views.clock(line['lost_at'])} ET")
                line["lost_at"] = None
            line["held"] = held
            for gap in gaps:
                tracker.on_gap(gap["start"], f"IBKR's data stopped at {views.clock(gap['start'])} ET")
            tracker.advance(now)
            last = tracker.last_print_ts
            if last is not None and now - last > LULD_FORGET_SEC:
                _forget(symbol)
        if len(_gaps_seen) > 200:
            _gaps_seen.clear()


def _forget(symbol: str) -> None:
    _trackers.pop(symbol, None)
    _tracked.discard(symbol)
    _facts_at.pop(symbol, None)
    _line.pop(symbol, None)


def view(symbol: str, now: float | None = None) -> dict[str, Any]:
    """One stock's LULD view on the live feed: its tracker's, or why there is none."""
    now = time.time() if now is None else now
    sym = (symbol or "").strip().upper()
    if not enabled():
        return views.absent_view(sym, now=now, source="live", reason="Nova's LULD calculation is off (NOVA_LULD=0)",
                                 state="off")
    with _lock:
        tracker = _trackers.get(sym)
        if tracker is None:
            return views.absent_view(sym, now=now, source="live", reason=(
                "Nova computes the band from this stock's Time & Sales: it holds no tape line for it now"))
        raw = tracker.view(now)
        facts = tracker.facts
        held = _line.get(sym, {}).get("held", True)
    out = views.tracker_view(raw, facts, symbol=sym, now=now, source="live", track=TRACK_RECORD)
    if not held:
        out["watching"] = False
        out["text"] = "Nova stopped holding this stock's tape: the band is as it last stood"
    else:
        out["watching"] = True
    return out


def status() -> dict[str, Any]:
    with _lock:
        return {"enabled": enabled(), "symbols": sorted(_trackers), "queue_depth": _q.qsize(), **_counts}


def reset_for_tests() -> None:
    with _lock:
        _trackers.clear()
        _tracked.clear()
        _last_l1.clear()
        _close.clear()
        _facts_at.clear()
        _line.clear()
        _gaps_seen.clear()
        _board_close.clear()
        for key in _counts:
            _counts[key] = 0
    while True:
        try:
            _q.get_nowait()
        except queue.Empty:
            break
