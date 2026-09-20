"""Pipe Sim/SIM1 tape into session Record using sim_capture_v1 row shapes."""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_sim import SIM_SYMBOL

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


def _unix(ts: Any) -> float:
    if isinstance(ts, (int, float)) and ts > 0:
        return float(ts)
    if isinstance(ts, str) and ts.strip():
        raw = ts.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ET)
            return dt.timestamp()
        except ValueError:
            pass
    return time.time()


def _session_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=ET).strftime("%Y-%m-%d")


def _recording_this(symbol: str) -> bool:
    try:
        from capture.mode import capture_symbol, is_capture_mode
        from capture.recorder import is_recording

        if not is_capture_mode() or not is_recording():
            return False
        want = (capture_symbol() or "").upper()
        return bool(want) and want == symbol.upper()
    except Exception:
        return False


def emit_sim_tick(print_payload: dict[str, Any], quote: dict[str, Any] | None, book: dict[str, Any] | None) -> None:
    """Enqueue a complete Sim step; never perform disk I/O on the feed loop."""
    if not _recording_this(SIM_SYMBOL):
        return
    from capture.worker import session_token, submit

    token = session_token(SIM_SYMBOL)
    submit(_write_sim_tick, print_payload, quote, book, token=token)


def _write_sim_tick(print_payload: dict[str, Any], quote: dict[str, Any] | None, book: dict[str, Any] | None) -> None:
    try:
        from capture.recorder import record_l2, record_print, record_quote
    except Exception:
        return

    ts = _unix(print_payload.get("time"))
    day = _session_date(ts)
    px = float(print_payload.get("price") or 0)
    size = float(print_payload.get("size") or 1)
    bid = print_payload.get("bid")
    ask = print_payload.get("ask")

    record_print(
        {
            "symbol": SIM_SYMBOL,
            "ts": ts,
            "price": px,
            "size": size,
            "exchange": str(print_payload.get("exchange") or "SIM"),
            "conditions": str(print_payload.get("conditions") or "SIM"),
            "side": print_payload.get("side"),
            "bid": float(bid) if bid is not None else None,
            "ask": float(ask) if ask is not None else None,
            "seq": None,
            "receive_ts": time.time(),
            "source": "sim",
            "session_date": day,
        }
    )

    try:
        from capture.bar_buckets import on_print
        on_print(SIM_SYMBOL, ts, px, size, source="sim", session_date=day)
    except Exception:
        logger.exception("CAPTURE: Sim bar aggregation failed")
        raise



    q = quote or {}
    record_quote(
        {
            "symbol": SIM_SYMBOL,
            "ts": ts,
            "bid": float(q["bid"]) if q.get("bid") is not None else (float(bid) if bid is not None else None),
            "bid_size": q.get("bid_size"),
            "ask": float(q["ask"]) if q.get("ask") is not None else (float(ask) if ask is not None else None),
            "ask_size": q.get("ask_size"),
            "last": float(q["last"]) if q.get("last") is not None else px,
            "volume": q.get("volume"),
            "source": "sim",
            "session_date": day,
        }
    )

    if book:
        def _levels(side: str) -> list[dict[str, Any]]:
            rows = book.get(side) or []
            out: list[dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                p = row.get("price")
                s = row.get("size")
                if p is None:
                    continue
                out.append({"price": float(p), "size": float(s or 0)})
            return out

        record_l2(
            {
                "symbol": SIM_SYMBOL,
                "ts": ts,
                "bids": _levels("bids"),
                "asks": _levels("asks"),
                "source": "sim",
                "session_date": day,
            }
        )


def emit_sim_bar(timeframe: str, bar: dict[str, Any]) -> None:
    if not _recording_this(SIM_SYMBOL):
        return
    from capture.worker import session_token, submit

    token = session_token(SIM_SYMBOL)
    submit(_write_sim_bar, timeframe, bar, token=token)


def _write_sim_bar(timeframe: str, bar: dict[str, Any]) -> None:
    try:
        from capture.recorder import record_bar
    except Exception:
        return
    ts = _unix(bar.get("t") or bar.get("ts") or bar.get("time"))
    day = _session_date(ts)
    record_bar(
        timeframe,
        {
            "symbol": SIM_SYMBOL,
            "ts": ts,
            "open": float(bar.get("o") if bar.get("o") is not None else bar.get("open") or 0),
            "high": float(bar.get("h") if bar.get("h") is not None else bar.get("high") or 0),
            "low": float(bar.get("l") if bar.get("l") is not None else bar.get("low") or 0),
            "close": float(bar.get("c") if bar.get("c") is not None else bar.get("close") or 0),
            "volume": float(bar.get("v") if bar.get("v") is not None else bar.get("volume") or 0),
            "timeframe": "1m" if timeframe in ("1Min", "1min", "1m") else "10s",
            "source": "sim",
            "session_date": day,
        },
    )
