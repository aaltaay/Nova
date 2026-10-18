"""Daily bars out of Massive's day files (``day_aggs_v1``), and the market's day around a session (ADR 059).

A day file is one row per US ticker per session: ``ticker, volume, open, close, high, low, window_start,
transactions``. Its prices are the regular session's official open / high / low / close; its volume is the whole
04:00-20:00 ET session with odd lots, and is fractional (fractional-share prints). Nothing is split-adjusted:
``adjust=True`` multiplies each day's prices by ``splits.factor`` (and divides volume by it), which reads only the
splits of the company that held the ticker that day. As of a day: a row is that session's own file; ``prev_close``
is the close of the symbol's previous session on disk, never a later one. Percents are percent points (1.5 = +1.5%).

Speed, measured on the desk's E: drive (2026-10-18): a day file is ~320 KB of gzip, ~12,500 tickers, with no seek
index. ``sim.massive_files.DayRead`` takes 20-33 ms per file (252 files: 5.6-8.4 s); inflating the whole file takes
4 ms, so a read inflates it and finds the ticker's line (``\\nSYM,``; no reliance on the file's sort order). Cold,
the read is the disk's: a year of one symbol is 3.4-7.2 s one file at a time, 1.8-2.3 s with 4 threads (used), 0.5 s
from the OS cache. An in-process cache keyed on the file's path and mtime keeps the rows already read (0.03 s for the
same year again; bounded; nothing is written to disk).
"""
from __future__ import annotations

import csv
import gzip
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd

from market_reads import REPO, slots  # noqa: F401  (REPO puts backend/ on sys.path)

from constants_sim import SIM_MASSIVE_DAYS
from sim import massive_files

# Three years of one symbol: ~756 files, a few seconds cold. A longer range is a scan (``scan`` / ``movers``).
MAX_SPAN_DAYS = 3 * 366
# How far back the session before ``date_from`` is looked for (a halted or thin stock skips days; holidays too).
PREV_LOOKBACK_DAYS = 31
MAX_CONTEXT_LOOKBACK = 260
CACHE_ENTRIES = 8192         # one small tuple per (file, symbols) read: a few MB at most
READ_WORKERS = 4             # cold year: 4 threads 1.8-2.3 s, one 3.4-7.2 s, 8 threads 1.5 s (measured 2026-10-18)
NUMERIC = ("volume", "open", "close", "high", "low", "transactions")
INDEX_LABELS = {"SPY": "large caps", "QQQ": "the Nasdaq 100", "IWM": "small caps", "DIA": "the Dow"}
FLAT_BAND_PCT = 0.3          # an average move inside +-0.3% is a flat day in the summary
UNITS = ("prices raw dollars unless adjusted; volume shares (fractional: odd lots and fractional shares); "
         "change_pct / gap_pct / range_pct / high_pct in percent points (1.5 = +1.5%)")
VOLUME_NOTE = ("the day bar's volume is the whole 04:00-20:00 ET session with odd lots; its prices are the regular "
               "session's (09:30-16:00)")


def _pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or pd.isna(a) or pd.isna(b) or not b:
        return None
    return (float(a) / float(b) - 1.0) * 100.0


@lru_cache(maxsize=CACHE_ENTRIES)
def _file_rows(path: str, mtime_ns: int, symbols: tuple[str, ...]) -> tuple[tuple[str, dict | None], ...]:
    """Each symbol's row of one day file (``None`` when the file has no row for it). ``mtime_ns`` is the cache key's
    invalidation: a re-downloaded file is read again."""
    with gzip.open(path, "rb") as fh:
        text = fh.read()
    nl = text.find(b"\n")
    header = next(csv.reader([text[:nl].decode("utf-8").strip()]))
    out = []
    for symbol in symbols:
        at = text.find(b"\n" + symbol.encode() + b",")
        if at < 0:
            out.append((symbol, None))
            continue
        end = text.find(b"\n", at + 1)
        line = text[at + 1:end if end >= 0 else len(text)].decode("utf-8").strip()
        fields = next(csv.reader([line]))
        row = dict(zip(header, fields, strict=True))
        values = {k: float(row[k]) if row.get(k) not in (None, "") else None for k in NUMERIC}
        if values["transactions"] is not None:
            values["transactions"] = int(values["transactions"])
        out.append((symbol, values))
    return tuple(out)


def _day_rows(day: str, symbols: tuple[str, ...]) -> dict[str, dict] | None:
    """``{symbol: row}`` for the symbols the day's file holds; ``None`` when there is no file (not a session)."""
    path = massive_files.day_file(SIM_MASSIVE_DAYS, day)
    if path is None:
        return None
    rows = _file_rows(str(path), Path(path).stat().st_mtime_ns, symbols)
    return {s: r for s, r in rows if r is not None}


def clear() -> None:
    _file_rows.cache_clear()


def _days(first: date, last: date) -> list[str]:
    return [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]


def _prev_close(symbol: str, before: date) -> tuple[str | None, float | None]:
    """The symbol's close on its last session before ``before`` (looked back ``PREV_LOOKBACK_DAYS``)."""
    for offset in range(1, PREV_LOOKBACK_DAYS + 1):
        day = (before - timedelta(days=offset)).isoformat()
        rows = _day_rows(day, (symbol,))
        if rows and symbol in rows:
            return day, rows[symbol]["close"]
    return None, None


def _symbol(symbol: str) -> str:
    out = str(symbol or "").strip().upper()
    if not out:
        raise ValueError("a symbol is required")
    return out


def _range(date_from: str, date_to: str) -> tuple[date, date]:
    first, last = date.fromisoformat(date_from), date.fromisoformat(date_to)
    if last < first:
        raise ValueError(f"date_to {date_to} is before date_from {date_from}")
    if (last - first).days > MAX_SPAN_DAYS:
        raise ValueError(f"{date_from}..{date_to} is longer than {MAX_SPAN_DAYS} days (3 years, ~756 day files, a "
                         "few seconds): ask for a shorter range, or use scan / movers for a many-year question")
    return first, last


def sessions(symbol: str, date_from: str, date_to: str) -> pd.DataFrame:
    """The raw rows (no slot taken: callers that already hold one use this). See ``daily_bars``."""
    symbol = _symbol(symbol)
    first, last = _range(date_from, date_to)
    days = _days(first, last)
    with ThreadPoolExecutor(READ_WORKERS) as pool:
        found = list(pool.map(lambda d: _day_rows(d, (symbol,)), days))
    rows = [{"date": d, **f[symbol]} for d, f in zip(days, found, strict=True) if f and symbol in f]
    frame = pd.DataFrame(rows, columns=["date", *NUMERIC])
    frame["transactions"] = frame["transactions"].astype("Int64")
    prev_day, prev = _prev_close(symbol, first) if len(frame) else (None, None)
    frame["prev_close"] = frame["close"].shift(1)
    if len(frame):
        frame.loc[0, "prev_close"] = prev
    frame.attrs.update(prev_close_from=prev_day)
    return frame


def _derive(frame: pd.DataFrame) -> pd.DataFrame:
    prev = frame["prev_close"]
    frame["change_pct"] = (frame["close"] / prev - 1.0) * 100.0
    frame["gap_pct"] = (frame["open"] / prev - 1.0) * 100.0
    frame["high_pct"] = (frame["high"] / prev - 1.0) * 100.0
    frame["range_pct"] = (frame["high"] - frame["low"]) / frame["open"] * 100.0
    return frame


def daily_bars(symbol: str, date_from: str, date_to: str, adjust: bool = False,
               as_of: str | None = None) -> pd.DataFrame:
    """One row per session ``symbol`` traded from ``date_from`` to ``date_to`` (ISO dates, both included, at most
    ``MAX_SPAN_DAYS``): ``date, open, high, low, close, volume, transactions, prev_close, change_pct, gap_pct,
    high_pct, range_pct`` (and ``split_factor`` when adjusted).

    ``prev_close`` is the previous row's close (the first row's: the symbol's last session before ``date_from``);
    ``change_pct`` close vs prev_close, ``gap_pct`` open vs prev_close, ``high_pct`` high vs prev_close, ``range_pct``
    (high - low) / open, all percent points. Raw (as traded) unless ``adjust``: then each day's prices x
    ``splits.factor(symbol, day, as_of)`` and its volume / it, so a split inside the range is not a fake move (raw
    ``change_pct`` across a split day reads the split). ``df.attrs`` says the units, the volume rule and the timing.
    """
    symbol = _symbol(symbol)
    _range(date_from, date_to)
    t0 = pd.Timestamp.now()
    with slots.heavy(f"daily_bars {symbol} {date_from}..{date_to}"):
        frame = sessions(symbol, date_from, date_to)
    if adjust and len(frame):
        from market_reads import splits
        factors = [splits.factor(symbol, d, as_of) for d in frame["date"]]
        prev_day = frame.attrs.get("prev_close_from")
        k_prev = [splits.factor(symbol, prev_day, as_of) if prev_day else 1.0] + factors[:-1]
        frame["split_factor"] = factors
        for column in ("open", "high", "low", "close"):
            frame[column] = frame[column] * frame["split_factor"]
        frame["volume"] = frame["volume"] / frame["split_factor"]
        frame["prev_close"] = frame["prev_close"] * pd.Series(k_prev, index=frame.index)
    frame = _derive(frame)
    frame.attrs.update(
        dataset=SIM_MASSIVE_DAYS, symbol=symbol, date_from=date_from, date_to=date_to, sessions=len(frame),
        adjusted=bool(adjust), adjusted_to=(as_of or "latest") if adjust else None, units=UNITS, volume_note=VOLUME_NOTE,
        as_of_rule="each row is its own session's file; prev_close is the previous session's close, never a later one",
        split_note=("prices x split_factor and volume / it, per day: splits.factor reads only the splits of the "
                    "company that held the ticker that day" if adjust else
                    "raw as traded: a split inside the range reads as a giant move (adjust=True puts every row in "
                    "one day's terms)"),
        seconds=round((pd.Timestamp.now() - t0).total_seconds(), 2))
    return frame


def _context_rows(day: str, symbols: tuple[str, ...], need: int) -> list[tuple[str, dict[str, dict]]]:
    """The last ``need`` sessions ending ``day`` (newest last), each ``(date, {symbol: row})``."""
    end = date.fromisoformat(day)
    out: list[tuple[str, dict[str, dict]]] = []
    offset = 0
    while len(out) < need and offset <= need * 2 + PREV_LOOKBACK_DAYS:
        d = (end - timedelta(days=offset)).isoformat()
        rows = _day_rows(d, symbols)
        if rows is not None:
            out.append((d, rows))
        offset += 1
    return out[::-1]


def _summary(moves: dict[str, float | None]) -> str:
    known = {s: m for s, m in moves.items() if m is not None}
    if not known:
        return "no index move on file for the day"
    parts = ", ".join(f"{s} {m:+.1f}%" for s, m in moves.items() if m is not None)
    mean = sum(known.values()) / len(known)
    kind = "an up day" if mean > FLAT_BAND_PCT else "a down day" if mean < -FLAT_BAND_PCT else "a flat day"
    if len(known) < 2:
        return f"{parts}: {kind}"
    low, high = min(known, key=known.get), max(known, key=known.get)
    weakest = INDEX_LABELS.get(low, low)
    strongest = INDEX_LABELS.get(high, high)
    lead = f"{weakest} weakest" if mean < 0 else f"{strongest} strongest"
    return f"{parts}: {kind}, {lead}"


def market_context(day: str, symbols: tuple[str, ...] | list[str] = ("SPY", "QQQ", "IWM"),
                   lookback: int = 20) -> dict:
    """The index ETFs' day ``day`` from the day files, nothing after it.

    Per symbol: ``open, high, low, close, volume, transactions`` (raw), ``prev_close``, ``change_pct``, ``gap_pct``,
    ``range_pct`` ((high - low) / open), ``return_5_pct`` and ``return_lookback_pct`` (close vs the close 5 and
    ``lookback`` sessions earlier), ``avg_close_lookback`` (mean close of the ``lookback`` sessions ending ``day``,
    ``day`` included) and ``close_vs_avg_pct``. ``summary`` is one plain line. Refuses a day with no day file."""
    symbols = tuple(_symbol(s) for s in symbols)
    lookback = int(lookback)
    if not 5 <= lookback <= MAX_CONTEXT_LOOKBACK:
        raise ValueError(f"lookback must be 5..{MAX_CONTEXT_LOOKBACK} sessions, not {lookback}")
    t0 = pd.Timestamp.now()
    with slots.heavy(f"market_context {day}"):
        history = _context_rows(day, symbols, lookback + 1)
    if not history or history[-1][0] != day:
        raise LookupError(f"no {SIM_MASSIVE_DAYS} file for {day} under {massive_files.root()}: not a session on disk")
    out: dict[str, dict] = {}
    for symbol in symbols:
        series = [(d, rows[symbol]) for d, rows in history if symbol in rows]
        if not series or series[-1][0] != day:
            out[symbol] = {"traded": False}
            continue
        closes = [r["close"] for _, r in series]
        today = series[-1][1]
        prev = closes[-2] if len(closes) >= 2 else None
        window = closes[-lookback:]
        avg = sum(window) / len(window) if len(window) == lookback else None
        out[symbol] = {
            "traded": True, **{k: today[k] for k in NUMERIC}, "prev_close": prev,
            "change_pct": _pct(today["close"], prev), "gap_pct": _pct(today["open"], prev),
            "range_pct": (today["high"] - today["low"]) / today["open"] * 100.0 if today["open"] else None,
            "return_5_pct": _pct(closes[-1], closes[-6]) if len(closes) >= 6 else None,
            "return_lookback_pct": _pct(closes[-1], closes[-lookback - 1]) if len(closes) > lookback else None,
            "avg_close_lookback": avg, "close_vs_avg_pct": _pct(closes[-1], avg)}
    return {
        "day": day, "lookback": lookback, "symbols": out,
        "summary": _summary({s: out[s].get("change_pct") for s in symbols}),
        "rules": {"as_of": "only sessions on or before day; returns count sessions on disk, not calendar days",
                  "range_pct": "(high - low) / open", "volume": VOLUME_NOTE,
                  "summary": f"the mean change_pct decides up / down / flat (inside +-{FLAT_BAND_PCT}% is flat)"},
        "units": UNITS, "raw": "prices raw as traded (ETF splits are not applied)",
        "seconds": round((pd.Timestamp.now() - t0).total_seconds(), 2)}
