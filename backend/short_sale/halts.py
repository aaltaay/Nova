"""Halts, for the short check: halted now, or within 10 minutes of an up-halt's resumption (ADR 048 1.8).

No short while the stock is halted, and none for ``SHORT_HALT_COOLOFF_SEC`` after an up-halt
resumes: a stock that halted on its way up can halt again on its way up. A state Nova cannot read
refuses, and says why.

**Live, Paper, Sim at the live edge.** Halted now is ``ibkr.halt_status.halted_now`` (IBKR's tick 49
where Nova holds a line, else the Nasdaq halt list while it answers). A resumption is the last one
tick 49 showed this process, or the latest the Nasdaq list names. "No resumption in the last 10
minutes" is a fact only while the Nasdaq list answers, or after tick 49 has read "trading" for 10
minutes; otherwise the cool-off is unknown, and the short refused.

**A past-day Sim replay** reads the day's halt log (the leaderboard's ``halt_events``: IBKR's tick-49
transitions and Nasdaq's list, backfilled from 2021-10) at the playhead, never after it. A day with
no halt log at all is unknown.

**Up or down** (CHOSEN in ADR 048): the side of the LULD limit state the halt came from
(``luld.live.halt_side``), else the last price before the halt against the price
``SHORT_HALT_DIRECTION_LOOKBACK_SEC`` before it. One Nova cannot place counts as up.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from constants_shorts import SHORT_HALT_COOLOFF_SEC, SHORT_HALT_DIRECTION_LOOKBACK_SEC
from short_sale.hours import clock

logger = logging.getLogger(__name__)

PriceFn = Callable[[str, float, float], list[tuple[float, float]]]


@dataclass(frozen=True)
class HaltRead:
    state: str                      # "clear" | "halted" | "cooloff" | "unknown"
    text: str
    resumed_at: float | None = None
    until: float | None = None      # the cool-off's end
    side: str | None = None         # "up" | "down" | None: not placed, counts as up
    source: str | None = None

    @property
    def ok(self) -> bool:
        return self.state == "clear"

    def as_dict(self) -> dict[str, Any]:
        return {"state": self.state, "text": self.text, "resumed_at": self.resumed_at, "until": self.until,
                "side": self.side, "source": self.source}


def _bar_prices(symbol: str, start: float, end: float) -> list[tuple[float, float]]:
    """The 1-minute closes Nova stored between ``start`` and ``end``, as ``(ts, close)``."""
    import bars_store
    from ibkr.historical_derive import bar_unix

    got = bars_store.read(symbol, "1Min", 32, from_ts=start, through_ts=end) or {}
    out = []
    for bar in got.get("bars") or []:
        ts = bar_unix(bar.get("t"))
        if ts is not None:
            out.append((float(ts), float(bar["c"])))
    return out


def direction(symbol: str, halt_start: float | None, *, prices: PriceFn = _bar_prices,
              luld_side: dict[str, Any] | None = None) -> str | None:
    """``"up"`` / ``"down"`` for the halt that began at ``halt_start``; None when Nova cannot place it."""
    if luld_side and luld_side.get("side") in ("up", "down"):
        start = luld_side.get("start")
        if halt_start is None or start is None or abs(float(start) - float(halt_start)) <= 120.0:
            return str(luld_side["side"])
    if halt_start is None:
        return None
    try:
        seen = prices(symbol, float(halt_start) - SHORT_HALT_DIRECTION_LOOKBACK_SEC - 60.0, float(halt_start))
    except Exception:  # no bars to read: the halt stays unplaced, which counts as up
        logger.debug("halt direction: prices unread for %s", symbol, exc_info=True)
        return None
    if len(seen) < 2:
        return None
    seen.sort()
    before, last = seen[0][1], seen[-1][1]
    if last > before:
        return "up"
    if last < before:
        return "down"
    return None


def _from_resume(symbol: str, resume: dict[str, Any], now: float, side: str | None) -> HaltRead:
    resumed = float(resume["resumed_at"])
    until = resumed + SHORT_HALT_COOLOFF_SEC
    if side == "down":
        return HaltRead("clear", f"{symbol} resumed from a down-halt at {clock(resumed)} ET: no cool-off.",
                        resumed_at=resumed, side=side, source=resume.get("source"))
    why = "an up-halt" if side == "up" else "a halt Nova cannot place as up or down (it counts as up)"
    return HaltRead("cooloff", (f"{symbol} resumed from {why} at {clock(resumed)} ET: no short for 10 minutes, "
                                f"until {clock(until)} ET."), resumed_at=resumed, until=until, side=side,
                    source=resume.get("source"))


def live(symbol: str, now: float | None = None) -> HaltRead:
    """Live, Paper and Sim at the live edge."""
    from ibkr import halt_status, nasdaq_halt_feed
    from luld import live as luld_live

    ts = time.time() if now is None else float(now)
    sym = (symbol or "").strip().upper()
    halted = halt_status.halted_now([sym], now=ts).get(sym)
    if halted is True:
        snap = halt_status.snapshot(sym, now=ts) or {}
        start = snap.get("halt_start")
        since = f" since {clock(float(start))} ET" if start else ""
        return HaltRead("halted", f"{sym} is halted{since}: no short until it trades again and 10 minutes pass "
                                  "after an up-halt.", source="ibkr")
    if halted is None:
        return HaltRead("unknown", (f"Nova cannot tell whether {sym} is halted: it holds no IBKR line that "
                                    "reports it, and the Nasdaq halt list is not answering. Open its Trader "
                                    "tab, or wait for the halt list."))
    resumes = [r for r in (halt_status.last_resume(sym), nasdaq_halt_feed.last_resume(sym, now=ts))
               if r and ts - float(r["resumed_at"]) < SHORT_HALT_COOLOFF_SEC]
    if resumes:
        latest = max(resumes, key=lambda r: float(r["resumed_at"]))
        side = direction(sym, latest.get("halt_start"), luld_side=luld_live.halt_side(sym))
        return _from_resume(sym, latest, ts, side)
    if nasdaq_halt_feed.answering(now=ts):
        return HaltRead("clear", f"{sym} is trading, with no halt resumed in the last 10 minutes.", source="nasdaq")
    since = halt_status.clear_since(sym)
    if since is not None and ts - since >= SHORT_HALT_COOLOFF_SEC:
        return HaltRead("clear", f"{sym} has traded without a halt since {clock(since)} ET.", source="ibkr")
    seen = f" its line has read 'trading' only since {clock(since)} ET" if since is not None else " no line watched it"
    return HaltRead("unknown", (f"Nova cannot rule out a halt on {sym} that resumed in the last 10 minutes: the "
                                f"Nasdaq halt list is not answering, and{seen}."))


def replay(symbol: str, at: float, day: str, *, prices: PriceFn | None = None) -> HaltRead:
    """A past-day Sim replay: the day's halt log at the playhead, never after it."""
    from leaderboard import halts as lb_halts
    from leaderboard import store as lb_store

    sym = (symbol or "").strip().upper()
    try:
        db = lb_store.read_only()
        if db is None:
            events = []
        else:
            try:
                events = lb_store.halt_events(db, day, until=float(at))
            finally:
                db.close()
    except Exception as exc:  # an unreadable log is no log: the short is refused, and says so
        logger.warning("halts: the halt log for %s is unreadable: %s", day, exc)
        events = []
    if not events:
        return HaltRead("unknown", (f"Nova has no halt log for {day} up to {clock(at)} ET, so it cannot tell "
                                    f"whether {sym} was halted then: a replay shorts only where the halt log "
                                    "says so."), source="halt_log")
    if lb_halts.halted_at(events, sym, float(at)):
        return HaltRead("halted", f"{sym} was halted at {clock(at)} ET in the replay.", source="halt_log")
    ends = [e for e in events if e.get("symbol") == sym and e.get("event") == "end"
            and float(at) - float(e["ts"]) < SHORT_HALT_COOLOFF_SEC]
    if not ends:
        return HaltRead("clear", f"{sym} had no halt resume in the 10 minutes before {clock(at)} ET.",
                        source="halt_log")
    latest = max(ends, key=lambda e: float(e["ts"]))
    starts = [float(e["ts"]) for e in events if e.get("symbol") == sym and e.get("event") == "start"
              and float(e["ts"]) <= float(latest["ts"])]
    start = max(starts) if starts else None
    side = direction(sym, start, prices=prices) if prices is not None else None
    return _from_resume(sym, {"resumed_at": float(latest["ts"]), "halt_start": start, "source": "halt_log"},
                        float(at), side)
