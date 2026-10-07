"""How close Nova's LULD bands come to the exchanges' (ADR 047): ``tools/luld_check.py``.

Read-only. Two sources of truth:

- **The SIP's own flags (Massive).** Every NBBO row in the Massive quotes files carries the
  SIP's LULD indicator. 5 is the NBB equal to the upper band, 6 the NBO equal to the lower band,
  7 / 8 the same with the other side outside the band, and 9 both. A row with one of them
  gives the band's exact price at that moment. The study replays each ticker-day's trades and
  NBBO through ``Tracker`` (which never sees the indicators) and compares, once per touch:
  a run of rows with the same side and price is one touch.
- **Nova's own recordings.** Session Records carry IBKR's tape and book, the data the live
  desk has. They have no indicators, so the truth there is the price the NBBO sat at for the
  15 s before a logged LULD pause.

Each tracker variant (``Options``) runs on the same events, so the study also measures what
the Plan leaves to the processors. ``approx`` trackers start mid-session (``APPROX_START_MIN``
after the open) to measure the seeded, approximate band.

Results are rows of plain dicts. ``summarize`` turns them into the track record the desk quotes
(``constants_luld.LULD_TRACK_RECORD``).
"""
from __future__ import annotations

import bisect
import csv
import json
import logging
import os
import threading
import zlib
from collections import Counter
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from luld.tracker import Facts, Options, Tracker

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

# Massive (Polygon) trade condition ids: Market Center Opening / Reopening Trade.
MASSIVE_OPEN_CODES = frozenset({17})
MASSIVE_REOPEN_CODES = frozenset({18})
# NBBO LULD indicators that put a price on a band: (upper from the bid, lower from the ask).
INDICATOR_BANDS = {5: (True, False), 6: (False, True), 7: (True, False), 8: (False, True), 9: (True, True)}
VARIANTS: dict[str, Options] = {
    "plan_literal": Options(exit_updates_reference=True, exit_resets_clock=True),
    "exit_keep_clock": Options(exit_updates_reference=True, exit_resets_clock=False),
    "no_exit": Options(exit_updates_reference=False),
    "no_exit_r2": Options(exit_updates_reference=False, reference_digits=2),
    "no_exit_r4": Options(exit_updates_reference=False, reference_digits=4),
    "no_exit_trades": Options(exit_updates_reference=False, reference_on="trades"),
    "exit_trades": Options(exit_updates_reference=True, exit_resets_clock=False, reference_on="trades"),
}
# The variant the approximate tracker runs (the desk's).
APPROX_VARIANT = "no_exit"
APPROX_START_MIN = 30
# The SIP flags a band on every NBBO row while it sits there: one touch per side and price,
# until that price has not been flagged for this long.
TOUCH_GAP_SEC = 60.0
READ_CHUNK = 16 * 2**20


def et(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S")


def _ts_at(day: str, hhmm: str) -> float:
    return datetime.fromisoformat(f"{day}T{hhmm}").replace(tzinfo=ET).timestamp()


# -- reading several tickers of one Massive file in one pass ----------------------------------------
def ticker_blocks(path: Path, tickers: list[str]) -> Iterator[tuple[str, list[str], list[bytes]]]:
    """``(ticker, header, lines)`` stretches for each wanted ticker, in one pass over a file sorted by
    ticker. Like ``sim.massive_files.ticker_batches`` for one ticker, but it moves on to the next
    wanted ticker instead of stopping. A ticker the file does not hold yields nothing."""
    wanted = sorted({t.strip().upper() for t in tickers if t})
    keys = [w.encode() + b"," for w in wanted]
    ki = 0
    decomp = zlib.decompressobj(31)
    header: list[str] | None = None
    tail = b""
    in_block = False
    with open(path, "rb") as fh:
        while ki < len(keys):
            chunk = fh.read(READ_CHUNK)
            if not chunk:
                break
            data = tail + decomp.decompress(chunk)
            while decomp.eof and decomp.unused_data:     # a multi-member file: the next member starts fresh
                rest = decomp.unused_data
                decomp = zlib.decompressobj(31)
                data += decomp.decompress(rest)
            if header is None:
                nl = data.find(b"\n")
                if nl < 0:
                    tail = data
                    continue
                header = data[:nl].decode("utf-8").strip().split(",")
                data = data[nl + 1:]
            end = data.rfind(b"\n")
            if end < 0:
                tail = data
                continue
            body, tail = data[:end], data[end + 1:]
            pos = 0
            while ki < len(keys) and pos < len(body):
                key = keys[ki]
                if not in_block:
                    if body.startswith(key, pos):
                        start = pos
                    else:
                        at = body.find(b"\n" + key, pos)
                        if at < 0:
                            last = body[body.rfind(b"\n") + 1:]
                            if last[:last.find(b",")] > key[:-1]:
                                ki += 1          # sorted, and past it: the file does not hold it
                                continue
                            break                # not reached yet: read on
                        start = at + 1
                    in_block, pos = True, start
                lines: list[bytes] = []
                cursor, finished = pos, False
                while cursor < len(body):
                    line_end = body.find(b"\n", cursor)
                    line = body[cursor:] if line_end < 0 else body[cursor:line_end]
                    if not line.startswith(key):
                        finished = True
                        break
                    lines.append(line)
                    cursor = len(body) if line_end < 0 else line_end + 1
                if lines:
                    yield wanted[ki], header, lines
                pos = cursor
                if finished:
                    in_block = False
                    ki += 1
    if ki < len(keys) and tail.startswith(keys[ki]):
        yield wanted[ki], header or [], [tail.rstrip(b"\r")]   # the file's last line, with no newline


def read_massive_day(day: str, tickers: list[str]) -> dict[str, dict[str, list]]:
    """Each ticker's trades and NBBO rows for one day, the two files read side by side."""
    from sim import massive_files as mf

    out: dict[str, dict[str, list]] = {t: {"trades": [], "quotes": []} for t in tickers}
    errors: list[BaseException] = []

    def trades() -> None:
        path = mf.day_file("trades_v1", day)
        if path is None:
            raise FileNotFoundError(f"no trades file for {day}")
        for ticker, header, lines in ticker_blocks(path, tickers):
            rows = out[ticker]["trades"]
            for fields in csv.reader(line.decode("utf-8") for line in lines):
                row = dict(zip(header, fields, strict=True))
                corr = int(row.get("correction") or 0)
                if corr in (10, 11):
                    continue
                codes = mf.condition_codes(row.get("conditions"))
                ex = int(row.get("exchange") or 0)
                rows.append((int(row["sip_timestamp"]) / 1e9, float(row["price"]),
                             mf.sets_price(row.get("conditions"), corr),
                             ("O" if codes & MASSIVE_OPEN_CODES else "") + ("5" if codes & MASSIVE_REOPEN_CODES else ""),
                             "FINRA" if ex == 4 else str(ex)))

    def quotes() -> None:
        path = mf.day_file("quotes_v1", day)
        if path is None:
            raise FileNotFoundError(f"no quotes file for {day}")
        for ticker, header, lines in ticker_blocks(path, tickers):
            rows = out[ticker]["quotes"]
            for fields in csv.reader(line.decode("utf-8") for line in lines):
                row = dict(zip(header, fields, strict=True))
                ind = row.get("indicators") or ""
                rows.append((int(row["sip_timestamp"]) / 1e9, float(row["bid_price"] or 0) or None,
                             float(row["ask_price"] or 0) or None,
                             int(ind) if ind.isdigit() else 0, row.get("conditions") or ""))

    def run(fn) -> None:
        try:
            fn()
        except BaseException as exc:  # re-raised on the calling thread
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(fn,), daemon=True) for fn in (trades, quotes)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    if errors:
        raise errors[0]
    for data in out.values():
        data["trades"].sort(key=lambda r: r[0])
        data["quotes"].sort(key=lambda r: r[0])
    return out


def massive_prev_close(day: str, tickers: list[str]) -> dict[str, float]:
    """The previous trading day's close from the Massive day aggregates (a small file)."""
    from sim import massive_files as mf

    base = mf.root() / "day_aggs_v1"
    files = sorted(p for p in base.glob("*/*/*.csv.gz") if p.name[:10] < day)
    if not files:
        return {}
    import gzip

    want = set(tickers)
    out: dict[str, float] = {}
    with gzip.open(files[-1], "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("ticker") in want:
                try:
                    out[row["ticker"]] = float(row["close"])
                except (KeyError, ValueError):
                    continue
    return out


# -- one ticker-day ---------------------------------------------------------------------------------
def _trackers(symbol: str, start: float, prev_close: float | None, tier: int) -> dict[str, Tracker]:
    facts = Facts(prev_close=prev_close, tier=tier)
    return {name: Tracker(symbol, started_at=start, facts=facts, options=opt) for name, opt in VARIANTS.items()}


def evaluate(symbol: str, day: str, trades: list, quotes: list, *, prev_close: float | None,
             pauses: list[float] | None = None, tier: int = 2) -> dict[str, Any]:
    """Replay one ticker-day and compare every band touch the SIP flagged (and each logged pause)."""
    open_ts = _ts_at(day, "09:30:00")
    close_ts = _ts_at(day, "16:00:00")
    start = min([open_ts - 3600] + [r[0] for r in trades[:1]] + [q[0] for q in quotes[:1]])
    # The day aggregates' close is not split-adjusted; the SIP's is. A first regular-hours trade far
    # from it is a split (or a bad close): the band's size is unknown, so the day is set apart.
    first = next((r[1] for r in trades if r[0] >= open_ts and r[2]), None)
    suspect = bool(prev_close and first and not (0.4 <= first / prev_close <= 2.5))
    exact = _trackers(symbol, start, prev_close, tier)
    approx_start = open_ts + APPROX_START_MIN * 60
    approx = Tracker(symbol, started_at=approx_start, facts=Facts(prev_close=prev_close, tier=tier),
                     options=VARIANTS[APPROX_VARIANT])
    events: list[tuple[float, int, tuple]] = [(r[0], 0, r) for r in trades] + [(q[0], 1, q) for q in quotes]
    events.sort(key=lambda e: (e[0], e[1]))
    touches: list[dict[str, Any]] = []
    last_flag: dict[tuple[str, float], float] = {}
    for ts, kind, item in events:
        live = [*exact.values()] + ([approx] if ts >= approx_start else [])
        if kind == 0:
            _ts, price, eligible, codes, venue = item
            for tr in live:
                tr.on_print(ts, price, eligible=eligible, conditions=codes, exchange=venue)
            continue
        _ts, bid, ask, ind, _cond = item
        for tr in live:
            tr.on_quote(ts, bid, ask)
        if not (open_ts <= ts < close_ts):
            continue
        sides = INDICATOR_BANDS.get(ind)
        if not sides:
            continue
        flagged = []
        if sides[0] and bid:
            flagged.append(("upper", round(bid, 2)))
        if sides[1] and ask:
            flagged.append(("lower", round(ask, 2)))
        for key in flagged:
            seen = last_flag.get(key)
            last_flag[key] = ts
            if seen is not None and ts - seen <= TOUCH_GAP_SEC:
                continue
            side, price = key
            row = {"symbol": symbol, "day": day, "ts": round(ts, 3), "et": et(ts), "side": side, "sip": price,
                   "indicator": ind}
            for name, tr in exact.items():
                v = tr.view(ts)
                row[name] = v[side]
                row[name + "_exact"] = v["exact"]
                row[name + "_source"] = v["reference_source"]
                row[name + "_ref"] = v["reference"]
            if ts >= approx_start:
                v = approx.view(ts)
                row["approx"] = v[side]
                row["approx_exact"] = v["exact"]
                row["approx_spread"] = v["spread"]
            touches.append(row)
    pause_rows = []
    for h in sorted(pauses or []):
        pause_rows.append(_pause_row(symbol, day, h, trades, quotes))
    return {"symbol": symbol, "day": day, "prev_close": prev_close, "prev_close_suspect": suspect,
            "touches": touches, "pauses": pause_rows}


def _pause_row(symbol, day, h, trades, quotes) -> dict[str, Any]:
    """The price the NBBO sat at for the 15 s before a pause, beside the band Nova had then."""
    lo_q = bisect.bisect_left([q[0] for q in quotes], h - 15.0)
    hi_q = bisect.bisect_right([q[0] for q in quotes], h)
    window = [q for q in quotes[lo_q:hi_q] if q[1] and q[2]]
    bids = Counter(round(q[1], 2) for q in window)
    asks = Counter(round(q[2], 2) for q in window)
    return {"symbol": symbol, "day": day, "ts": h, "et": et(h),
            "pinned_bid": bids.most_common(1)[0][0] if bids else None,
            "pinned_ask": asks.most_common(1)[0][0] if asks else None}


# -- summary ----------------------------------------------------------------------------------------
def headline(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The ticker-days the track record counts: a trustworthy previous close (no split), under $50
    (Tier 1 names -- 5% bands -- are rare among stocks that halt, and the study assumes Tier 2)."""
    return [r for r in results if not r.get("prev_close_suspect") and r.get("prev_close") and r["prev_close"] <= 50]


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Per variant: touches where Nova had an exact band, and how many matched to the cent."""
    kept = headline(results)
    touches = [t for r in kept for t in r["touches"]]
    out: dict[str, Any] = {"ticker_days": len(kept), "touches": len(touches), "variants": {},
                           "set_apart": {"ticker_days": len(results) - len(kept),
                                         "touches": sum(len(r["touches"]) for r in results) - len(touches)}}
    for name in [*VARIANTS, "approx"]:
        rows = [t for t in touches if t.get(name) is not None and (name == "approx" or t.get(name + "_exact"))]
        if name == "approx":
            rows = [t for t in touches if t.get("approx") is not None and not t.get("approx_exact")]
        diffs = [round(abs(t[name] - t["sip"]) * 100) for t in rows]
        n = len(diffs)
        out["variants"][name] = {
            "touches": n,
            "exact": sum(d == 0 for d in diffs),
            "within_1c": sum(d <= 1 for d in diffs),
            "within_5c": sum(d <= 5 for d in diffs),
            "median_c": sorted(diffs)[n // 2] if n else None,
            "p90_c": sorted(diffs)[int(n * 0.9)] if n else None,
            "max_c": max(diffs) if diffs else None,
            "pct_exact": round(100 * sum(d == 0 for d in diffs) / n, 1) if n else None,
        }
        if name == "approx":
            rel = [abs(t["approx"] - t["sip"]) / t["sip"] for t in rows if t["sip"]]
            rel.sort()
            out["variants"][name]["median_pct"] = round(100 * rel[len(rel) // 2], 2) if rel else None
            out["variants"][name]["p90_pct"] = round(100 * rel[int(len(rel) * 0.9)], 2) if rel else None
            spreads = [t["approx_spread"] for t in rows if t.get("approx_spread") is not None]
            out["variants"][name]["inside_spread"] = sum(
                1 for t in rows if t.get("approx_spread") is not None and abs(t["approx"] - t["sip"]) <= t["approx_spread"] + 1e-9)
            out["variants"][name]["spread_median"] = sorted(spreads)[len(spreads) // 2] if spreads else None
    out["no_band"] = sum(1 for t in touches if t.get(APPROX_VARIANT) is None)
    return out


def misses(results: list[dict[str, Any]], variant: str) -> list[dict[str, Any]]:
    """The touches where ``variant`` had an exact band that missed the SIP's by a cent or more."""
    out = []
    for r in headline(results):
        for t in r["touches"]:
            v = t.get(variant)
            if v is not None and t.get(variant + "_exact") and round(abs(v - t["sip"]) * 100) > 0:
                out.append({"symbol": r["symbol"], "day": r["day"], "prev_close": r["prev_close"], **t})
    return out


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, path)
