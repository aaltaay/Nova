"""Causal facts for the desk review route.

A bar is usable only once it has closed. Levels, the session VWAP and the
session day's daily candle are computed from those bars alone. No disk and
no broker.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
SESSION_START = time(4, 0)
SESSION_END = time(16, 0)
RTH_OPEN = time(9, 30)
OPENING_RANGE_END = time(9, 35)
LOOKBACK_DAYS = 183
MAX_SYMBOLS = 9
DEFAULT_AS_OF = "16:00"
DEFAULT_TFS = ("1m", "5m", "10s", "1d")
TF_ORDER = ("5m", "10s", "1d", "1m")
CHART_TIMEFRAMES = ("10s", "1m", "5m", "1d")
TF_STEP = {"1m": timedelta(minutes=1), "5m": timedelta(minutes=5), "10s": timedelta(seconds=10)}
OUTPUTS = frozenset({"png", "interactive", "both"})


def parse_day(day: str) -> date:
    if len(day) != 10:
        raise ValueError(f"date must be YYYY-MM-DD, not {day!r}")
    return date.fromisoformat(day)


def check_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if not text or len(text) > 10 or not text[0].isalpha() or any(ch != "." and not ch.isalnum() for ch in text):
        raise ValueError(f"symbol must be a ticker, not {symbol!r}")
    return text


def check_clock(as_of: str) -> str:
    text = str(as_of or DEFAULT_AS_OF).strip()
    parts = text.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"as_of must be HH:MM ET, not {as_of!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if hour > 23 or minute > 59:
        raise ValueError(f"as_of must be HH:MM ET, not {as_of!r}")
    return f"{hour:02d}:{minute:02d}"


def check_tfs(tfs: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if tfs is None or tfs == "":
        asked = list(DEFAULT_TFS)
    elif isinstance(tfs, str):
        asked = [part.strip() for part in tfs.split(",") if part.strip()]
    else:
        asked = [str(part).strip() for part in tfs if str(part).strip()]
    unknown = [part for part in asked if part not in DEFAULT_TFS]
    if not asked or unknown:
        raise ValueError(f"tf must be 1m, 5m, 10s, 1d, not {tfs!r}")
    return [part for part in TF_ORDER if part in asked]


def as_of_dt(day: str, as_of: str | None) -> datetime:
    clock = check_clock(as_of or DEFAULT_AS_OF)
    hour, minute = (int(part) for part in clock.split(":"))
    return datetime.combine(parse_day(day), time(hour, minute), tzinfo=ET)


def bar_start(row: dict[str, Any]) -> datetime:
    raw = row.get("time_et", row.get("t"))
    if hasattr(raw, "to_pydatetime"):
        raw = raw.to_pydatetime()
    if isinstance(raw, str):
        raw = datetime.fromisoformat(raw)
    if not isinstance(raw, datetime):
        raise ValueError("bar is missing time_et")
    if raw.tzinfo is None:
        raw = raw.replace(tzinfo=ET)
    return raw.astimezone(ET)


def _num(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value is None:
        raise ValueError(f"bar is missing {key}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"bar {key} is not finite")
    return number


def _finite_price(row: dict[str, Any]) -> bool:
    """A volume-only bucket has NaN OHLC. It is not a candle."""
    for key in ("open", "high", "low", "close"):
        try:
            _num(row, key)
        except (TypeError, ValueError):
            return False
    return True


def closed_bars(rows: list[dict[str, Any]], tf: str, as_of: datetime) -> list[dict[str, Any]]:
    """Bars whose whole window has ended by ``as_of``. A 09:55 5-minute bar stays out until 10:00."""
    step = TF_STEP[tf]
    kept = []
    for row in rows:
        if not _finite_price(row):
            continue
        start = bar_start(row)
        if start + step <= as_of:
            kept.append(row)
    return kept


def _session_bars(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if SESSION_START <= bar_start(row).time() < SESSION_END]


def wire_bar(row: dict[str, Any], tf: str) -> dict[str, Any] | None:
    """One candle. ``None`` when OHLC is missing or not finite, so JSON never contains NaN."""
    if not _finite_price(row):
        return None
    start = bar_start(row)
    stamp = start.date().isoformat() if tf == "1d" else start.isoformat()
    try:
        volume = float(row.get("volume", row.get("v", 0)) or 0)
    except (TypeError, ValueError):
        volume = 0.0
    if not math.isfinite(volume):
        volume = 0.0
    return {"t": stamp, "o": _num(row, "open"), "h": _num(row, "high"), "l": _num(row, "low"),
            "c": _num(row, "close"), "v": volume}


def wire_bars(rows: list[dict[str, Any]], tf: str) -> list[dict[str, Any]]:
    return [bar for row in rows if (bar := wire_bar(row, tf)) is not None]


def day_key(row: dict[str, Any]) -> str:
    raw = row.get("date", row.get("t"))
    if hasattr(raw, "isoformat") and not isinstance(raw, str):
        return raw.isoformat()[:10]
    return str(raw)[:10]


def levels(minute_bars: list[dict[str, Any]], dailies: list[dict[str, Any]], day: str, as_of: datetime) -> dict[str, Any]:
    """Highs and lows the desk can know at ``as_of``. Opening range stays empty until 09:35."""
    kept = _session_bars(minute_bars)
    hod = max((_num(row, "high") for row in kept), default=None)
    lod = min((_num(row, "low") for row in kept), default=None)
    premarket = [row for row in kept if bar_start(row).time() < RTH_OPEN]
    pm_high = max((_num(row, "high") for row in premarket), default=None)
    opening = None
    if as_of.timetz().replace(tzinfo=None) >= OPENING_RANGE_END:
        window = [row for row in kept if RTH_OPEN <= bar_start(row).time() < OPENING_RANGE_END]
        if window:
            opening = (max(_num(row, "high") for row in window), min(_num(row, "low") for row in window))
    prior = [row for row in dailies if day_key(row) < day and _finite_price(row)]
    last = prior[-1] if prior else None
    return {
        "hod": hod,
        "lod": lod,
        "premarket_high": pm_high,
        "opening_range_high": opening[0] if opening else None,
        "opening_range_low": opening[1] if opening else None,
        "prior_high": _num(last, "high") if last else None,
        "prior_low": _num(last, "low") if last else None,
        "prior_close": _num(last, "close") if last else None,
    }


def session_vwap(minute_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The desk's session VWAP: typical price, anchored at 04:00, reset at 16:00.

    Matches ``sessionVwapPoints`` in the chart package: bars before 04:00 add
    nothing, and the cash-session total does not take after-hours volume.
    """
    points = []
    cum_pv = 0.0
    cum_v = 0.0
    value = None
    day = None
    after_hours = False
    for row in minute_bars:
        start = bar_start(row)
        if start.date() != day:
            cum_pv = 0.0
            cum_v = 0.0
            value = None
            day = start.date()
            after_hours = False
        clock = start.time()
        if clock < SESSION_START:
            continue
        if clock >= SESSION_END and not after_hours:
            cum_pv = 0.0
            cum_v = 0.0
            value = None
            after_hours = True
        volume = float(row.get("volume") or 0)
        if volume > 0 and clock < time(20, 0) and _finite_price(row):
            typical = (_num(row, "high") + _num(row, "low") + _num(row, "close")) / 3.0
            cum_pv += typical * volume
            cum_v += volume
        if cum_v > 0:
            value = cum_pv / cum_v
        if value is not None:
            points.append({"t": start.isoformat(), "value": value})
    return points


def daily_series(dailies: list[dict[str, Any]], minute_bars: list[dict[str, Any]], day: str) -> list[dict[str, Any]]:
    """Prior sessions stay. The session day is the cut minutes, never the official daily row."""
    out = []
    for row in dailies:
        key = day_key(row)
        if key < day and _finite_price(row):
            volume = float(row.get("volume") or 0)
            if not math.isfinite(volume):
                volume = 0.0
            out.append({"t": key, "o": _num(row, "open"), "h": _num(row, "high"), "l": _num(row, "low"),
                        "c": _num(row, "close"), "v": volume})
    kept = _session_bars(minute_bars)
    if kept:
        out.append({
            "t": day,
            "o": _num(kept[0], "open"),
            "h": max(_num(row, "high") for row in kept),
            "l": min(_num(row, "low") for row in kept),
            "c": _num(kept[-1], "close"),
            "v": float(sum(float(row.get("volume") or 0) for row in kept)),
        })
    out.sort(key=lambda row: row["t"])
    return out


def causal_setups(bars_5m: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A flat top is three closed 5-minute highs within 0.5% of each other. Known at the third bar."""
    found = []
    index = 0
    while index + 2 < len(bars_5m) and len(found) < 4:
        window = bars_5m[index:index + 3]
        highs = [_num(row, "high") for row in window]
        top = max(highs)
        if top > 0 and (top - min(highs)) / top <= 0.005:
            found.append({"kind": "flat_top", "time": bar_start(window[2]).isoformat(), "price": top, "label": "flat top"})
            index += 3
        else:
            index += 1
    return found


def lookback_start(day: str) -> str:
    return (parse_day(day) - timedelta(days=LOOKBACK_DAYS)).isoformat()


def _query(params: list[tuple[str, str]]) -> str:
    return urlencode(params)


def review_link(symbol: str, date: str, as_of: str, api: str | None, base: str) -> str:
    """One symbol's four-pane review page. Later open_in_nova can call this same builder."""
    params = [("symbol", symbol), ("date", date), ("tf", ",".join(CHART_TIMEFRAMES))]
    if as_of != DEFAULT_AS_OF:
        params.append(("as_of", as_of))
    if api:
        params.append(("api", api.rstrip("/")))
    return f"{base.rstrip('/')}/review?{_query(params)}"


def gallery_link(symbols: list[str], date: str, as_of: str, api: str | None, base: str) -> str:
    """The gallery opens on the 5-minute tab."""
    params = [("symbols", ",".join(symbols)), ("date", date), ("gtf", "5m"), ("tf", ",".join(CHART_TIMEFRAMES))]
    if as_of != DEFAULT_AS_OF:
        params.append(("as_of", as_of))
    if api:
        params.append(("api", api.rstrip("/")))
    return f"{base.rstrip('/')}/review?{_query(params)}"


def symbol_url(base: str, symbol: str, day: str, tfs: list[str], as_of: str, api: str | None = None) -> str:
    del tfs
    return review_link(symbol, day, as_of, api, base)


def gallery_url(base: str, symbols: list[str], day: str, tfs: list[str], as_of: str, api: str | None = None) -> str:
    del tfs
    return gallery_link(symbols, day, as_of, api, base)


def chat_message(*, date: str, as_of: str, links: list[dict[str, str]], gallery_url_text: str | None = None,
                 preview_code: str | None = None) -> str:
    """The text every client posts. ASCII only. No markdown besides the plain URLs."""
    lines = [f"Nova charts for {date}, as of {as_of} ET (10s, 1m, 5m, 1d, full session):"]
    for item in links:
        lines.append(f"- {item['symbol']}: {item['url']}")
    if gallery_url_text and len(links) > 1:
        lines.append(f"Gallery: {gallery_url_text}")
    if preview_code:
        lines.append(f"Preview images unavailable: {preview_code}")
    text = "\n".join(lines)
    if any(ord(ch) > 127 for ch in text):
        raise ValueError("chat_message is not ASCII")
    return text


def chart_links(symbols: list[str] | str, day: str, as_of: str | None, *, base: str,
                api: str | None = None) -> dict[str, Any]:
    """Review URLs only. This does not read bars."""
    names = parse_symbols(symbols)
    session = parse_day(day).isoformat()
    clock = check_clock(as_of or DEFAULT_AS_OF)
    links = [{"symbol": symbol, "url": review_link(symbol, session, clock, api, base)} for symbol in names]
    return {
        "ok": True,
        "loaded": False,
        "date": session,
        "as_of": clock,
        "links": links,
        "gallery_url": gallery_link(names, session, clock, api, base),
    }


def parse_symbols(symbols: list[str] | str) -> list[str]:
    raw = symbols.split(",") if isinstance(symbols, str) else list(symbols)
    out = []
    seen = set()
    for item in raw:
        symbol = check_symbol(item)
        if symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    if not out or len(out) > MAX_SYMBOLS:
        raise ValueError(f"symbols must be 1 to {MAX_SYMBOLS} tickers")
    return out


def chart_pages(symbols: list[str] | str, day: str, tfs: list[str] | str | None, output: str = "interactive",
                *, base: str, as_of: str | None = None, api: str | None = None) -> dict[str, Any]:
    """Review URLs only. This does not read bars; each page loads its own."""
    mode = output or "interactive"
    if mode not in OUTPUTS:
        return {"ok": False, "error": {"code": "BAD_OUTPUT", "detail": mode}}
    try:
        names = parse_symbols(symbols)
        session = parse_day(day).isoformat()
        frames = check_tfs(tfs)
        clock = check_clock(as_of or DEFAULT_AS_OF)
    except ValueError as exc:
        return {"ok": False, "error": {"code": "BAD_REQUEST", "detail": str(exc)}}
    pages = [{"symbol": symbol, "date": session, "url": symbol_url(base, symbol, session, frames, clock, api)}
             for symbol in names]
    return {
        "ok": True,
        "output": mode,
        "lazy": True,
        "loaded": False,
        "urls": {
            "symbols": pages,
            "gallery": gallery_url(base, names, session, frames, clock, api),
        },
    }


def trade_pages(trades: list[dict[str, Any]], output: str = "interactive", *, base: str,
                api: str | None = None) -> dict[str, Any]:
    """One review URL per symbol and date. A gallery URL when every trade is the same day."""
    if not isinstance(trades, list) or not trades:
        return {"ok": False, "error": {"code": "BAD_REQUEST", "detail": "trades must be a list"}}
    pairs = []
    seen = set()
    try:
        for trade in trades:
            symbol = check_symbol(str(trade.get("symbol") or ""))
            day = parse_day(str(trade.get("date") or trade.get("day") or "")).isoformat()
            if (symbol, day) not in seen:
                seen.add((symbol, day))
                pairs.append((symbol, day))
    except ValueError as exc:
        return {"ok": False, "error": {"code": "BAD_REQUEST", "detail": str(exc)}}
    if len(pairs) > MAX_SYMBOLS:
        return {"ok": False, "error": {"code": "TOO_MANY_SYMBOLS", "detail": str(len(pairs))}}
    mode = output or "interactive"
    if mode not in OUTPUTS:
        return {"ok": False, "error": {"code": "BAD_OUTPUT", "detail": mode}}
    frames = list(TF_ORDER)
    pages = [{"symbol": symbol, "date": day, "url": symbol_url(base, symbol, day, frames, DEFAULT_AS_OF, api)}
             for symbol, day in pairs]
    dates = {day for _, day in pairs}
    gallery = gallery_url(base, [symbol for symbol, _ in pairs], next(iter(dates)), frames, DEFAULT_AS_OF, api) if len(dates) == 1 else None
    return {"ok": True, "output": mode, "lazy": True, "loaded": False, "urls": {"symbols": pages, "gallery": gallery}}
