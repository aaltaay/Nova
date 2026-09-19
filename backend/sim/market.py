"""Looping synthetic tape for SIM1 -- last/bid/ask, prints, simplified L2, bars.

Bar timestamps are UTC ISO strings (frontend RawBar.t / isoToEtTime).
Session clock is 06:00–18:00 America/New_York via sim.session_clock.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

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
from sim import session_clock as _clock

ET = ZoneInfo("America/New_York")

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


def rebuild_for_scrub() -> None:
    """Drop live 1m buffer; for capture, seek emit cursor and reseed tape/L2 viewers."""
    global _bars_1m
    _bars_1m = []
    try:
        from sim import capture_player as _player
        from sim import replay as _replay
        if not _replay.is_capture_replay():
            return
        now_ts = _clock.now_et().timestamp()
        _player.seek_emit_cursor(now_ts)
        status = _replay.status_payload() or {}
        sym = str(status.get("replay_symbol") or SIM_SYMBOL).strip().upper()
        if not sym:
            return
        from ibkr.tape_stream import _push_queue
        _push_queue(sym, {"type": "scrub_reset", "symbol": sym})
        for row in _player.recent_prints(40):
            _push_queue(sym, {**row, "type": "print", "symbol": sym})
        try:
            from ibkr.depth import state as _depth_state
            book = _player.book_at()
            if book is not None:
                book = dict(book)
                book["symbol"] = sym
                _depth_state.push_book(sym, book)
        except Exception:
            pass
    except Exception:
        pass



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
    try:
        from sim import replay as _replay
        from sim import capture_player as _player
        if _replay.is_capture_replay():
            q = _player.quote_at()
            if q is not None:
                return q
    except Exception:
        pass
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
    try:
        from sim import replay as _replay
        from sim import capture_player as _player
        if _replay.is_capture_replay():
            b = _player.book_at()
            if b is not None:
                return b
    except Exception:
        pass
    b = bid()
    a = ask()
    mult = _clock.phase_volume_mult()
    bids = [
        {
            "price": round(b - i * SIM_BOOK_TICK, 4),
            "size": float(SIM_BOOK_SIZE * (SIM_BOOK_LEVELS - i) * mult),
            "side": "bid",
            "mm": "SIM",
        }
        for i in range(SIM_BOOK_LEVELS)
    ]
    asks = [
        {
            "price": round(a + i * SIM_BOOK_TICK, 4),
            "size": float(SIM_BOOK_SIZE * (SIM_BOOK_LEVELS - i) * mult),
            "side": "ask",
            "mm": "SIM",
        }
        for i in range(SIM_BOOK_LEVELS)
    ]
    return {"bids": bids, "asks": asks, "l1_fallback": False}


def recent_prints(limit: int = 20) -> list[dict[str, Any]]:
    try:
        from sim import replay as _replay
        from sim import capture_player as _player
        if _replay.is_capture_replay():
            return _player.recent_prints(limit)
    except Exception:
        pass
    cap = max(1, int(limit))
    return list(_prints[-cap:])


def print_payload() -> dict[str, Any]:
    px = last()
    b, a = bid(), ask()
    side = "buy" if px >= (b + a) / 2.0 else "sell"
    size = int(round(SIM_PRINT_SIZE * _clock.phase_volume_mult()))
    return {
        "type": "print",
        "symbol": SIM_SYMBOL,
        "time": _now_iso(),
        "price": px,
        "size": max(1, size),
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
    amp = SIM_TICK_AMPLITUDE * (1.35 if _clock.phase() == "rth" else 0.85)
    mid = SIM_PREV_CLOSE + amp * math.sin(_tick * SIM_TICK_STEP_RAD)
    # Scrub position nudges mid so charts repaint when clock moves.
    minute = _clock.status_payload()["minute_from_open"]
    mid += 0.0004 * (minute - 360)
    _last = max(0.01, mid)
    _high = max(_high, _last)
    _low = min(_low, _last)
    size = int(round(SIM_PRINT_SIZE * _clock.phase_volume_mult()))
    _volume += max(1, size)
    payload = print_payload()
    _prints.append(payload)
    if len(_prints) > 800:
        del _prints[:400]
    _roll_minute(payload)
    return payload


def ticker_snapshot(symbol: str) -> dict[str, Any]:
    q = quote(symbol)
    if q is None:
        return {}
    now = _now_iso()
    last = q.get("last")
    prev = q.get("prev_close")
    if prev is None:
        prev = last
    return {
        "latest_trade": {
            "price": last,
            "size": SIM_PRINT_SIZE,
            "exchange": SIM_EXCHANGE,
            "timestamp": now,
        },
        "latest_quote": {"bid": q.get("bid"), "ask": q.get("ask"), "timestamp": now},
        "minute_bar": None,
        "daily_bar": {
            "open": SIM_START_LAST,
            "high": _high if _high else last,
            "low": _low if _low else last,
            "close": last,
            "volume": _volume,
            "trade_count": None,
            "vwap": None,
            "timestamp": now,
        },
        "prev_daily_bar": {
            "open": None,
            "high": None,
            "low": None,
            "close": prev,
            "volume": None,
            "trade_count": None,
            "vwap": None,
            "timestamp": None,
        },
        "prev_close": prev,
        "session_close": prev,
        "session_prev_close": None,
        "source": q.get("source") or "sim",
    }


def _tf_step_sec(timeframe: str) -> int | None:
    tf = (timeframe or "").strip()
    mapping = {
        "10Sec": 10,
        "10sec": 10,
        "1Min": 60,
        "1min": 60,
        "1m": 60,
        "5Min": 300,
        "5min": 300,
        "15Min": 900,
        "15min": 900,
        "30Min": 1800,
        "1Hour": 3600,
    }
    return mapping.get(tf)


def chart_bars(symbol: str, timeframe: str, limit: int) -> dict[str, Any]:
    sym = (symbol or "").strip().upper()
    try:
        from sim import replay as _replay
        from sim import capture_player as _player
        # Capture owns scrubbed intraday only — daily+ is IBKR (chart_bars.py).
        tf_norm = (timeframe or "").strip()
        if _replay.is_capture_replay() and tf_norm not in ("1Day", "1Week", "1Month"):
            bars = _player.chart_bars(timeframe, limit)
            return {
                "symbol": sym or _replay.status_payload().get("replay_symbol") or SIM_SYMBOL,
                "timeframe": timeframe,
                "bars": bars,
                "source": "capture",
                "coverage": {
                    "as_of": _now_iso(),
                    "complete_through": bars[-1]["t"] if bars else None,
                    "filling": False,
                },
            }
    except Exception:
        pass
    cap = max(1, min(int(limit or SIM_CHART_BARS_DEFAULT), 2000))
    tf = timeframe or "1Min"
    scrubbed = bool(_clock.status_payload().get("scrubbed"))
    if tf in ("1Day", "1Week", "1Month"):
        bars = _seed_daily(cap)
    elif scrubbed:
        # Scrub must re-seed history ending at sim now — ignore live 1m buffer.
        step = _tf_step_sec(tf) or 60
        bars = _seed_session_bars(cap, step)
    elif tf in ("1Min", "1min", "1m") and _bars_1m:
        bars = list(_bars_1m[-cap:])
        if len(bars) < min(cap, 30):
            seeded = _seed_session_bars(cap, 60)
            # Prefer live tip after seed history
            bars = seeded[:-1] + bars if bars else seeded
            bars = _dedupe_ascending(bars)[-cap:]
    else:
        step = _tf_step_sec(tf) or 60
        bars = _seed_session_bars(cap, step)
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
    # Use sim clock so scrub moves print times + chart as_of
    return _clock.now_et().astimezone(timezone.utc).isoformat()


def _roll_minute(payload: dict[str, Any]) -> None:
    n = _clock.now_et()
    bucket = n.replace(second=0, microsecond=0)
    px = float(payload["price"])
    size = float(payload["size"])
    t_iso = bucket.astimezone(timezone.utc).isoformat()
    if _bars_1m and _bars_1m[-1]["t"] == t_iso:
        bar = _bars_1m[-1]
        bar["h"] = max(bar["h"], px)
        bar["l"] = min(bar["l"], px)
        bar["c"] = px
        bar["v"] = float(bar["v"]) + size
        return
    if _bars_1m:
        try:
            from capture.bridge_sim import emit_sim_bar

            emit_sim_bar("1m", _bars_1m[-1])
        except Exception:
            pass
    _bars_1m.append({"t": t_iso, "o": px, "h": px, "l": px, "c": px, "v": size})
    if len(_bars_1m) > 800:
        del _bars_1m[:400]


def _seed_session_bars(count: int, step_sec: int) -> list[dict[str, Any]]:
    """Dense ascending ISO bars ending at sim now, within 06:00–18:00 ET."""
    now = _clock.now_et()
    start, _end = _clock.session_bounds_on(now)
    out: list[dict[str, Any]] = []
    # Walk backward in step_sec from now, stay >= session open
    cursor = now.replace(microsecond=0)
    # Align to step
    epoch = int(cursor.timestamp())
    aligned = epoch - (epoch % step_sec)
    cursor = datetime.fromtimestamp(aligned, tz=ET)
    for i in range(count):
        if cursor < start:
            break
        mid = SIM_PREV_CLOSE + SIM_TICK_AMPLITUDE * math.sin((count - i) * SIM_TICK_STEP_RAD)
        px = round(max(0.01, mid), 4)
        out.append(
            {
                "t": cursor.astimezone(timezone.utc).isoformat(),
                "o": px,
                "h": round(px + 0.01, 4),
                "l": round(max(0.01, px - 0.01), 4),
                "c": px,
                "v": float(SIM_PRINT_SIZE * _clock.phase_volume_mult(cursor)),
            }
        )
        cursor -= timedelta(seconds=step_sec)
    out.reverse()
    return _dedupe_ascending(out)


def _seed_daily(count: int) -> list[dict[str, Any]]:
    now = _clock.now_et().date()
    out: list[dict[str, Any]] = []
    for i in range(count, 0, -1):
        d = now - timedelta(days=i - 1)
        mid = SIM_PREV_CLOSE + SIM_TICK_AMPLITUDE * math.sin(i * SIM_TICK_STEP_RAD)
        px = round(max(0.01, mid), 4)
        # Daily business-day string YYYY-MM-DD (isoToEtTime daily path uses slice 0:10)
        out.append(
            {
                "t": f"{d.isoformat()}T16:00:00+00:00",
                "o": px,
                "h": round(px + 0.05, 4),
                "l": round(max(0.01, px - 0.05), 4),
                "c": px,
                "v": float(SIM_PRINT_SIZE * 40),
            }
        )
    return _dedupe_ascending(out)


def _dedupe_ascending(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not bars:
        return bars
    out: list[dict[str, Any]] = []
    last_t = None
    for b in bars:
        t = b["t"]
        if last_t is not None and t <= last_t:
            continue
        out.append(b)
        last_t = t
    return out
