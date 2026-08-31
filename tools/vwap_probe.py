#!/usr/bin/env python3
"""Live trail for Nova chart session VWAP.

Fetches store-first ``/api/ticker/{symbol}/bars`` and reprints the same
questions a human asks when the orange line looks wrong:

  * What is daytime VWAP (04:00-16:00 ET)?
  * What is after-hours VWAP (16:00-20:00 ET) -- the line after the cash close?
  * What would RTH-only VWAP (09:30-16:00 ET) be?
  * Does yesterday leftover sit next to today's 04:00? LineSeries would
    draw a diagonal through that hole.

This is a soak tool, not a CI gate. The paint contract lives in
``frontend/src/chart/vwapSession.ts`` (vitest).

Usage (API up):

  py -3 tools/vwap_probe.py AEMD
  py -3 tools/vwap_probe.py AEMD --timeframe 1Min --limit 1000 --json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
RTH_START = 9 * 3600 + 30 * 60
RTH_END = 16 * 3600
EXT_START = 4 * 3600
AH_END = 20 * 3600
DEFAULT_URL = "http://127.0.0.1:8000"


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET)


def _sod(dt: datetime) -> int:
    return dt.hour * 3600 + dt.minute * 60 + dt.second


def session_vwap(bars: list[dict], start_sec: int, end_sec: int) -> list[dict]:
    """Mirror of ``sessionVwapPoints`` -- hlc3 * volume, reset each ET day."""
    out: list[dict] = []
    cum_pv = 0.0
    cum_v = 0.0
    value: float | None = None
    day = None
    for bar in bars:
        dt = _parse(str(bar["t"]))
        key = dt.date()
        if key != day:
            cum_pv = 0.0
            cum_v = 0.0
            value = None
            day = key
        second = _sod(dt)
        if second < start_sec:
            continue
        if second < end_sec:
            volume = float(bar.get("v") or 0)
            if volume > 0:
                hlc3 = (float(bar["h"]) + float(bar["l"]) + float(bar["c"])) / 3.0
                cum_pv += hlc3 * volume
                cum_v += volume
        if cum_v > 0:
            value = cum_pv / cum_v
            out.append(
                {
                    "t": dt.isoformat(sep=" "),
                    "value": value,
                    "close": float(bar["c"]),
                    "volume": float(bar.get("v") or 0),
                    "day": key.isoformat(),
                    "sod": second,
                }
            )
    return out


def segmented_session_vwap(bars: list[dict]) -> list[dict]:
    """Mirror of ``sessionVwapPoints`` after D-007: 04:00-16:00, reset, 16:00-20:00."""
    out: list[dict] = []
    cum_pv = 0.0
    cum_v = 0.0
    value: float | None = None
    day = None
    in_after_hours = False
    for bar in bars:
        dt = _parse(str(bar["t"]))
        key = dt.date()
        if key != day:
            cum_pv = 0.0
            cum_v = 0.0
            value = None
            day = key
            in_after_hours = False
        second = _sod(dt)
        if second < EXT_START:
            continue
        after_cash = second >= RTH_END
        if after_cash and not in_after_hours:
            cum_pv = 0.0
            cum_v = 0.0
            value = None
            in_after_hours = True
        accumulating = second < AH_END if after_cash else True
        if accumulating:
            volume = float(bar.get("v") or 0)
            if volume > 0:
                hlc3 = (float(bar["h"]) + float(bar["l"]) + float(bar["c"])) / 3.0
                cum_pv += hlc3 * volume
                cum_v += volume
        if cum_v > 0:
            value = cum_pv / cum_v
            out.append(
                {
                    "t": dt.isoformat(sep=" "),
                    "value": value,
                    "close": float(bar["c"]),
                    "volume": float(bar.get("v") or 0),
                    "day": key.isoformat(),
                    "sod": second,
                }
            )
    return out


def interpolation_pair(points: list[dict]) -> dict | None:
    """Last leftover of the prior ET day vs first point of the newest day."""
    if len(points) < 2:
        return None
    last_day = points[-1]["day"]
    today = [p for p in points if p["day"] == last_day]
    prior = [p for p in points if p["day"] != last_day]
    if not today or not prior:
        return None
    left = prior[-1]
    right = today[0]
    left_dt = datetime.fromisoformat(left["t"])
    right_dt = datetime.fromisoformat(right["t"])
    gap_min = (right_dt - left_dt).total_seconds() / 60.0
    return {
        "prior": left,
        "today": right,
        "gap_min": gap_min,
        "would_interpolate": gap_min > 1.5,
    }


def paint_latest_day(points: list[dict], pane_day: str) -> list[dict]:
    """Mirror of the pane rule: only the newest ET day is drawn."""
    return [p for p in points if p["day"] == pane_day and p["sod"] >= EXT_START]


def fetch_bars(base: str, symbol: str, timeframe: str, limit: int) -> dict:
    url = f"{base.rstrip('/')}/api/ticker/{symbol}/bars?timeframe={timeframe}&limit={limit}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def report(payload: dict) -> dict:
    bars = list(payload.get("bars") or [])
    if not bars:
        return {"error": "no bars", "symbol": payload.get("symbol")}

    first = _parse(str(bars[0]["t"]))
    last = _parse(str(bars[-1]["t"]))
    pane_day = last.date().isoformat()
    rth = session_vwap(bars, RTH_START, RTH_END)
    daytime = session_vwap(bars, EXT_START, RTH_END)
    ah = session_vwap(bars, RTH_END, AH_END)
    painted = paint_latest_day(segmented_session_vwap(bars), pane_day)
    pair = interpolation_pair(daytime)

    today_bars = [b for b in bars if _parse(str(b["t"])).date().isoformat() == pane_day]
    premarket = [b for b in today_bars if _sod(_parse(str(b["t"]))) < RTH_START]
    rth_today = [
        b
        for b in today_bars
        if RTH_START <= _sod(_parse(str(b["t"]))) < RTH_END
    ]
    ah_today = [
        b
        for b in today_bars
        if RTH_END <= _sod(_parse(str(b["t"]))) < AH_END
    ]
    premarket_vol = sum(float(b.get("v") or 0) for b in premarket)
    rth_vol = sum(float(b.get("v") or 0) for b in rth_today)
    ah_vol = sum(float(b.get("v") or 0) for b in ah_today)

    rth_today_pts = [p for p in rth if p["day"] == pane_day and p["sod"] < RTH_END]
    daytime_today = [p for p in daytime if p["day"] == pane_day and p["sod"] < RTH_END]
    ah_today_pts = [p for p in ah if p["day"] == pane_day]

    return {
        "symbol": payload.get("symbol"),
        "timeframe": payload.get("timeframe"),
        "source": payload.get("source"),
        "bar_count": len(bars),
        "window_et": {"first": first.strftime("%Y-%m-%d %H:%M"), "last": last.strftime("%Y-%m-%d %H:%M")},
        "rth": {
            "points": len(rth_today_pts),
            "last": rth_today_pts[-1] if rth_today_pts else None,
        },
        "daytime": {
            "points": len(daytime_today),
            "last": daytime_today[-1] if daytime_today else None,
        },
        "afterhours": {
            "points": len(ah_today_pts),
            "last": ah_today_pts[-1] if ah_today_pts else None,
        },
        "today": {
            "premarket_bars": len(premarket),
            "premarket_volume": premarket_vol,
            "rth_bars": len(rth_today),
            "rth_volume": rth_vol,
            "ah_bars": len(ah_today),
            "ah_volume": ah_vol,
        },
        "interpolation_pair": pair,
        "paint_latest_day": {
            "points": len(painted),
            "first": painted[0] if painted else None,
            "last": painted[-1] if painted else None,
        },
        "how_to_read": (
            "Paint is segmented: 04:00-16:00 daytime, reset at 16:00, "
            "16:00-20:00 after-hours. RTH 09:30 is the cash-session what-if. "
            "would_interpolate=YES means leftover sits next to today's 04:00 "
            "with a hole -- LineSeries would draw a diagonal. "
            "paint_latest_day last is the axis tag (AH after 16:00)."
        ),
    }


def _fmt_point(point: dict | None) -> str:
    if not point:
        return "(none)"
    return f"{point['t']}  ${point['value']:.4f}  close=${point['close']:.4f}  vol={point['volume']:.0f}"


def print_text(rep: dict) -> None:
    if rep.get("error"):
        print(f"ERROR: {rep['error']}")
        return
    print(f"{rep['symbol']}  {rep['timeframe']}  bars={rep['bar_count']}  source={rep['source']}")
    print(f"window ET  {rep['window_et']['first']}  ..  {rep['window_et']['last']}")
    print()
    print("DAY 04:00-16:00  (orange on RTH/premarket bars)")
    print(f"  points={rep['daytime']['points']}  last  {_fmt_point(rep['daytime']['last'])}")
    print("AH  16:00-20:00  (orange after the cash close)")
    print(f"  points={rep['afterhours']['points']}  last  {_fmt_point(rep['afterhours']['last'])}")
    print("RTH 09:30-16:00  (what-if)")
    print(f"  points={rep['rth']['points']}  last  {_fmt_point(rep['rth']['last'])}")
    today = rep["today"]
    print()
    print(f"today premarket  bars={today['premarket_bars']}  vol={today['premarket_volume']:.0f}")
    print(f"today RTH        bars={today['rth_bars']}  vol={today['rth_volume']:.0f}")
    print(f"today afterhours bars={today['ah_bars']}  vol={today['ah_volume']:.0f}")
    pair = rep.get("interpolation_pair")
    print()
    if pair:
        flag = "YES -- old LineSeries draws a diagonal through this hole" if pair["would_interpolate"] else "no"
        print("overnight pair (old paint)")
        print(f"  leftover  {_fmt_point(pair['prior'])}")
        print(f"  open      {_fmt_point(pair['today'])}")
        print(f"  gap_min={pair['gap_min']:.1f}  would_interpolate={flag}")
    else:
        print("overnight pair  (none -- one session only)")
    paint = rep["paint_latest_day"]
    print()
    print("paint latest ET day (segmented 04:00 / 16:00)")
    print(f"  points={paint['points']}")
    print(f"  first  {_fmt_point(paint['first'])}")
    print(f"  last   {_fmt_point(paint['last'])}")
    print()
    print(rep["how_to_read"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Soak / trail for chart session VWAP")
    parser.add_argument("symbol", help="Ticker, e.g. AEMD")
    parser.add_argument("--timeframe", default="1Min")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--base", default=DEFAULT_URL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    symbol = args.symbol.strip().upper()
    try:
        payload = fetch_bars(args.base, symbol, args.timeframe, args.limit)
    except urllib.error.URLError as exc:
        print(f"ABORT: cannot reach {args.base} ({exc})", file=sys.stderr)
        return 2

    payload.setdefault("symbol", symbol)
    payload.setdefault("timeframe", args.timeframe)
    rep = report(payload)
    if args.json:
        print(json.dumps(rep, indent=2, default=str))
    else:
        print_text(rep)
    return 0 if not rep.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
