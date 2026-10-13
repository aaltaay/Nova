"""The band at once for a stock Nova starts following mid-session (ADR 047 amendment, 2026-10-13).

FLYE, 2026-10-13: Nova's first print of it came at 09:43:06 ET, when the operator opened it, and it halted at
09:46:37 -- while its band still waited for five minutes of Nova's own tape, so the chart had no band at all. Now a
tracker that starts between 09:30 and 16:00 asks once for IBKR's trades of the ten minutes before its first print
(``ibkr.historical_trades``) and is rebuilt on them, then on its own inputs since (``Tracker.rebuilt``): an
approximate reference with a history like the exchanges'. When IBKR's pages stop short of ten minutes (a busy
stock), the minutes they missed come from IBKR's 1-minute bars (``minute_rows``).

``ask`` runs when the live worker starts a tracker; the request runs on the IB connect-loop, and its answer comes
back through the worker's queue (``apply``). One request is in flight at a time, so the backfill never holds more
than one of the historical slots an open chart needs. Shed by pacing or an open chart, or failed, it is asked again
by ``tick`` while the tracker still has no reference. ``status`` is what the view says about it.

Owner: this module's per-symbol status, in memory with the trackers (schema_version n/a). Every function is called
with ``luld.live``'s lock held; the IB task only enqueues. ``NOVA_LULD_BACKFILL=0`` turns it off.
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import Any

from luld import rules
from luld.constants_luld import (
    LULD_BACKFILL_BACK_SEC,
    LULD_BACKFILL_ENV,
    LULD_BACKFILL_FAIL_RETRY_SEC,
    LULD_BACKFILL_HEADROOM,
    LULD_BACKFILL_LOST_SEC,
    LULD_BACKFILL_MAX_FAILS,
    LULD_BACKFILL_MAX_PAGES,
    LULD_BACKFILL_PAGE_TIMEOUT_SEC,
    LULD_BACKFILL_RETRY_SEC,
)
from luld.tracker import Tracker

logger = logging.getLogger(__name__)
Put = Callable[[tuple], None]

_status: dict[str, dict[str, Any]] = {}
_in_flight: set[str] = set()
_clock = time.time            # the arrival clock the answer is stamped with (the live tape's)


def enabled() -> bool:
    return (os.environ.get(LULD_BACKFILL_ENV) or "1").strip() != "0"


def ask(symbol: str, tracker: Tracker, first_ts: float, exchange_ts: float | None, put: Put) -> None:
    """A tracker just took its first print: ask for the five minutes before it when that came mid-session and set
    no reference (an opening or reopening print does)."""
    bounds = rules.rth_bounds(first_ts)
    if not enabled() or bounds is None or not (bounds[0] < first_ts < bounds[1]) or tracker.reference is not None:
        tracker.stop_journal()
        return
    # IBKR's second of the first print Nova heard: the trades of that second Nova heard live from it on.
    end = float(int(exchange_ts)) if exchange_ts else float(int(first_ts)) - 1.0
    _status[symbol] = {"state": "asking", "asked_at": round(first_ts, 3), "end": end, "tries": 0, "fails": 0,
                       "next_try": first_ts, "reason": None}
    _send(symbol, tracker, first_ts, put)


def _send(symbol: str, tracker: Tracker, now: float, put: Put) -> None:
    st = _status[symbol]
    if _in_flight:
        st["next_try"] = now + LULD_BACKFILL_RETRY_SEC
        return
    try:
        from ibkr.loop_supervisor import spawn_ib

        spawn_ib(f"luld.backfill.{symbol}", lambda: _job(symbol, st["end"], put))
    except RuntimeError as exc:                     # the IB loop is not running
        _failed(st, now, f"IBKR's connection is not running ({exc})", tracker)
        return
    _in_flight.add(symbol)
    st["tries"] += 1
    st["next_try"], st["sent_at"] = None, now


async def _job(symbol: str, end: float, put: Put) -> None:
    from ibkr import historical_trades
    from ibkr.historical_service import HistoricalShed

    try:
        got = await historical_trades.recent_trades(symbol, end, LULD_BACKFILL_BACK_SEC, max_pages=LULD_BACKFILL_MAX_PAGES,
                                                    headroom=LULD_BACKFILL_HEADROOM,
                                                    timeout=LULD_BACKFILL_PAGE_TIMEOUT_SEC)
    except HistoricalShed as exc:
        put(("backfill_shed", symbol, _clock(), str(exc), end))
    except Exception as exc:  # any IBKR failure: the worker says so and asks again later
        logger.warning("LULD: IBKR's trades before %s could not be read: %s", symbol, exc)
        put(("backfill_failed", symbol, _clock(), f"{type(exc).__name__}: {exc}", end))
    else:
        put(("backfill", symbol, _clock(), got, end))


def _failed(st: dict[str, Any], now: float, reason: str, tracker: Tracker | None) -> None:
    st["fails"] += 1
    st["reason"] = reason
    if st["fails"] >= LULD_BACKFILL_MAX_FAILS:
        st["state"], st["next_try"] = "failed", None
        if tracker is not None:
            tracker.stop_journal()
    else:
        st["next_try"] = now + LULD_BACKFILL_FAIL_RETRY_SEC


def apply(symbol: str, tracker: Tracker, item: tuple) -> Tracker:
    """An answer from the IB task: the tracker rebuilt on IBKR's trades, or why not and when to ask again. Returns the
    tracker to keep. An answer to an earlier tracker of the stock (forgotten, then started again) is dropped."""
    _in_flight.discard(symbol)
    st = _status.get(symbol)
    if st is None or st["state"] != "asking" or item[4] != st["end"]:
        return tracker
    kind, now = item[0], item[2]
    if kind == "backfill_shed":
        st["reason"] = item[3]
        st["next_try"] = now + LULD_BACKFILL_RETRY_SEC
        return tracker
    if kind == "backfill_failed":
        _failed(st, now, item[3], tracker)
        return tracker
    got = item[3]
    rows = [(r["ts"], r["price"], bool(r.get("sets_price")), r.get("conditions") or "", r.get("exchange") or "")
            for r in got["trades"]]
    start = st["end"] - LULD_BACKFILL_BACK_SEC
    filler = [] if got["complete"] else minute_rows(got.get("minutes") or [], start, got["since"], st["end"])
    st.update(pages=got["pages"], trades=sum(1 for r in rows if r[2]), since=round(got["since"], 3),
              complete=got["complete"], minutes=len(got.get("minutes") or []) if filler else 0,
              at=round(now, 3), next_try=None)
    new = tracker.rebuilt(now, filler + rows, since=start if filler else got["since"], complete=got["complete"])
    if new is None:
        st["state"], st["reason"] = "not_needed", _why_not(tracker, now)
        tracker.stop_journal()
        return tracker
    st["state"], st["reason"] = "seeded", None
    return new


def minute_rows(minutes: list[dict[str, Any]], start: float, since: float, end: float) -> list[tuple]:
    """IBKR's 1-minute bars as trades for the minutes from ``start`` to ``since`` the pages did not reach: each
    bar's average price, once per trade it counted, at the middle of its part of those minutes. A bar that runs past
    ``since`` (or began before ``start``) gives the share of its trades its part of the minute holds; the last bar
    ends at ``end``, the first print's second."""
    out: list[tuple] = []
    for bar in minutes:
        m = float(bar["ts"])
        a, b = max(m, start), min(m + 60.0, since)
        span = min(m + 60.0, end) - m
        if b <= a or span <= 0:
            continue
        n = round(int(bar["count"]) * min(1.0, (b - a) / span))
        if n:
            out += [((a + b) / 2, float(bar["average"]), True, "", "")] * n
    return out


def _why_not(tracker: Tracker, now: float) -> str:
    if tracker.reference is not None:
        return "Nova's own tape had set the band first"
    if not tracker.keeps_journal:
        return "Nova's own tape ran past what it keeps while it waited for IBKR's trades"
    if not tracker.view(now)["in_rth"]:
        return "the regular session had ended"
    return "IBKR had no price-setting trades in the 10 minutes before Nova began watching"


def tick(now: float, trackers: dict[str, Tracker], put: Put) -> None:
    """Ask again where an answer said later, while the tracker still has no reference of its own. An answer that
    never came (its queue item dropped) frees the one request in flight."""
    for symbol in list(_in_flight):
        st = _status.get(symbol)
        if st is None:
            _in_flight.discard(symbol)
        elif now - (st.get("sent_at") or now) > LULD_BACKFILL_LOST_SEC:
            _in_flight.discard(symbol)
            _failed(st, now, "IBKR's answer never reached the LULD worker", trackers.get(symbol))
    for symbol, st in list(_status.items()):
        if st["state"] != "asking" or st["next_try"] is None or now < st["next_try"]:
            continue
        tracker = trackers.get(symbol)
        if tracker is None:
            continue
        if tracker.reference is not None:
            st["state"], st["next_try"] = "not_needed", None
            st["reason"] = _why_not(tracker, now)
            tracker.stop_journal()
            continue
        _send(symbol, tracker, now, put)


def status(symbol: str) -> dict[str, Any] | None:
    """The view's ``backfill``: ``{state, asked_at, at, since, trades, minutes, pages, complete, reason}``, or
    None."""
    st = _status.get(symbol)
    if st is None:
        return None
    return {k: st.get(k) for k in ("state", "asked_at", "at", "since", "trades", "minutes", "pages", "complete",
                                   "reason")}


def forget(symbol: str) -> None:
    _status.pop(symbol, None)
    _in_flight.discard(symbol)


def reset() -> None:
    _status.clear()
    _in_flight.clear()
