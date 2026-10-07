"""LULD on a Session Record replay (ADR 047): the bands at the Sim playhead.

On a Sim desk off the live edge with a Session Record loaded (``sim.capture_player``), the Level 2
ladder shows the bands Nova would have shown at that moment, from the recording's own prints and
book tops through the same ``Tracker``, never ahead of the playhead. The day's halts come from
the leaderboard's halt log (IBKR's tick 49, else the Nasdaq halt feed); a gap between recorded
stretches is a tape gap.

A replay is fed in time order. The worker keeps a copy of the tracker every
``CHECKPOINT_EVERY_SEC`` of replay time, so a scrub back restarts from the copy before it rather
than from the first print. The work runs on its own thread: ``view`` never waits on it, and answers
with the last result (``loading`` until the first) while it catches up.

Owner: this module's one replay state, rebuilt when another recording loads. Not persisted.
"""
from __future__ import annotations

import sqlite3

import bisect
import copy
import logging
import threading
import time
from typing import Any

from luld import rules, views
from luld.constants_luld import LULD_TAPE_GAP_SEC
from luld.track_record import TRACK_RECORD
from luld.tracker import DEFAULT_OPTIONS, Facts, Tracker

logger = logging.getLogger(__name__)
CHECKPOINT_EVERY_SEC = 300.0
_lock = threading.Lock()
_wake = threading.Event()
_thread: threading.Thread | None = None
_want: tuple[str, float] | None = None      # (capture key, playhead) the desk asked for last
_result: dict[str, Any] | None = None       # {"key", "asof", "view"}
_state: dict[str, Any] | None = None        # the replay being fed (worker thread only)


def _capture() -> Any:
    from sim import capture_player

    return capture_player.snapshot()


def _playhead() -> float:
    from sim import capture_player

    return capture_player.asof_unix()


def view(symbol: str) -> dict[str, Any]:
    """The bands at the playhead for the loaded Session Record, or why there are none."""
    sym = (symbol or "").strip().upper()
    now = time.time()
    data = _capture()
    if data is None or data.symbol != sym:
        return views.absent_view(sym, now=now, source="replay", reason=(
            "On a Sim replay, Nova draws the band from a Session Record of this stock; none is loaded"))
    asof = _playhead()
    _ask(data.key, asof)
    with _lock:
        res = _result
    if res is None or res["key"] != data.key:
        return views.absent_view(sym, now=now, source="replay", reason="Reading the recording's tape for the band",
                                 state="warming")
    out = dict(res["view"])
    out["as_of"] = round(res["asof"], 3)
    return out


def _ask(key: str, asof: float) -> None:
    global _want, _thread
    with _lock:
        _want = (key, asof)
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_run, name="luld-replay", daemon=True)
            _thread.start()
    _wake.set()


def _run() -> None:
    while True:
        _wake.wait(timeout=5.0)
        _wake.clear()
        with _lock:
            want = _want
        if want is None:
            continue
        try:
            _serve(*want)
        except Exception:
            logger.exception("LULD replay: could not compute the band at %s", want)


def _halts(day: str, symbol: str) -> list[tuple[float, bool]]:
    """The day's halts for the symbol: IBKR's tick 49 when logged, else the Nasdaq halt feed."""
    try:
        from leaderboard import store

        db = store.read_only()
        if db is None:
            return []
        db.row_factory = sqlite3.Row   # halt_events reads rows by name
        try:
            rows = store.halt_events(db, day, symbols=[symbol])
        finally:
            db.close()
    except Exception:  # maintainer: allow-swallow without the halt log the recording's reopening prints decide
        logger.warning("LULD replay: no halt log for %s %s", symbol, day, exc_info=True)
        return []
    ibkr = [(r["ts"], r["event"] == "start") for r in rows if r.get("source") == "ibkr_ticker_halted"]
    rss = [(r["ts"], r["event"] == "start") for r in rows if r.get("source") == "nasdaq_trade_halt_rss"]
    return sorted(ibkr or rss)


def _events(data: Any) -> list[tuple]:
    from sale_conditions import row_sets_price

    out: list[tuple] = []
    for row in data.prints:
        price = row.get("price")
        if not price:
            continue
        out.append((float(row.get("ts") or 0.0), 0, float(price), row_sets_price(row), row.get("conditions") or "",
                    row.get("exchange") or ""))
    for row in data.quotes:
        out.append((float(row.get("ts") or 0.0), 1, row.get("bid"), row.get("ask")))
    out.sort(key=lambda e: (e[0], e[1]))
    return out


def _facts(data: Any) -> Facts:
    prev = data.prev_close
    covered, reason = rules.covered(data.symbol)
    tier, basis, sure = None, None, True
    if rules.tier_needed(prev):
        cap = None
        try:
            import fundamentals

            cap = (fundamentals.peek_cached(data.symbol) or {}).get("market_cap")
        except Exception:
            logger.debug("LULD replay: no market cap for %s", data.symbol, exc_info=True)
        tier, basis, sure = rules.tier_from_size(cap)
    elif prev is not None:
        basis = "at or under $3.00 both tiers share one band"
    return Facts(prev_close=prev, tier=tier, tier_basis=basis, tier_sure=sure, covered=covered, covered_reason=reason)


def _fresh_state(data: Any) -> dict[str, Any]:
    events = _events(data)
    start = events[0][0] if events else time.time()
    day = data.key.split("|", 1)[0]
    return {"key": data.key, "events": events, "times": [e[0] for e in events], "i": 0,
            "tracker": Tracker(data.symbol, started_at=start, facts=_facts(data), options=DEFAULT_OPTIONS),
            "halts": _halts(day, data.symbol), "hi": 0, "checkpoints": [], "last_cp": start,
            "last_ts": None, "spans": list(data.spans or [])}


def _restore(state: dict[str, Any], asof: float) -> None:
    """Back to the newest copy at or before ``asof`` (or the start)."""
    cps = state["checkpoints"]
    k = bisect.bisect_right([c[0] for c in cps], asof) - 1
    if k < 0:
        data = _capture()
        fresh = _fresh_state(data)
        state.update({key: fresh[key] for key in ("tracker", "i", "hi", "checkpoints", "last_cp", "last_ts")})
        return
    ts, i, hi, tracker, last_ts = cps[k]
    del cps[k + 1:]
    state.update(tracker=copy.deepcopy(tracker), i=i, hi=hi, last_cp=ts, last_ts=last_ts)


def _feed(state: dict[str, Any], asof: float) -> None:
    events, halts, tracker = state["events"], state["halts"], state["tracker"]
    spans = state["spans"]
    i, hi = state["i"], state["hi"]
    while i < len(events) and events[i][0] <= asof:
        ev = events[i]
        ts = ev[0]
        while hi < len(halts) and halts[hi][0] <= ts:
            tracker.on_halt(halts[hi][0], halts[hi][1])
            hi += 1
        last = state["last_ts"]
        if last is not None and ts - last > LULD_TAPE_GAP_SEC and _crosses_gap(spans, last, ts):
            tracker.on_gap(ts, f"The recording has a gap from {views.clock(last)} ET")
        if ev[1] == 0:
            tracker.on_print(ts, ev[2], eligible=ev[3], conditions=ev[4], exchange=ev[5])
            state["last_ts"] = ts
        else:
            tracker.on_quote(ts, ev[2], ev[3])
        i += 1
        if ts - state["last_cp"] >= CHECKPOINT_EVERY_SEC:
            state["checkpoints"].append((ts, i, hi, copy.deepcopy(tracker), state["last_ts"]))
            state["last_cp"] = ts
    while hi < len(halts) and halts[hi][0] <= asof:
        tracker.on_halt(halts[hi][0], halts[hi][1])
        hi += 1
    state["i"], state["hi"] = i, hi
    tracker.advance(asof)


def _crosses_gap(spans: list, a: float, b: float) -> bool:
    """True when ``a`` and ``b`` fall in different recorded stretches (unknown stretches: any long silence)."""
    if not spans:
        return True
    starts = [s[0] for s in spans]
    ka, kb = bisect.bisect_right(starts, a) - 1, bisect.bisect_right(starts, b) - 1
    return ka != kb


def _serve(key: str, asof: float) -> None:
    global _state, _result
    data = _capture()
    if data is None or data.key != key:
        return
    if _state is None or _state["key"] != key:
        _state = _fresh_state(data)
    state = _state
    if asof < state["tracker"].clock:
        _restore(state, asof)
    _feed(state, asof)
    tracker = state["tracker"]
    out = views.tracker_view(tracker.view(asof), tracker.facts, symbol=data.symbol, now=asof, source="replay",
                             track=TRACK_RECORD)
    with _lock:
        _result = {"key": key, "asof": asof, "view": out}


def reset_for_tests() -> None:
    global _want, _result, _state
    with _lock:
        _want, _result, _state = None, None, None
