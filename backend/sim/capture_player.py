"""Play recorded sim_capture jsonl into Sim desk (charts / T&S / L2 / quotes)."""
from __future__ import annotations

import bisect
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from capture.recorder import capture_root
from capture.constants_capture import (
    CAPTURE_CHART_DEFAULT_LIMIT, CAPTURE_CHART_MAX_LIMIT, CAPTURE_L2_LOAD_LIMIT,
)
from capture.schema import read_manifest
from sim.capture_reader import read_jsonl as _read_jsonl, usable_rows, new_diagnostics, sample_l2

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

@dataclass
class CaptureData:
    key: str
    symbol: str
    prints: list[dict]
    quotes: list[dict]
    l2: list[dict]
    bars: dict[str, list[dict]]
    print_keys: list[float]
    quote_keys: list[float]
    l2_keys: list[float]
    bar_keys: dict[str, list[float]]
    print_bar_cache: dict = field(default_factory=dict)
    last_emit: float = 0.0


_state: CaptureData | None = None
_generation = 0
_load_lock = threading.Lock()


def reset_for_tests() -> None:
    global _state, _generation
    with _load_lock:
        _generation += 1
        _state = None


def snapshot() -> CaptureData | None:
    return _state


def _ts(row: dict[str, Any]) -> float:
    v = row.get("ts")
    return float(v) if isinstance(v, (int, float)) else 0.0


def session_dir(date: str, symbol: str) -> Path:
    return capture_root() / date / symbol.upper()


def prepare_load() -> int:
    global _generation
    with _load_lock:
        _generation += 1
        return _generation


def load(date: str, symbol: str, *, generation: int | None = None) -> dict[str, Any]:
    """Load validated streams on the replay worker; no file I/O during playback."""
    global _state
    generation = prepare_load() if generation is None else generation
    key = f"{date}|{symbol.upper()}"
    root = session_dir(date, symbol)
    def failure(error: str, diagnostics: dict | None = None) -> dict:
        global _state
        with _load_lock:
            if generation == _generation:
                _state = None
        return {"ok": False, "error": error, "key": key, **(diagnostics or {})}
    if not root.is_dir():
        return failure(f"missing {root}")

    diagnostics = new_diagnostics()
    try:
        _manifest, diagnostics["legacy_schema"] = read_manifest(root)
        def read(name: str, kind: str) -> list[dict]:
            return usable_rows(_read_jsonl(root / (name + ".jsonl"), diagnostics), kind, symbol, diagnostics)
        prints = read("prints", "prints")
        quotes = read("quotes", "quotes")
        l2 = sample_l2(read("l2", "l2"), CAPTURE_L2_LOAD_LIMIT, diagnostics)
        bars = {tf: read("bars_" + tf, "bars") for tf in ("10s", "1m", "5m")}
    except ValueError as exc:
        return failure(str(exc), diagnostics)
    if not prints and not quotes:
        return failure("Capture contains no usable prints or quotes; "
                       f"discarded {diagnostics['malformed_rows']} malformed, "
                       f"{diagnostics['invalid_timestamp_rows']} invalid timestamp and "
                       f"{diagnostics['invalid_rows']} invalid payload rows", diagnostics)
    state = CaptureData(key, symbol.upper(), prints, quotes, l2, bars,
                        [_ts(r) for r in prints], [_ts(r) for r in quotes],
                        [_ts(r) for r in l2], {k: [_ts(r) for r in v] for k, v in bars.items()})
    event_keys = state.print_keys + state.quote_keys
    first_ts, last_ts = min(event_keys), max(event_keys)
    l2_path = root / "l2.jsonl"
    l2_bytes = l2_path.stat().st_size if l2_path.is_file() else 0
    with _load_lock:
        if generation != _generation:
            return {"ok": False, "error": "Capture selection was superseded", "key": key}
        _state = state
    logger.info("CAPTURE PLAY: loaded %s prints=%s quotes=%s l2=%s", key, len(prints), len(quotes), len(l2))
    return {
        "ok": True,
        "key": key,
        "dir": str(root),
        **diagnostics,
        "counts": {
            "prints": len(prints),
            "quotes": len(quotes),
            "l2": len(l2),
            "l2_bytes": l2_bytes,
            "bars_10s": len(bars["10s"]),
            "bars_1m": len(bars["1m"]),
            "bars_5m": len(bars["5m"]),
        },
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


def unload() -> None:
    reset_for_tests()


def is_loaded() -> bool:
    return _state is not None


def loaded_key() -> str | None:
    state = _state
    return state.key if state else None


def asof_unix() -> float:
    from sim import session_clock as _clock

    return _clock.now_et().timestamp()


def _bar_tf(timeframe: str) -> str:
    tf = (timeframe or "").strip().lower().replace(" ", "")
    if tf in ("10s", "10sec", "10"):
        return "10s"
    if tf in ("5m", "5min", "5minute"):
        return "5m"
    if tf in ("1d", "1day", "day", "daily"):
        return "1d"
    return "1m"


def _to_chart_bar(row: dict[str, Any]) -> dict[str, Any]:
    ts = _ts(row)
    t_iso = datetime.fromtimestamp(ts, tz=ET).astimezone(timezone.utc).isoformat()
    return {
        "t": t_iso,
        "o": float(row.get("open") or row.get("o") or 0),
        "h": float(row.get("high") or row.get("h") or 0),
        "l": float(row.get("low") or row.get("l") or 0),
        "c": float(row.get("close") or row.get("c") or 0),
        "v": float(row.get("volume") or row.get("v") or 0),
    }


def _asof_index(keys: list[float], asof: float) -> int:
    if not keys:
        return -1
    return bisect.bisect_right(keys, asof) - 1


def has_prints() -> bool:
    state = _state
    return bool(state and state.prints)


def chart_bars(timeframe: str, limit: int, *, asof: float | None = None) -> list[dict[str, Any]]:
    """Intraday bars from capture. Daily SSOT is IBKR (see chart_bars.py); 1d here is unused for desk."""
    state = _state
    if state is None:
        return []
    from sim.chart_replay import INTERVAL_SECONDS, aggregate_prints, print_candle
    from ibkr.historical_derive import derive_from_1min

    seconds = INTERVAL_SECONDS.get(timeframe)
    if seconds is None:
        return []
    kind = _bar_tf(timeframe)
    derive = timeframe in ("15Min", "30Min", "1Hour")
    if derive:
        kind = "1m"
    rows = state.bars.get(kind) or []
    keys = state.bar_keys.get(kind) or []
    if not rows and state.prints:
        if timeframe not in state.print_bar_cache:
            aggregated = aggregate_prints(state.prints, seconds)
            state.print_bar_cache[timeframe] = (aggregated, [_ts(r) for r in aggregated])
        rows, keys = state.print_bar_cache[timeframe]
        derive = False
    asof = asof_unix() if asof is None else asof
    bucket = int(asof // seconds) * seconds
    # A bar's timestamp is its OPEN. Its final OHLCV is not known until close.
    i = _asof_index(keys, bucket - (60 if derive else seconds))
    cap = max(1, min(int(limit or CAPTURE_CHART_DEFAULT_LIMIT), CAPTURE_CHART_MAX_LIMIT))
    source_cap = cap * (seconds // 60) if derive else cap
    bars = list({r["t"]: r for r in (
        _to_chart_bar(row) for row in rows[max(0, i - source_cap + 1):i + 1]
    )}.values())
    if derive:
        bars = derive_from_1min(bars, timeframe)
    lo = bisect.bisect_left(state.print_keys, bucket)
    hi = bisect.bisect_right(state.print_keys, asof)
    partial = print_candle(state.prints[lo:hi], bucket)
    if partial:
        bars.append(partial)
    return bars[-cap:]


def recent_prints(limit: int = 40, *, state: CaptureData | None = None) -> list[dict[str, Any]]:
    state = state or _state
    if state is None or not state.prints:
        return []
    asof = asof_unix()
    i = _asof_index(state.print_keys, asof + 1e-6)
    if i < 0:
        return []
    cap = max(1, int(limit))
    chunk = state.prints[max(0, i - cap + 1) : i + 1]
    out: list[dict[str, Any]] = []
    for p in chunk:
        ts = _ts(p)
        t_iso = datetime.fromtimestamp(ts, tz=ET).astimezone(timezone.utc).isoformat()
        out.append(
            {
                "type": "print",
                "symbol": str(p.get("symbol") or "").upper(),
                "time": t_iso,
                "price": float(p.get("price") or 0),
                "size": int(p["size"]) if p.get("size") is not None else None,
                "exchange": str(p.get("exchange") or ""),
                "conditions": str(p.get("conditions") or ""),
                "side": p.get("side"),
                "bid": p.get("bid"),
                "ask": p.get("ask"),
            }
        )
    return out


def quote_at(asof: float | None = None, *, state: CaptureData | None = None) -> dict[str, Any] | None:
    state = state or _state
    if state is None:
        return None
    t = asof if asof is not None else asof_unix()
    if state.quotes:
        i = _asof_index(state.quote_keys, t)
        if i >= 0:
            row = state.quotes[i]
            last = float(row.get("last") or row.get("price") or 0)
            return {
                "symbol": str(row.get("symbol") or "").upper(),
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "last": last,
                "prev_close": row.get("prev_close"),
                "bid_size": row.get("bid_size"),
                "ask_size": row.get("ask_size"),
                "volume": row.get("volume"),
                "ts": _ts(row),
                "source": "capture",
            }
    i = _asof_index(state.print_keys, t)
    if i < 0:
        return None
    row = state.prints[i]
    px = float(row.get("price") or 0)
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "bid": row.get("bid"),
        "ask": row.get("ask"),
        "last": px,
        "prev_close": None,
        "bid_size": None,
        "ask_size": None,
        "volume": None,
        "ts": _ts(row),
        "source": "capture",
    }


def last_print_at(asof: float, *, state: CaptureData | None = None) -> float | None:
    """Price of the last recorded print at or before ``asof``."""
    state = state or _state
    if state is None or not state.prints:
        return None
    i = _asof_index(state.print_keys, asof)
    return float(state.prints[i]["price"]) if i >= 0 else None


def book_at(asof: float | None = None, *, state: CaptureData | None = None) -> dict[str, Any] | None:
    state = state or _state
    if state is None or not state.l2:
        return None
    t = asof if asof is not None else asof_unix()
    i = _asof_index(state.l2_keys, t)
    if i < 0:
        return None
    row = state.l2[i]
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "bids": list(row.get("bids") or []),
        "asks": list(row.get("asks") or []),
        "ts": _ts(row),
        "source": "capture",
    }


def prints_since(since_ts: float, until_ts: float, *, state: CaptureData | None = None) -> list[dict[str, Any]]:
    state = state or _state
    if state is None or not state.prints:
        return []
    lo = bisect.bisect_right(state.print_keys, float(since_ts))
    hi = bisect.bisect_right(state.print_keys, float(until_ts))
    return state.prints[lo:hi]


def last_emit_ts() -> float:
    state = _state
    return state.last_emit if state else 0.0


def mark_emitted(ts: float, *, state: CaptureData | None = None) -> None:
    state = state or _state
    if state is not None:
        state.last_emit = max(state.last_emit, float(ts))


def seek_emit_cursor(asof: float, *, state: CaptureData | None = None) -> None:
    """Position emit cursor just before asof so the next tick streams forward."""
    state = state or _state
    if state is not None:
        state.last_emit = float(asof) - 0.001
