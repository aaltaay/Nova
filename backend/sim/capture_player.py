"""Play recorded sim_capture jsonl into Sim desk (charts / T&S / L2 / quotes)."""
from __future__ import annotations

import bisect
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from capture.recorder import capture_root

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

_prints: list[dict[str, Any]] = []
_quotes: list[dict[str, Any]] = []
_l2: list[dict[str, Any]] = []
_bars: dict[str, list[dict[str, Any]]] = {"10s": [], "1m": [], "5m": [], "1d": []}
_print_keys: list[float] = []
_quote_keys: list[float] = []
_l2_keys: list[float] = []
_bar_keys: dict[str, list[float]] = {}
_loaded_key: str | None = None
_last_emit_ts: float = 0.0
_l2_path: Path | None = None
_print_bar_cache: dict[str, tuple[list[dict], list[float]]] = {}


def reset_for_tests() -> None:
    global _prints, _quotes, _l2, _bars, _loaded_key, _last_emit_ts, _l2_path
    global _print_keys, _quote_keys, _l2_keys, _bar_keys
    _prints, _quotes, _l2 = [], [], []
    _bars = {"10s": [], "1m": [], "5m": [], "1d": []}
    _print_keys, _quote_keys, _l2_keys = [], [], []
    _bar_keys = {}
    _loaded_key = None
    _last_emit_ts = 0.0
    _l2_path = None
    _print_bar_cache.clear()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    rows: list[dict[str, Any]] = []
    dropped = 0
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                dropped += 1
                continue
    if dropped:
        # D-067: a torn tail from an interrupted write is real data loss; say so
        # instead of silently replaying a short session.
        logger.warning(
            "CAPTURE replay: dropped %d unparseable line(s) from %s "
            "(truncated tail from an interrupted write?) — %d rows loaded",
            dropped,
            path,
            len(rows),
        )
    return rows


def _ts(row: dict[str, Any]) -> float:
    v = row.get("ts")
    return float(v) if isinstance(v, (int, float)) else 0.0


def session_dir(date: str, symbol: str) -> Path:
    return capture_root() / date / symbol.upper()


def load(date: str, symbol: str) -> dict[str, Any]:
    """Eager prints/quotes/bars; defer L2 so API stays responsive."""
    global _prints, _quotes, _l2, _bars, _loaded_key, _last_emit_ts, _l2_path
    global _print_keys, _quote_keys, _l2_keys, _bar_keys
    key = f"{date}|{symbol.upper()}"
    _print_bar_cache.clear()
    root = session_dir(date, symbol)
    if not root.is_dir():
        reset_for_tests()
        return {"ok": False, "error": f"missing {root}", "key": key}

    _prints = sorted(_read_jsonl(root / "prints.jsonl"), key=_ts)
    _quotes = sorted(_read_jsonl(root / "quotes.jsonl"), key=_ts)
    _l2 = []
    _l2_path = root / "l2.jsonl"
    _bars = {
        "10s": sorted(_read_jsonl(root / "bars_10s.jsonl"), key=_ts),
        "1m": sorted(_read_jsonl(root / "bars_1m.jsonl"), key=_ts),
        "5m": sorted(_read_jsonl(root / "bars_5m.jsonl"), key=_ts),
        "1d": sorted(_read_jsonl(root / "bars_1d.jsonl"), key=_ts),
    }
    _print_keys = [_ts(r) for r in _prints]
    _quote_keys = [_ts(r) for r in _quotes]
    _l2_keys = []
    _bar_keys = {k: [_ts(r) for r in v] for k, v in _bars.items()}
    _loaded_key = key
    _last_emit_ts = 0.0
    first_ts = _print_keys[0] if _print_keys else None
    last_ts = _print_keys[-1] if _print_keys else None
    l2_bytes = _l2_path.stat().st_size if _l2_path.is_file() else 0
    logger.info(
        "CAPTURE PLAY: loaded %s prints=%s quotes=%s bars1m=%s l2_bytes=%s",
        root,
        len(_prints),
        len(_quotes),
        len(_bars["1m"]),
        l2_bytes,
    )
    return {
        "ok": True,
        "key": key,
        "dir": str(root),
        "counts": {
            "prints": len(_prints),
            "quotes": len(_quotes),
            "l2": -1,
            "l2_bytes": l2_bytes,
            "bars_10s": len(_bars["10s"]),
            "bars_1m": len(_bars["1m"]),
            "bars_5m": len(_bars["5m"]),
            "bars_1d": len(_bars["1d"]),
        },
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


def unload() -> None:
    reset_for_tests()


def is_loaded() -> bool:
    return _loaded_key is not None


def loaded_key() -> str | None:
    return _loaded_key


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


def _ensure_l2() -> None:
    global _l2, _l2_keys, _l2_path
    if _l2 or _l2_path is None:
        return
    path = _l2_path
    if not path.is_file():
        return
    rows = _read_jsonl(path)
    if len(rows) > 30_000:
        step = max(1, len(rows) // 30_000)
        rows = rows[::step]
    _l2 = sorted(rows, key=_ts)
    _l2_keys = [_ts(r) for r in _l2]
    logger.info("CAPTURE PLAY: L2 hydrated n=%s from %s", len(_l2), path)


def has_prints() -> bool:
    return bool(_prints)


def chart_bars(timeframe: str, limit: int, *, asof: float | None = None) -> list[dict[str, Any]]:
    """Intraday bars from capture. Daily SSOT is IBKR (see chart_bars.py); 1d here is unused for desk."""
    if not is_loaded():
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
    rows = _bars.get(kind) or []
    keys = _bar_keys.get(kind) or []
    if not rows and _prints:
        if timeframe not in _print_bar_cache:
            aggregated = aggregate_prints(_prints, seconds)
            _print_bar_cache[timeframe] = (aggregated, [_ts(r) for r in aggregated])
        rows, keys = _print_bar_cache[timeframe]
        derive = False
    asof = asof_unix() if asof is None else asof
    bucket = int(asof // seconds) * seconds
    # A bar's timestamp is its OPEN. Its final OHLCV is not known until close.
    i = _asof_index(keys, bucket - (60 if derive else seconds))
    cap = max(1, min(int(limit or 300), 2000))
    source_cap = cap * (seconds // 60) if derive else cap
    bars = list({r["t"]: r for r in (
        _to_chart_bar(row) for row in rows[max(0, i - source_cap + 1):i + 1]
    )}.values())
    if derive:
        bars = derive_from_1min(bars, timeframe)
    lo = bisect.bisect_left(_print_keys, bucket)
    hi = bisect.bisect_right(_print_keys, asof)
    partial = print_candle(_prints[lo:hi], bucket)
    if partial:
        bars.append(partial)
    return bars[-cap:]


def recent_prints(limit: int = 40) -> list[dict[str, Any]]:
    if not is_loaded() or not _prints:
        return []
    asof = asof_unix()
    i = _asof_index(_print_keys, asof + 1e-6)
    if i < 0:
        return []
    cap = max(1, int(limit))
    chunk = _prints[max(0, i - cap + 1) : i + 1]
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
                "size": int(p.get("size") or 1),
                "exchange": str(p.get("exchange") or ""),
                "conditions": str(p.get("conditions") or ""),
                "side": p.get("side"),
                "bid": p.get("bid"),
                "ask": p.get("ask"),
            }
        )
    return out


def quote_at(asof: float | None = None) -> dict[str, Any] | None:
    t = asof if asof is not None else asof_unix()
    if _quotes:
        i = _asof_index(_quote_keys, t)
        if i >= 0:
            row = _quotes[i]
            last = float(row.get("last") or row.get("price") or 0)
            return {
                "symbol": str(row.get("symbol") or "").upper(),
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "last": last,
                "prev_close": float(row.get("prev_close") or last),
                "bid_size": row.get("bid_size"),
                "ask_size": row.get("ask_size"),
                "volume": row.get("volume"),
                "ts": _ts(row),
                "source": "capture",
            }
    i = _asof_index(_print_keys, t)
    if i < 0:
        return None
    row = _prints[i]
    px = float(row.get("price") or 0)
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "bid": row.get("bid") or round(px - 0.01, 2),
        "ask": row.get("ask") or round(px + 0.01, 2),
        "last": px,
        "prev_close": px,
        "bid_size": 100,
        "ask_size": 100,
        "volume": None,
        "ts": _ts(row),
        "source": "capture",
    }


def book_at(asof: float | None = None) -> dict[str, Any] | None:
    _ensure_l2()
    if not _l2:
        return None
    t = asof if asof is not None else asof_unix()
    i = _asof_index(_l2_keys, t)
    if i < 0:
        return None
    row = _l2[i]
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "bids": list(row.get("bids") or []),
        "asks": list(row.get("asks") or []),
        "ts": _ts(row),
        "source": "capture",
    }


def prints_since(since_ts: float, until_ts: float) -> list[dict[str, Any]]:
    if not _prints:
        return []
    lo = bisect.bisect_right(_print_keys, float(since_ts))
    hi = bisect.bisect_right(_print_keys, float(until_ts))
    return _prints[lo:hi]


def last_emit_ts() -> float:
    return _last_emit_ts


def mark_emitted(ts: float) -> None:
    global _last_emit_ts
    _last_emit_ts = max(_last_emit_ts, float(ts))


def seek_emit_cursor(asof: float) -> None:
    """Position emit cursor just before asof so the next tick streams forward."""
    global _last_emit_ts
    _last_emit_ts = float(asof) - 0.001
