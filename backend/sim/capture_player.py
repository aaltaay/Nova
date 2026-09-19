"""Play recorded sim_capture jsonl into Sim desk (charts / T&S / L2 / quotes)."""
from __future__ import annotations

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
_loaded_key: str | None = None
_last_emit_ts: float = 0.0


def reset_for_tests() -> None:
    global _prints, _quotes, _l2, _bars, _loaded_key, _last_emit_ts
    _prints, _quotes, _l2 = [], [], []
    _bars = {"10s": [], "1m": [], "5m": [], "1d": []}
    _loaded_key = None
    _last_emit_ts = 0.0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _ts(row: dict[str, Any]) -> float:
    v = row.get("ts")
    return float(v) if isinstance(v, (int, float)) else 0.0


def session_dir(date: str, symbol: str) -> Path:
    return capture_root() / date / symbol.upper()


def load(date: str, symbol: str) -> dict[str, Any]:
    global _prints, _quotes, _l2, _bars, _loaded_key, _last_emit_ts
    key = f"{date}|{symbol.upper()}"
    root = session_dir(date, symbol)
    if not root.is_dir():
        reset_for_tests()
        return {"ok": False, "error": f"missing {root}", "key": key}
    _prints = sorted(_read_jsonl(root / "prints.jsonl"), key=_ts)
    _quotes = sorted(_read_jsonl(root / "quotes.jsonl"), key=_ts)
    _l2 = sorted(_read_jsonl(root / "l2.jsonl"), key=_ts)
    _bars = {
        "10s": sorted(_read_jsonl(root / "bars_10s.jsonl"), key=_ts),
        "1m": sorted(_read_jsonl(root / "bars_1m.jsonl"), key=_ts),
        "5m": sorted(_read_jsonl(root / "bars_5m.jsonl"), key=_ts),
        "1d": sorted(_read_jsonl(root / "bars_1d.jsonl"), key=_ts),
    }
    _loaded_key = key
    _last_emit_ts = 0.0
    first_ts = _ts(_prints[0]) if _prints else (_ts(_bars["1m"][0]) if _bars["1m"] else None)
    last_ts = _ts(_prints[-1]) if _prints else (_ts(_bars["1m"][-1]) if _bars["1m"] else None)
    logger.info("CAPTURE PLAY: loaded %s prints=%s l2=%s bars1m=%s", root, len(_prints), len(_l2), len(_bars["1m"]))
    return {
        "ok": True,
        "key": key,
        "dir": str(root),
        "counts": {
            "prints": len(_prints),
            "quotes": len(_quotes),
            "l2": len(_l2),
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


def _bars_from_prints(kind: str, limit: int, asof: float) -> list[dict[str, Any]]:
    step = {"10s": 10, "1m": 60, "5m": 300, "1d": 86400}.get(kind, 60)
    prints = [p for p in _prints if _ts(p) <= asof + 1e-6]
    if not prints:
        return []
    buckets: dict[int, dict[str, Any]] = {}
    for p in prints:
        ts = int(_ts(p))
        bts = ts - (ts % step)
        px = float(p.get("price") or 0)
        sz = float(p.get("size") or 0)
        cur = buckets.get(bts)
        if cur is None:
            buckets[bts] = {"ts": float(bts), "open": px, "high": px, "low": px, "close": px, "volume": sz}
        else:
            cur["high"] = max(cur["high"], px)
            cur["low"] = min(cur["low"], px)
            cur["close"] = px
            cur["volume"] += sz
    ordered = [buckets[k] for k in sorted(buckets)]
    cap = max(1, min(int(limit or 300), 2000))
    return [_to_chart_bar(r) for r in ordered[-cap:]]


def chart_bars(timeframe: str, limit: int) -> list[dict[str, Any]]:
    if not is_loaded():
        return []
    kind = _bar_tf(timeframe)
    rows = _bars.get(kind) or []
    asof = asof_unix()
    usable = [r for r in rows if _ts(r) <= asof + 1e-6]
    if not usable:
        return _bars_from_prints(kind, limit, asof)
    cap = max(1, min(int(limit or 300), 2000))
    return [_to_chart_bar(r) for r in usable[-cap:]]


def recent_prints(limit: int = 40) -> list[dict[str, Any]]:
    if not is_loaded():
        return []
    asof = asof_unix()
    rows = [p for p in _prints if _ts(p) <= asof + 1e-6]
    out: list[dict[str, Any]] = []
    for p in rows[-max(1, limit):]:
        ts = _ts(p)
        t_iso = datetime.fromtimestamp(ts, tz=ET).astimezone(timezone.utc).isoformat()
        out.append({
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
        })
    return out


def quote_at() -> dict[str, Any] | None:
    if not is_loaded():
        return None
    asof = asof_unix()
    qrows = [q for q in _quotes if _ts(q) <= asof + 1e-6]
    prows = [p for p in _prints if _ts(p) <= asof + 1e-6]
    last = float(prows[-1]["price"]) if prows else None
    bid = ask = None
    if qrows:
        q = qrows[-1]
        bid, ask = q.get("bid"), q.get("ask")
        if last is None and q.get("last") is not None:
            last = float(q["last"])
    elif prows:
        bid, ask = prows[-1].get("bid"), prows[-1].get("ask")
    if last is None:
        return None
    return {
        "last": last,
        "bid": float(bid) if bid is not None else last,
        "ask": float(ask) if ask is not None else last,
        "volume": None,
        "prev_close": None,
        "change_pct": None,
        "change_abs": None,
    }


def book_at() -> dict[str, Any] | None:
    if not is_loaded() or not _l2:
        return None
    asof = asof_unix()
    rows = [r for r in _l2 if _ts(r) <= asof + 1e-6]
    if not rows:
        return None
    r = rows[-1]
    return {"bids": r.get("bids") or [], "asks": r.get("asks") or [], "l1_fallback": False}


def prints_since(after_ts: float, until_ts: float) -> list[dict[str, Any]]:
    if not is_loaded():
        return []
    return [p for p in _prints if after_ts < _ts(p) <= until_ts + 1e-6]


def last_emit_ts() -> float:
    return _last_emit_ts


def mark_emitted(until_ts: float) -> None:
    global _last_emit_ts
    _last_emit_ts = max(_last_emit_ts, until_ts)


def seek_emit_cursor(asof: float) -> None:
    global _last_emit_ts
    _last_emit_ts = asof
