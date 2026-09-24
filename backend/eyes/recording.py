"""A Session Record as the eyes read it (ADR 029).

One recorded symbol-day: every usable print (the tape gate reads them all), the
price the detectors follow (per second, only prints that set a price --
``sale_conditions``), the recorded Level 2 books, the day's one-minute bars and
the stretches the recorder was up. Loaded read-only with the capture reader's
own validation; the capture player's loaded state is never touched.

Bars come from the bar archive (``bars_store``: the bars the live eyes saw that
day, 04:00 on), else the recording's own one-minute bars -- ``bars_source``
says which. Pillars at a moment come from the scanner leaderboard's row for the
symbol at or before it (ADR 023, point in time) and the catalyst verdict at it
(ADR 024); what neither holds stays ``None`` -- unknown, never failed.
"""
from __future__ import annotations

import bisect
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from constants_eyes import EYES_REPLAY_BOOK_SAMPLE_SEC, EYES_REPLAY_PRICE_STEP_SEC
from setup_scanner.bars import Bar, bar_from

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
SESSION_HOURS = 16


def day_start_ts(date: str) -> float:
    d = datetime.strptime(date, "%Y-%m-%d").date()
    return datetime.combine(d, dtime(4, 0), ET).timestamp()


@dataclass
class Recording:
    date: str
    symbol: str
    prints: list[dict]
    print_ts: list[float]
    ticks: list[tuple[float, float, float]]          # (second end, high, last) of price-setting prints
    books: list[tuple[float, dict]]                  # sampled at EYES_REPLAY_BOOK_SAMPLE_SEC
    book_ts: list[float]
    bars: list[Bar]
    bars_source: str                                 # "archive" | "recording" | "none"
    spans: list[tuple[float, float]]
    prev_close: float | None
    diagnostics: dict = field(default_factory=dict)

    @property
    def first_ts(self) -> float | None:
        return self.print_ts[0] if self.print_ts else (self.book_ts[0] if self.book_ts else None)

    @property
    def last_ts(self) -> float | None:
        return self.print_ts[-1] if self.print_ts else (self.book_ts[-1] if self.book_ts else None)

    def prints_between(self, start: float, end: float) -> list[dict]:
        lo, hi = bisect.bisect_left(self.print_ts, start), bisect.bisect_right(self.print_ts, end)
        return self.prints[lo:hi]

    def books_between(self, start: float, end: float) -> list[tuple[float, dict]]:
        lo, hi = bisect.bisect_left(self.book_ts, start), bisect.bisect_right(self.book_ts, end)
        return self.books[lo:hi]

    def recorded_at(self, ts: float) -> bool:
        if not self.spans:
            return self.first_ts is not None and self.first_ts <= ts <= (self.last_ts or ts)
        return any(a <= ts <= b for a, b in self.spans)

    def summary(self) -> dict[str, Any]:
        return {"date": self.date, "symbol": self.symbol, "prints": len(self.prints), "books": len(self.books),
                "bars": len(self.bars), "bars_source": self.bars_source, "spans": [list(s) for s in self.spans],
                "first_ts": self.first_ts, "last_ts": self.last_ts, "prev_close": self.prev_close}


def _ticks(prints: list[dict], step: float) -> list[tuple[float, float, float]]:
    """Per ``step`` seconds: the high and the last of the prints that set a price."""
    from sale_conditions import row_sets_price

    out: list[tuple[float, float, float]] = []
    bucket, hi, last = None, 0.0, 0.0
    for row in prints:
        if not row_sets_price(row):
            continue
        px = float(row["price"])
        b = math.floor(float(row["ts"]) / step)
        if b != bucket:
            if bucket is not None:
                out.append(((bucket + 1) * step, hi, last))
            bucket, hi = b, px
        hi, last = max(hi, px), px
    if bucket is not None:
        out.append(((bucket + 1) * step, hi, last))
    return out


def _sample_books(rows: list[dict], step: float) -> list[tuple[float, dict]]:
    """The last book in each ``step`` -- the cadence the live tape feed samples at."""
    out: list[tuple[float, dict]] = []
    bucket = None
    for row in rows:
        b = math.floor(float(row["ts"]) / step)
        book = {"bids": row.get("bids") or [], "asks": row.get("asks") or []}
        if b == bucket and out:
            out[-1] = (float(row["ts"]), book)
        else:
            out.append((float(row["ts"]), book))
            bucket = b
    return out


def archive_bars(symbol: str, date: str) -> list[Bar]:
    import bars_store

    start = day_start_ts(date)
    res = bars_store.read(symbol, "1Min", SESSION_HOURS * 60, from_ts=start, through_ts=start + SESSION_HOURS * 3600 - 1)
    return [b for b in (bar_from(r) for r in (res or {}).get("bars") or []) if b is not None]


def _recording_bars(rows: list[dict]) -> list[Bar]:
    out = []
    for r in rows:
        bar = bar_from({"t": r.get("ts"), "o": r.get("open", r.get("o")), "h": r.get("high", r.get("h")),
                        "l": r.get("low", r.get("l")), "c": r.get("close", r.get("c")),
                        "v": r.get("volume", r.get("v"))})
        if bar is not None:
            out.append(bar)
    return sorted(out, key=lambda b: b.t)


def load(date: str, symbol: str, *, root: Path | None = None,
         bars_fn: Callable[[str, str], list[Bar]] = archive_bars) -> Recording:
    """Read one Session Record. Raises ``ValueError`` with the reason when it is not usable."""
    from capture.recorder import capture_root
    from capture.schema import read_manifest
    from capture.sessions import is_ibkr_source
    from sim.capture_reader import new_diagnostics, read_jsonl, usable_rows
    from sim.capture_spans import load_spans, previous_close_for, recording_here

    sym = symbol.upper()
    folder = (root or capture_root()) / date / sym
    if not folder.is_dir():
        raise ValueError(f"no Session Record for {sym} on {date}")
    diagnostics = new_diagnostics()
    manifest, _legacy = read_manifest(folder)
    if not is_ibkr_source(manifest):
        raise ValueError(f"{sym} {date} is not an IBKR recording")

    def read(name: str, kind: str) -> list[dict]:
        return usable_rows(read_jsonl(folder / f"{name}.jsonl", diagnostics), kind, sym, diagnostics)

    prints = read("prints", "prints")
    l2 = read("l2", "l2")
    if not prints:
        raise ValueError(f"{sym} {date} holds no usable prints")
    print_ts = [float(r["ts"]) for r in prints]
    books = _sample_books(l2, EYES_REPLAY_BOOK_SAMPLE_SEC)
    try:
        bars, bars_source = bars_fn(sym, date), "archive"
    except Exception:
        logger.warning("eyes: archive bars unread for %s %s", sym, date, exc_info=True)
        bars, bars_source = [], "archive"
    if not bars:
        bars, bars_source = _recording_bars(read("bars_1m", "bars")), "recording"
    if not bars:
        bars_source = "none"
    _segments, spans = load_spans(manifest, folder, live=recording_here(folder),
                                  first_ts=min(print_ts), last_ts=max(print_ts))
    return Recording(date=date, symbol=sym, prints=prints, print_ts=print_ts,
                     ticks=_ticks(prints, EYES_REPLAY_PRICE_STEP_SEC), books=books,
                     book_ts=[t for t, _ in books], bars=bars, bars_source=bars_source,
                     spans=[(float(a), float(b)) for a, b in spans],
                     prev_close=previous_close_for(sym, date), diagnostics=diagnostics)


def usable_sessions() -> list[tuple[str, str]]:
    """``(date, symbol)`` of every usable Session Record with prints, oldest day first."""
    from capture.sessions import list_sessions

    out = []
    for day, rows in list_sessions().get("tickers_by_day", {}).items():
        out += [(day, r["symbol"]) for r in rows if r.get("usable") and int(r.get("prints") or 0) != 0]
    return sorted(out)


def pillars_at(symbol: str, date: str, ts: float, *, last_price: float | None, prev_close: float | None) -> dict:
    """The Five Pillars as the eyes could have read them at ``ts`` (point in time)."""
    row = None
    try:
        from leaderboard import store as lb_store

        with lb_store.connect() as db:
            hit = db.execute(
                "SELECT price, change_pct, rvol, float_shares, source FROM rows WHERE session_date = ? AND symbol = ?"
                " AND minute_ts <= ? ORDER BY minute_ts DESC, CASE source WHEN 'recorded' THEN 0 ELSE 1 END LIMIT 1",
                (date, symbol.upper(), int(ts))).fetchone()
            row = dict(hit) if hit else None
    except Exception:
        logger.debug("eyes: leaderboard unread for %s %s", symbol, date, exc_info=True)
    price = last_price if last_price is not None else (row or {}).get("price")
    change = None
    if row and row.get("change_pct") is not None:
        change = float(row["change_pct"]) * 100.0
    elif price is not None and prev_close:
        change = (float(price) / float(prev_close) - 1.0) * 100.0
    catalyst = None
    try:
        from catalysts import live as catalyst_live

        catalyst = catalyst_live.verdict_for(symbol, ts)
    except Exception:
        logger.debug("eyes: catalyst verdict unread for %s at %s", symbol, ts, exc_info=True)
    from setup_scanner.grade import news_pillar

    compact = None
    if catalyst is not None:
        from catalysts import live as catalyst_live

        compact = catalyst_live.compact(catalyst)
    return {"price": price, "change_pct": change, "rvol": (row or {}).get("rvol"),
            "float": (row or {}).get("float_shares"), "news": news_pillar(catalyst),
            "headline": (catalyst or {}).get("title"), "catalyst": compact,
            "source": "leaderboard" if row else "recording"}
