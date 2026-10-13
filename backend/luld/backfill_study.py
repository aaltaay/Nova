"""How close a backfilled LULD band comes to the exchanges' (ADR 047 amendment, 2026-10-13).

Read-only, like ``luld/study.py``, on the same Massive ticker-days and the same truth: every NBBO row
the SIP flagged on a band. For each flagged touch it starts a tracker ``lead`` seconds before it, as
if the operator had opened the stock then, and asks what that tracker shows at the touch. Every variant
but ``none`` is the live worker's ``Tracker.rebuilt``, landing ``BACKFILL_DELAY_SEC`` after the first
print, on different trades before it:

- ``none``: today's tracker, which waits for five minutes of its own tape.
- ``ticks_<n>``: IBKR's trades of the five minutes before the start, the most recent ``n`` (``n / 1000``
  pages); ``ticks_all`` has every one. Five minutes seed the reference as the first print arrives: a
  mean taken at once.
- ``replay_<n>``: the same over ten minutes. The tracker seeds itself five minutes into them and runs the
  1% / 30 s rule over the rest, so its reference has a history like the exchanges'. Pages that reach back
  less than five minutes seed when they land.
- ``bars``: the ten minutes as 1-minute bars at their best (each minute's own mean of trades and its count),
  turned into trades as the live worker turns IBKR's (``backfill.minute_rows``). IBKR's bars carry a
  volume-weighted average, not this, so real bars can only do worse.
- ``hybrid_<n>``: what ships: ``replay_<n>``, and when its ``n`` trades stop short of ten minutes, the minutes
  before them from those bars.
"""
from __future__ import annotations

import bisect
from typing import Any

from luld.backfill import minute_rows
from luld.study import APPROX_VARIANT, VARIANTS, _ts_at, et
from luld.tracker import Facts, Tracker

LEADS = (30, 60, 120, 180, 240)
CAPS = (1000, 4000)
REPLAY_CAPS = (4000, 10000)
TICKS_SEC = 300.0
REPLAY_SEC = 600.0
BACKFILL_DELAY_SEC = 2.0
Row = tuple[float, float, bool, str, str]


def variants() -> list[str]:
    return ["none", "ticks_all", *[f"ticks_{c}" for c in CAPS], "replay_all", *[f"replay_{c}" for c in REPLAY_CAPS],
            "bars", "hybrid_4000"]


def _minute_bars(trades: list, start: float, end: float) -> list[dict[str, Any]]:
    """1-minute bars at their best, from the trades before ``end``: each minute's own mean of trades and how many."""
    by_min: dict[int, list[float]] = {}
    for ts, price, eligible, _codes, _venue in trades:
        if eligible and start - 60 < ts < end:
            by_min.setdefault(int(ts // 60), []).append(price)
    return [{"ts": m * 60.0, "average": sum(p) / len(p), "count": len(p)} for m, p in sorted(by_min.items())]


def _pages(name: str, trades: list, t0: float) -> tuple[list[Row], float, bool] | None:
    """What the backfill reads before ``t0``: its trades, how far back they reach, and whether that is all of it."""
    if name == "none":
        return None
    start = t0 - REPLAY_SEC
    if name == "bars":
        return minute_rows(_minute_bars(trades, start, t0), start, t0, t0), start, True
    if name.startswith("hybrid_"):
        rows, since, complete = _pages("replay_" + name.split("_")[1], trades, t0) or ([], t0, True)
        if complete or not rows:
            return rows, since, complete
        return minute_rows(_minute_bars(trades, start, t0), start, since, t0) + rows, start, False
    back = REPLAY_SEC if name.startswith("replay_") else TICKS_SEC
    ts = [r[0] for r in trades]
    rows = [(r[0], r[1], r[2], r[3], r[4]) for r in trades[bisect.bisect_right(ts, t0 - back):bisect.bisect_left(ts, t0)]]
    cap = name.split("_")[1]
    if cap == "all" or len(rows) <= int(cap):
        return rows, t0 - back, True
    rows = rows[-int(cap):]
    return rows, rows[0][0], False


def _band_at(name: str, symbol: str, trades: list, events: list, t0: float, at: float, facts: Facts) -> dict[str, Any]:
    """One variant's tracker, started on the first print at ``t0``, rebuilt ``BACKFILL_DELAY_SEC`` later, read at
    the touch ``at``."""
    land = t0 + BACKFILL_DELAY_SEC
    pages = _pages(name, trades, t0)
    tr = Tracker(symbol, started_at=t0, facts=facts, options=VARIANTS[APPROX_VARIANT],
                 journal=0 if pages is None else 10**7)
    for ts, kind, item in events:
        if pages is not None and ts >= land:
            tr, pages = tr.rebuilt(land, pages[0], since=pages[1], complete=pages[2]) or tr, None
        if kind == 0:
            tr.on_print(ts, item[1], eligible=item[2], conditions=item[3], exchange=item[4])
        else:
            tr.on_quote(ts, item[1], item[2])
    if pages is not None and at >= land:
        tr = tr.rebuilt(land, pages[0], since=pages[1], complete=pages[2]) or tr
    return tr.view(at)


def evaluate(symbol: str, day: str, trades: list, quotes: list, touches: list[dict[str, Any]], *,
             prev_close: float | None, tier: int = 2, names: list[str] | None = None) -> list[dict[str, Any]]:
    """One row per (touch, lead): each variant's band at the touch beside the SIP's."""
    open_ts, close_ts = _ts_at(day, "09:30:00"), _ts_at(day, "16:00:00")
    t_ts = [r[0] for r in trades]
    q_ts = [q[0] for q in quotes]
    rows = []
    for touch in touches:
        at, side, sip = touch["ts"], touch["side"], touch["sip"]
        for lead in LEADS:
            first = bisect.bisect_left(t_ts, at - lead)
            if first >= len(trades) or trades[first][0] >= at:
                continue
            t0 = trades[first][0]                       # the first print Nova hears
            if not (open_ts < t0 < close_ts):
                continue
            events = [(r[0], 0, r) for r in trades[first:bisect.bisect_right(t_ts, at)]]
            events += [(q[0], 1, q) for q in quotes[bisect.bisect_left(q_ts, t0):bisect.bisect_right(q_ts, at)]]
            events.sort(key=lambda e: (e[0], e[1]))
            row = {"symbol": symbol, "day": day, "ts": at, "et": et(at), "side": side, "sip": sip, "lead": lead,
                   "start_et": et(t0), "exact_tracker": touch.get(APPROX_VARIANT)}
            for name in names or variants():
                v = _band_at(name, symbol, trades, events, t0, at, Facts(prev_close=prev_close, tier=tier))
                row[name] = v[side]
                row[name + "_spread"] = v["spread"]
                row[name + "_complete"] = (v.get("backfill") or {}).get("complete")
            rows.append(row)
    return rows


def _score(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    have = [r for r in rows if r.get(name) is not None]
    diffs = sorted(round(abs(r[name] - r["sip"]) * 100) for r in have)
    rel = sorted(abs(r[name] - r["sip"]) / r["sip"] for r in have if r["sip"])
    n = len(diffs)
    return {
        "band": n,
        "exact": sum(d == 0 for d in diffs),
        "within_1c": sum(d <= 1 for d in diffs),
        "inside_spread": sum(1 for r in have if r.get(name + "_spread") is not None
                             and abs(r[name] - r["sip"]) <= r[name + "_spread"] + 1e-9),
        "median_pct": round(100 * rel[n // 2], 2) if n else None,
        "p90_pct": round(100 * rel[int(n * 0.9)], 2) if n else None,
        "short": sum(1 for r in have if r.get(name + "_complete") is False),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per variant, over the touches where today's tracker had no band yet (what a backfill adds): touches with a
    band, to the cent, within a cent, inside the stated spread, the error's median and 90th percentile, and how
    many read fewer than ten minutes of trades. Per lead, and all leads together."""
    added = [r for r in rows if "none" in r and r["none"] is None]
    names = [v for v in variants() if v != "none" and any(v in r for r in rows)]
    out: dict[str, Any] = {"rows": len(rows), "added": len(added), "all_leads": {}, "leads": {}}
    for name in names:
        out["all_leads"][name] = _score(added, name)
    for lead in LEADS:
        mine = [r for r in added if r["lead"] == lead]
        out["leads"][str(lead)] = {"touches": len(mine), **{name: _score(mine, name) for name in names}}
    return out
