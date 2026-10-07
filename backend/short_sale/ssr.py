"""SSR: may a short sell only above the bid? (Reg SHO Rule 201; ADR 048 1.10)

Once a stock trades 10% or more under the prior session's close, a short may execute only above the
national best bid, for the rest of that day and all of the next. Nova never prices a short on a
guess: SSR reads ``on``, ``off`` or ``unknown``, and unknown counts as on -- a short above the bid is
always legal. SSR never blocks a cover.

**Today.** The trigger is 90% of the prior close: IBKR's tick 9 on the stock's line, else the prior
session's regular-hours close from IBKR's daily bars, else the leaderboard's. On when any price Nova
saw today reached it: IBKR's day low (tick 7), the last trade, today's 1-minute lows in the bar
store, today's whole-day bar. Off only when Nova knows the whole day's low: IBKR's 04:00-20:00
daily bar read at or after 09:30 covers the premarket, and IBKR's day low the session since.

**Yesterday.** On when the prior session's low (its 04:00-20:00 daily bar) reached 90% of the
session before's regular-hours close; off when both are known and it did not.

**A past-day Sim replay** reads the replay's own prints up to the playhead against the replayed
day's prior close (``sim.prior_close``): on when one reached the trigger, never off (Nova does not
know that day's whole tape or the day before), so a replayed short is priced as under SSR.

``request_history`` asks IBKR for the two daily reads on a worker thread -- once a stock a day, again
after 09:30 for today's premarket, again ``SSR_HISTORY_RETRY_SEC`` after a miss -- and keeps them
for the day, in memory.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from constants_scanner import SESSION_RTH_OPEN_MIN_ET
from constants_shorts import (
    SSR_HISTORY_DURATION,
    SSR_HISTORY_RETRY_SEC,
    SSR_HISTORY_TIMEOUT_SEC,
    SSR_HISTORY_WORKERS,
    SSR_TRIGGER_FRACTION,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

PrintsFn = Callable[[str, float, float], list[tuple[float, float]]]


@dataclass(frozen=True)
class SsrRead:
    state: str                  # "on" | "off" | "unknown"
    text: str
    since: str | None = None    # "today" | "yesterday" when on
    trigger: float | None = None
    prior_close: float | None = None
    low: float | None = None

    @property
    def effective_on(self) -> bool:
        """Unknown counts as on: a short above the bid is always legal."""
        return self.state != "off"

    def as_dict(self) -> dict[str, Any]:
        return {"state": self.state, "effective_on": self.effective_on, "text": self.text, "since": self.since,
                "trigger": _round(self.trigger), "prior_close": self.prior_close, "low": self.low}


def _round(x: float | None) -> float | None:
    return None if x is None else round(float(x), 4)


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def _money(x: float | None) -> str:
    return "?" if x is None else f"{x:,.2f}"


# -- IBKR's daily bars, per stock, for the day ------------------------------------------------
_history: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()
_asking: set[str] = set()
_pool: ThreadPoolExecutor | None = None


def _et_day(ts: float) -> date:
    return datetime.fromtimestamp(float(ts), ET).date()


def _rth_open(day: date) -> float:
    return (datetime(day.year, day.month, day.day, tzinfo=ET) + timedelta(minutes=SESSION_RTH_OPEN_MIN_ET)).timestamp()


def history_for(symbol: str, now: float) -> dict[str, Any] | None:
    with _lock:
        got = _history.get((symbol or "").strip().upper())
    if got is None or got.get("day") != _et_day(now).isoformat():
        return None
    return got


def _due(symbol: str, now: float) -> bool:
    got = history_for(symbol, now)
    if got is None:
        return True
    if got.get("error"):
        return now - float(got.get("fetched_at") or 0) >= SSR_HISTORY_RETRY_SEC
    opened = _rth_open(_et_day(now))
    return now >= opened and float(got.get("fetched_at") or 0) < opened


async def _fetch(symbol: str) -> dict[str, Any]:
    from ibkr import historical_service

    whole = await historical_service.request_daily_bars(symbol, SSR_HISTORY_DURATION, use_rth=False)
    regular = await historical_service.request_daily_bars(symbol, SSR_HISTORY_DURATION, use_rth=True)
    return {"all": whole, "rth": regular}


def _ask_in_background(symbol: str) -> None:
    from ibkr.client_bridge import run_coro

    now = time.time()
    entry: dict[str, Any] = {"day": _et_day(now).isoformat(), "fetched_at": now, "all": [], "rth": [], "error": None}
    try:
        got = run_coro(_fetch(symbol), SSR_HISTORY_TIMEOUT_SEC, label="ssr history")
        entry.update(all=list(got.get("all") or []), rth=list(got.get("rth") or []))
    except Exception as exc:  # paced, busy or disconnected: SSR stays unknown (counts as on) and says why
        entry["error"] = f"IBKR's daily bars were not read ({exc})"
        logger.info("SSR: daily bars for %s not read: %s", symbol, exc)
    finally:
        with _lock:
            _history[symbol] = entry
            _asking.discard(symbol)


def request_history(symbol: str, now: float | None = None) -> bool:
    """Ask IBKR for the stock's daily bars on a worker thread, when due; False when not asked."""
    sym = (symbol or "").strip().upper()
    ts = time.time() if now is None else float(now)
    if not sym or not _due(sym, ts):
        return False
    from ibkr import client as _client

    if not _client.is_ready():
        return False
    global _pool
    with _lock:
        if sym in _asking:
            return False
        _asking.add(sym)
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=SSR_HISTORY_WORKERS, thread_name_prefix="nova-ssr")
        pool = _pool
    pool.submit(_ask_in_background, sym)
    return True


def remember_history_for_tests(symbol: str, entry: dict[str, Any]) -> None:
    with _lock:
        _history[(symbol or "").strip().upper()] = entry


def reset_for_tests() -> None:
    with _lock:
        _history.clear()
        _asking.clear()


# -- The read -----------------------------------------------------------------------------------
def _stored_low(symbol: str, day: date, now: float) -> float | None:
    import bars_store

    start = (datetime(day.year, day.month, day.day, tzinfo=ET) + timedelta(hours=4)).timestamp()
    got = bars_store.read(symbol, "1Min", 960, from_ts=start, through_ts=now) or {}
    lows = [_num(bar.get("l")) for bar in got.get("bars") or []]
    lows = [x for x in lows if x is not None]
    return min(lows) if lows else None


def _previous_close(symbol: str, day: date, rth: dict[str, dict[str, Any]]) -> float | None:
    from sim.prior_close import previous_close
    from sim.trading_day import last_open_day

    before = last_open_day(day - timedelta(days=1)).isoformat()
    bar = rth.get(before)
    if bar and _num(bar.get("close")) is not None:
        return float(bar["close"])
    return previous_close(symbol, day.isoformat())


def judge(*, symbol: str, prior_close: float | None, seen: list[float], today_complete: bool,
          yesterday_low: float | None, yesterday_prior: float | None, why_unknown: str) -> SsrRead:
    """The verdict from the facts (pure)."""
    trigger = prior_close * (1.0 - SSR_TRIGGER_FRACTION) if prior_close else None
    low = min(seen) if seen else None
    if trigger is not None and low is not None and low <= trigger:
        return SsrRead("on", (f"SSR is on: {symbol} traded {_money(low)} today, at or under {_money(trigger)} -- 90% of "
                              f"the prior close {_money(prior_close)}. A short sells only above the bid, today and "
                              "all of tomorrow."), since="today", trigger=trigger, prior_close=prior_close, low=low)
    y_trigger = yesterday_prior * (1.0 - SSR_TRIGGER_FRACTION) if yesterday_prior else None
    if yesterday_low is not None and y_trigger is not None and yesterday_low <= y_trigger:
        return SsrRead("on", (f"SSR is on from yesterday: {symbol} fell to {_money(yesterday_low)}, under "
                              f"{_money(y_trigger)} (90% of the close before). A short sells only above the bid "
                              "all of today."), since="yesterday", trigger=trigger, prior_close=prior_close, low=low)
    if today_complete and trigger is not None and low is not None and yesterday_low is not None and y_trigger is not None:
        return SsrRead("off", (f"No SSR: {symbol}'s low today, {_money(low)}, stays over {_money(trigger)} (90% of the "
                               f"prior close {_money(prior_close)}), and yesterday's stayed over 90% of the close "
                               "before."), trigger=trigger, prior_close=prior_close, low=low)
    return SsrRead("unknown", f"SSR unknown: {why_unknown} Nova prices the short as if SSR were on.",
                   trigger=trigger, prior_close=prior_close, low=low)


def live(symbol: str, now: float | None = None) -> SsrRead:
    """Live, Paper and Sim at the live edge: IBKR's line, the bar store, IBKR's daily bars."""
    from ibkr import ticks as _ticks
    from sim.trading_day import last_open_day

    ts = time.time() if now is None else float(now)
    sym = (symbol or "").strip().upper()
    today = _et_day(ts)
    quote = _ticks.last_quotes([sym]).get(sym) or {}
    ticker = _ticks.get_ticker(sym)
    day_low = _num(getattr(ticker, "low", None))
    last = None if quote.get("quote_quality") == "close_fallback" else _num(quote.get("price"))
    hist = history_for(sym, ts) or {}
    whole = {b["date"]: b for b in hist.get("all") or []}
    regular = {b["date"]: b for b in hist.get("rth") or []}
    prior_close = _num(quote.get("prev_close")) or _previous_close(sym, today, regular)
    today_bar = _num((whole.get(today.isoformat()) or {}).get("low"))
    try:
        stored = _stored_low(sym, today, ts)
    except Exception:  # the bar store is optional evidence: without it SSR leans to on, never off
        logger.debug("SSR: stored 1-minute lows unread for %s", sym, exc_info=True)
        stored = None
    seen = [x for x in (day_low, last, today_bar, stored) if x is not None]
    complete = (today_bar is not None and day_low is not None
                and float(hist.get("fetched_at") or 0) >= _rth_open(today))
    prior = last_open_day(today - timedelta(days=1))
    y_low = _num((whole.get(prior.isoformat()) or {}).get("low"))
    y_prior = _previous_close(sym, prior, regular)
    missing = []
    if prior_close is None:
        missing.append("the prior close is not known")
    if not complete:
        missing.append(hist.get("error") or "Nova does not have today's whole-day low yet (IBKR's daily bar read "
                                            "after 09:30 and its day low)")
    if y_low is None or y_prior is None:
        missing.append("yesterday's low or the close before it is not known")
    return judge(symbol=sym, prior_close=prior_close, seen=seen, today_complete=complete, yesterday_low=y_low,
                 yesterday_prior=y_prior, why_unknown="; ".join(missing) + ".")


def replay(symbol: str, at: float, day: str, prints: PrintsFn) -> SsrRead:
    """A past-day Sim replay: the replay's prints up to the playhead, never after it."""
    from sim.prior_close import previous_close

    sym = (symbol or "").strip().upper()
    prior_close = previous_close(sym, day)
    d = date.fromisoformat(day)
    start = (datetime(d.year, d.month, d.day, tzinfo=ET) + timedelta(hours=4)).timestamp()
    try:
        seen = [float(price) for _ts, price in prints(sym, start - 1.0, float(at)) if _num(price) is not None]
    except Exception:  # no replay prints: SSR stays unknown, which counts as on
        logger.debug("SSR: replay prints unread for %s", sym, exc_info=True)
        seen = []
    return judge(symbol=sym, prior_close=prior_close, seen=seen, today_complete=False, yesterday_low=None,
                 yesterday_prior=None,
                 why_unknown=("a replay knows only the prints it loaded, not the whole day or the day before"
                              if prior_close is not None else "the replayed day's prior close is not known"))
