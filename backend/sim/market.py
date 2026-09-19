"""Looping synthetic tape for SIM1 -- last/bid/ask, prints, simplified L2, bars."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from constants_sim import (
    SIM_BOOK_LEVELS,
    SIM_BOOK_SIZE,
    SIM_BOOK_TICK,
    SIM_CHART_BARS_DEFAULT,
    SIM_EXCHANGE,
    SIM_NAME,
    SIM_PREV_CLOSE,
    SIM_PRINT_SIZE,
    SIM_SPREAD,
    SIM_START_LAST,
    SIM_SYMBOL,
    SIM_TICK_AMPLITUDE,
    SIM_TICK_STEP_RAD,
)

_tick = 0
_last = SIM_START_LAST
_high = SIM_START_LAST
_low = SIM_START_LAST
_volume = 0
_prints: list[dict[str, Any]] = []
_bars_1m: list[dict[str, Any]] = []


def reset_for_tests() -> None:
    global _tick, _last, _high, _low, _volume, _prints, _bars_1m
    _tick = 0
    _last = SIM_START_LAST
    _high = SIM_START_LAST
    _low = SIM_START_LAST
    _volume = 0
    _prints = []
    _bars_1m = []


def last() -> float:
    return round(_last, 4)


def bid() -> float:
    return round(_last - SIM_SPREAD / 2.0, 4)


def ask() -> float:
    return round(_last + SIM_SPREAD / 2.0, 4)


def prev_close() -> float:
    return SIM_PREV_CLOSE


def volume() -> int:
    return _volume


def quote(symbol: str | None = None) -> dict[str, Any] | None:
    sym = (symbol or SIM_SYMBOL).strip().upper()
    if sym != SIM_SYMBOL:
        return None
    px = last()
    prev = prev_close()
    change = px - prev
    return {
        "symbol": SIM_SYMBOL,
        "last": px,
        "bid": bid(),
        "ask": ask(),
        "prev_close": prev,
        "volume": _volume,
        "change_abs": round(change, 4),
        "change_pct": round(change / prev, 6) if prev else 0.0,
    }


def last_quotes(symbols: list[str] | None = None) -> dict[str, dict[str, Any]]:
    wanted = None
    if symbols is not None:
        wanted = {(s or "").strip().upper() for s in symbols if s and str(s).strip()}
    if wanted is not None and SIM_SYMBOL not in wanted:
        return {}
    q = quote(SIM_SYMBOL)
    if q is None:
        return {}
    return {
        SIM_SYMBOL: {
            "price": q["last"],
            "last_update_ts": _now_iso(),
            "owners": {"sim"},
            "volume": q["volume"],
        }
    }


def book() -> dict[str, Any]:
    b = bid()
    a = ask()
    bids = [
        {
            "price": round(b - i * SIM_BOOK_TICK, 4),
            "size": float(SIM_BOOK_SIZE * (SIM_BOOK_LEVELS - i)),
            "side": "bid",
            "mm": "SIM",
        }
        for i in range(SIM_BOOK_LEVELS)
    ]
    asks = [
        {
            "price": round(a + i * SIM_BOOK_TICK, 4),
            "size": float(SIM_BOOK_SIZE * (SIM_BOOK_LEVELS - i)),
            "side": "ask",
            "mm": "SIM",
        }
        for i in range(SIM_BOOK_LEVELS)
    ]
    return {"bids": bids, "asks": asks, "l1_fallback": False}


def recent_prints(limit: int = 20) -> list[dict[str, Any]]:
    cap = max(1, int(limit))
    return list(_prints[-cap:])


def print_payload() -> dict[str, Any]:
    px = last()
    b, a = bid(), ask()
    side = "buy" if px >= (b + a) / 2.0 else "sell"
    return {
        "type": "print",
        "symbol": SIM_SYMBOL,
        "time": _now_iso(),
        "price": px,
        "size": SIM_PRINT_SIZE,
        "exchange": SIM_EXCHANGE,
        "conditions": "SIM",
        "side": side,
        "bid": b,
        "ask": a,
    }


def step() -> dict[str, Any]:
    """Advance one loop tick. Returns the print just produced."""
    global _tick, _last, _high, _low, _volume
    _tick += 1
    mid = SIM_PREV_CLOSE + SIM_TICK_AMPLITUDE * math.sin(_tick * SIM_TICK_STEP_RAD)
    _last = max(0.01, mid)
    _high = max(_high, _last)
    _low = min(_low, _last)
    _volume += SIM_PRINT_SIZE
    payload = print_payload()
    _prints.append(payload)
    if len(_prints) > 400:
        del _prints[:200]
    _roll_minute(payload)
    return payload


def ticker_snapshot(symbol: str) -> dict[str, Any]:
    q = quote(symbol)
    if q is None:
        return {}
    now = _now_iso()
    return {
        "latest_trade": {
            "price": q["last"],
            "size": SIM_PRINT_SIZE,
            "exchange": SIM_EXCHANGE,
            "timestamp": now,
        },
        "latest_quote": {"bid": q["bid"], "ask": q["ask"], "timestamp": now},
        "minute_bar": None,
        "daily_bar": {
            "open": SIM_START_LAST,
            "high": _high,
            "low": _low,
            "close": q["last"],
            "volume": _volume,
            "trade_count": None,
            "vwap": None,
            "timestamp": now,
        },
        "prev_daily_bar": {
            "open": None,
            "high": None,
            "low": None,
            "close": q["prev_close"],
            "volume": None,
            "trade_count": None,
            "vwap": None,
            "timestamp": None,
        },
        "prev_close": q["prev_close"],
        "session_close": q["prev_close"],
        "session_prev_close": None,
        "source": "sim",
    }


def chart_bars(symbol: str, timeframe: str, limit: int) -> dict[str, Any]:
    sym = (symbol or "").strip().upper()
    cap = max(1, min(int(limit or SIM_CHART_BARS_DEFAULT), 2000))
    now = int(datetime.now(timezone.utc).timestamp())
    if timeframe in ("1Min", "1min", "1m"):
        bars = list(_bars_1m[-cap:])
        if not bars:
            bars = _seed_bars(now, cap, 60)
    elif timeframe in ("10Sec", "10sec"):
        bars = _seed_bars(now, cap, 10)
    else:
        bars = _seed_bars(now, cap, 60)
    return {
        "symbol": sym or SIM_SYMBOL,
        "timeframe": timeframe,
        "bars": bars,
        "source": "sim",
        "coverage": {
            "as_of": _now_iso(),
            "complete_through": bars[-1]["t"] if bars else None,
            "filling": False,
        },
    }


def gainer_row() -> dict[str, Any]:
    q = quote(SIM_SYMBOL) or {}
    px = q.get("last")
    prev = q.get("prev_close")
    return {
        "symbol": SIM_SYMBOL,
        "name": SIM_NAME,
        "exchange": SIM_EXCHANGE,
        "rank": 1,
        "price": px,
        "prev_close": prev,
        "previous_close": prev,
        "current_price": px,
        "change_pct": q.get("change_pct"),
        "change_abs": q.get("change_abs"),
        "gap_percent": q.get("change_pct"),
        "volume": q.get("volume") or 0,
        "rel_volume": None,
        "has_news": False,
        "newest_headline_at": None,
        "market_cap": None,
        "float": None,
        "short_interest": None,
        "short_ratio": None,
        "source": "sim",
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _roll_minute(payload: dict[str, Any]) -> None:
    ts = int(datetime.now(timezone.utc).timestamp())
    bucket = ts - (ts % 60)
    px = float(payload["price"])
    size = float(payload["size"])
    if _bars_1m and _bars_1m[-1]["t"] == bucket:
        bar = _bars_1m[-1]
        bar["h"] = max(bar["h"], px)
        bar["l"] = min(bar["l"], px)
        bar["c"] = px
        bar["v"] = float(bar["v"]) + size
        return
    _bars_1m.append({"t": bucket, "o": px, "h": px, "l": px, "c": px, "v": size})
    if len(_bars_1m) > 400:
        del _bars_1m[:200]


def _seed_bars(now: int, count: int, step_sec: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(count, 0, -1):
        t = now - i * step_sec
        mid = SIM_PREV_CLOSE + SIM_TICK_AMPLITUDE * math.sin(i * SIM_TICK_STEP_RAD)
        px = round(max(0.01, mid), 4)
        out.append({"t": t, "o": px, "h": px, "l": px, "c": px, "v": float(SIM_PRINT_SIZE)})
    return out
