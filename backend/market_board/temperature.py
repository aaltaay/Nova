"""The small-cap temperature (ADR 053 amendment 2026-10-25): the day hot / warm / cold, the week good / ok / choppy /
cold, the month hot / warm / cold. Stated rules over Nova's recorded Gainers board, not a model.

The climate's lens (the board's first ``MARKET_CLIMATE_RANK_MAX`` ranks), stocks whose prior close is
``MARKET_TEMP_PRICE_MIN``-``MARKET_TEMP_PRICE_MAX``. ``read`` walks one session minute by minute: the runners at
+100% and the money in the ``MARKET_TEMP_TOP`` biggest gainers (shares x last price, by peak gain of 20% or more),
and at its last minute how many runners that peaked at ``MARKET_TEMP_HOLD_PEAK``+ still keep
``MARKET_TEMP_HOLD_SHARE`` of that gain. ``label_days`` compares each session with the usual money of the sessions
before it at the same time of day; a session with no board minute near that time (its recording started later, or
stopped) has no observation and is left out, never read as zero. ``block`` and ``summary`` turn the labels into the
period's word. Pure apart from ``read``'s query.
"""
from __future__ import annotations

import statistics
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from constants_market_board import (
    MARKET_CLIMATE_RANK_MAX,
    MARKET_CLIMATE_THRESHOLDS,
    MARKET_PERIOD_SESSIONS,
    MARKET_TEMP_BASELINE_DAYS,
    MARKET_TEMP_BASELINE_MIN,
    MARKET_TEMP_HOLD_PEAK,
    MARKET_TEMP_HOLD_SHARE,
    MARKET_TEMP_HOT_RUNNERS,
    MARKET_TEMP_MINUTE_GAP_SEC,
    MARKET_TEMP_MONTH_MIN_DAYS,
    MARKET_TEMP_MONTH_SCORE,
    MARKET_TEMP_PRICE_MAX,
    MARKET_TEMP_PRICE_MIN,
    MARKET_TEMP_TOP,
    MARKET_TEMP_WEEK_CHOPPY_HOLD,
    MARKET_TEMP_WEEK_COLD_DAYS,
    MARKET_TEMP_WEEK_GOOD_HOLD,
    MARKET_TEMP_WEEK_HOT_DAYS,
    MARKET_TEMP_WEEK_MIN_DAYS,
)
from market_board import clock

_UP20 = MARKET_CLIMATE_THRESHOLDS["up20"]
_UP100 = MARKET_CLIMATE_THRESHOLDS["up100"]
_DAY_WORDS = ("hot", "warm", "cold")


@dataclass
class Gauges:
    """One session's inputs: per board minute (ascending) the +100% runners and the top gainers' money; the hold at
    its last minute."""
    minutes: list[int] = field(default_factory=list)
    runners: list[int] = field(default_factory=list)
    money: list[float] = field(default_factory=list)
    held: int = 0
    faded: int = 0

    def at(self, ts: float) -> tuple[int, float] | None:
        """(runners, money) at ``ts``, or ``None`` when the board has no minute within ``MARKET_TEMP_MINUTE_GAP_SEC``
        before it (not recorded yet, or a gap): an unobserved time is not zero runners and zero money."""
        i = bisect_right(self.minutes, ts) - 1
        if i < 0 or ts - self.minutes[i] > MARKET_TEMP_MINUTE_GAP_SEC:
            return None
        return self.runners[i], self.money[i]

    def hold(self) -> float | None:
        n = self.held + self.faded
        return self.held / n if n else None


def read(db: Any, iso: str, source: str, board: str, end_ts: float) -> Gauges:
    """One session's gauges from its board rows up to ``end_ts`` (a past session: its close)."""
    out = Gauges()
    peak: dict[str, float] = {}
    last: dict[str, float] = {}
    money: dict[str, float] = {}
    minute: int | None = None
    seen: set[str] = set()
    changes: list[float] = []

    def tally(m: int) -> None:
        top = sorted((p, s) for s, p in peak.items() if p >= _UP20)[-MARKET_TEMP_TOP:]
        out.minutes.append(m)
        out.runners.append(sum(1 for p in peak.values() if p >= _UP100))
        out.money.append(sum(money.get(s, 0.0) for _, s in top))

    for m, sym, price, prev, chg, vol in db.execute(
            "SELECT minute_ts, symbol, price, prev_close, change_pct, volume FROM rows WHERE session_date = ?"
            " AND source = ? AND board = ? AND rank <= ? AND minute_ts <= ? ORDER BY minute_ts",
            (iso, source, board, MARKET_CLIMATE_RANK_MAX, int(end_ts))):
        if m != minute:
            if minute is not None:
                tally(minute)
            minute, seen, changes = m, set(), []
        seen.add(sym)
        if chg is not None:
            changes.append(chg)
        if chg is None or prev is None or not MARKET_TEMP_PRICE_MIN <= prev <= MARKET_TEMP_PRICE_MAX:
            continue
        peak[sym] = max(peak.get(sym, chg), chg)
        last[sym] = chg
        if vol is not None and price is not None:
            money[sym] = float(vol) * float(price)
    if minute is None:
        return out
    tally(minute)
    # A runner gone from a full board is below its 50th row: faded when that row is under half its peak, else unknown.
    floor = min(changes) if len(changes) >= MARKET_CLIMATE_RANK_MAX else None
    for sym, p in peak.items():
        if p < MARKET_TEMP_HOLD_PEAK:
            continue
        keep = MARKET_TEMP_HOLD_SHARE * p
        if sym in seen:
            if last[sym] >= keep:
                out.held += 1
            else:
                out.faded += 1
        elif floor is not None and floor < keep:
            out.faded += 1
    return out


def day_label(runners: int, money: float, usual: float | None) -> str | None:
    if usual is None:
        return None
    if runners >= MARKET_TEMP_HOT_RUNNERS and money > usual:
        return "hot"
    if runners == 0 and money <= usual:
        return "cold"
    return "warm"


def label_days(chain: list[tuple[date, Gauges | None]], as_of: float, count: int) -> list[dict[str, Any]]:
    """The last ``count`` sessions of ``chain`` (oldest first, ``None`` = no board), each with its label. The last
    session is read as of ``as_of`` (today so far), every other at its close; each against the median money of the
    up to ``MARKET_TEMP_BASELINE_DAYS`` sessions with a board before it that were recorded at that minute of the day
    (``Gauges.at``: one recorded later, or across a gap, is left out of the median and of ``usual_days``)."""
    out: list[dict[str, Any]] = []
    n = len(chain)
    for i in range(max(0, n - count), n):
        d, g = chain[i]
        close = clock.at(d, clock.close_minute(d))
        when = min(as_of, close) if i == n - 1 else close
        row: dict[str, Any] = {"date": d.isoformat(), "board": g is not None, "label": None, "runners_100": None,
                               "money": None, "usual_money": None, "usual_days": 0, "hold_pct": None}
        out.append(row)
        if g is None:
            continue
        minute = clock.minute_of_day(when)
        prior = [(pd, pg) for pd, pg in chain[:i] if pg is not None][-MARKET_TEMP_BASELINE_DAYS:]
        seen = (pg.at(clock.at(pd, min(minute, clock.close_minute(pd)))) for pd, pg in prior)
        values = [obs[1] for obs in seen if obs is not None]
        usual = statistics.median(values) if len(values) >= MARKET_TEMP_BASELINE_MIN else None
        hold = g.hold()
        row.update(usual_money=round(usual) if usual is not None else None, usual_days=len(values),
                   hold_pct=round(100.0 * hold, 1) if hold is not None else None)
        now_seen = g.at(when)
        if now_seen is None:
            continue
        runners, money = now_seen
        row.update(label=day_label(runners, money, usual), runners_100=runners, money=round(money))
    return out


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 1) if values else None


def _rule(period: str, days: list[dict[str, Any]]) -> dict[str, Any]:
    """The period's word from its sessions' labels: ``{label, why, hot, warm, cold, labelled, hold_pct, score_pct}``."""
    labelled = [d for d in days if d["label"]]
    counts = {w: sum(1 for d in labelled if d["label"] == w) for w in _DAY_WORDS}
    hold_pct = _mean([d["hold_pct"] for d in labelled if d["hold_pct"] is not None])
    out: dict[str, Any] = {"label": None, "why": None, **counts, "labelled": len(labelled), "hold_pct": hold_pct,
                           "score_pct": None}
    if period == "1D":
        d = days[-1]
        out["label"] = d["label"]
        if not d["board"]:
            out["why"] = "Nova recorded no Gainers board this session"
        elif d["runners_100"] is None:
            out["why"] = "Nova's Gainers board has no recording near this time"
        elif d["label"] is None:
            out["why"] = (f"the usual money needs {MARKET_TEMP_BASELINE_MIN} recorded sessions before this one "
                          f"(Nova has {d['usual_days']})")
        return out
    need = MARKET_TEMP_WEEK_MIN_DAYS if period == "7D" else MARKET_TEMP_MONTH_MIN_DAYS
    if len(labelled) < need:
        out["why"] = f"{len(labelled)} of its {len(days)} sessions have a label; it needs {need}"
        return out
    if period == "7D":
        hold = None if hold_pct is None else hold_pct / 100.0
        if counts["cold"] >= MARKET_TEMP_WEEK_COLD_DAYS:
            out["label"] = "cold"
        elif counts["hot"] >= MARKET_TEMP_WEEK_HOT_DAYS and hold is not None and hold >= MARKET_TEMP_WEEK_GOOD_HOLD:
            out["label"] = "good"
        elif hold is not None and hold < MARKET_TEMP_WEEK_CHOPPY_HOLD:
            out["label"] = "choppy"
        else:
            out["label"] = "ok"
        return out
    score = (counts["hot"] - counts["cold"]) / len(labelled)
    out["score_pct"] = round(100.0 * score, 1)
    out["label"] = "hot" if score >= MARKET_TEMP_MONTH_SCORE else "cold" if score <= -MARKET_TEMP_MONTH_SCORE else "warm"
    return out


def block(period: str, chain: list[tuple[date, Gauges | None]], as_of: float) -> dict[str, Any]:
    """The climate's ``heat`` for ``period``."""
    days = label_days(chain, as_of, MARKET_PERIOD_SESSIONS[period])
    return {**_rule(period, days), "price_min": MARKET_TEMP_PRICE_MIN, "price_max": MARKET_TEMP_PRICE_MAX,
            "days": days}


def summary(chain: list[tuple[date, Gauges | None]], as_of: float) -> dict[str, str | None]:
    """The Day Read's three words: today, the last 5 and the last 21 sessions."""
    days = label_days(chain, as_of, MARKET_PERIOD_SESSIONS["30D"])
    return {"day": _rule("1D", days[-MARKET_PERIOD_SESSIONS["1D"]:])["label"],
            "week": _rule("7D", days[-MARKET_PERIOD_SESSIONS["7D"]:])["label"],
            "month": _rule("30D", days)["label"]}
