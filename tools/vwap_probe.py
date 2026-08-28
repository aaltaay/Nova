#!/usr/bin/env python3
"""Live trail for Nova chart session VWAP.

Fetches store-first ``/api/ticker/{symbol}/bars`` and reprints the same
questions a human asks when the orange line looks wrong:

  * What is session VWAP (04:00-16:00 ET) -- what the chart paints?
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
    ext = session_vwap(bars, EXT_START, RTH_END)
    painted = paint_latest_day(ext, pane_day)
    pair = interpolation_pair(ext)

    today_bars = [b for b in bars if _parse(str(b["t"])).date().isoformat() == pane_day]
    premarket = [b for b in today_bars if _sod(_parse(str(b["t"]))) < RTH_START]
    rth_today = [
        b
        for b in today_bars
        if RTH_START <= _sod(_parse(str(b["t"]))) < RTH_END
    ]
    premarket_vol = sum(float(b.get("v") or 0) for b in premarket)
    rth_vol = sum(float(b.get("v") or 0) for b in rth_today)

    return {
        "symbol": payload.get("symbol"),
        "timeframe": payload.get("timeframe"),
        "source": payload.get("source"),
        "bar_count": len(bars),
        "window_et": {"first": first.strftime("%Y-%m-%d %H:%M"), "last": last.strftime("%Y-%m-%d %H:%M")},
        "rth": {
            "points": len(rth),
            "last": rth[-1] if rth else None,
        },
        "extended": {
            "points": len(ext),
            "last": ext[-1] if ext else None,
        },
        "today": {
            "premarket_bars": len(premarket),
            "premarket_volume": premarket_vol,
            "rth_bars": len(rth_today),
            "rth_volume": rth_vol,
        },
        "interpolation_pair": pair,
        "paint_latest_day": {
            "points": len(painted),
            "first": painted[0] if painted else None,
            "last": painted[-1] if painted else None,
        },
        "how_to_read": (
            "Extended 04:00-16:00 is what the chart paints. RTH 09:30 is the "
            "what-if. would_interpolate=YES means leftover sits next to "
            "today's 04:00 with a hole -- LineSeries would draw a diagonal. "
            "paint_latest_day is the line on the newest ET day only."
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
    print("EXT 04:00-16:00  (chart paints this)")
    print(f"  points={rep['extended']['points']}  last  {_fmt_point(rep['extended']['last'])}")
    print("RTH 09:30-16:00  (what-if)")
    print(f"  points={rep['rth']['points']}  last  {_fmt_point(rep['rth']['last'])}")
    today = rep["today"]
    print()
    print(f"today premarket  bars={today['premarket_bars']}  vol={today['premarket_volume']:.0f}")
    print(f"today RTH        bars={today['rth_bars']}  vol={today['rth_volume']:.0f}")
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
    print("paint latest ET day (new rule)")
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
