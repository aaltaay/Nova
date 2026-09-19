"""L2 book, spread, flow, and liquidity adapters."""
from __future__ import annotations

import time
from typing import Any

from constants_sensors import (
    SENSOR_BOOK_LEVELS,
    SENSOR_FLOW_SWEEP_MIN_PRINTS,
    SENSOR_TICK_DOLLARS,
)
from l2 import features as l2_features
from sensors import rings
from sensors.envelope import build_envelope
from sensors.feeds import get_book, get_prints, get_quote, peek_avg_volume


def _levels(side: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in side[:n]:
        try:
            out.append(
                {
                    "price": float(row.get("price")),
                    "size": float(row.get("size") or 0),
                    "mm": row.get("mm"),
                }
            )
        except (TypeError, ValueError):
            continue
    return out


def _spread_ticks(spread: float | None) -> float | None:
    if spread is None:
        return None
    return round(spread / SENSOR_TICK_DOLLARS, 4)


def _book_rates(symbol: str) -> dict[str, Any]:
    hist = rings.recent_books(symbol)
    if len(hist) < 2:
        return {
            "replenish_events": 0,
            "cancel_events": 0,
            "window_sec": None,
            "replenish_per_sec": None,
            "cancel_per_sec": None,
            "spoof_hints": [],
            "note": "Need at least two book snapshots (open Trader L2 or poll).",
        }
    first, last = hist[0], hist[-1]
    window = max(0.001, float(last["ts"]) - float(first["ts"]))
    replenish = 0
    cancel = 0
    vanished: list[dict[str, Any]] = []
    prev_map: dict[tuple[str, float], float] = {}
    for snap in hist:
        cur: dict[tuple[str, float], float] = {}
        for side in ("bids", "asks"):
            for row in snap.get(side) or []:
                try:
                    key = (side, float(row.get("price")))
                    size = float(row.get("size") or 0)
                except (TypeError, ValueError):
                    continue
                cur[key] = size
                prior = prev_map.get(key)
                if prior is None:
                    if size > 0:
                        replenish += 1
                elif size > prior:
                    replenish += 1
                elif size < prior:
                    cancel += 1
                    if prior >= 100 and size <= 0:
                        vanished.append({"side": side, "price": key[1], "from_size": prior})
        prev_map = cur
    return {
        "replenish_events": replenish,
        "cancel_events": cancel,
        "window_sec": round(window, 3),
        "replenish_per_sec": round(replenish / window, 4),
        "cancel_per_sec": round(cancel / window, 4),
        "spoof_hints": vanished[-5:],
        "note": "Hints only -- size that appeared then dropped to 0. Not a detection.",
    }


def read_l2(symbol: str) -> dict[str, Any]:
    book, source = get_book(symbol)
    if not book:
        return build_envelope(
            sensor="l2",
            symbol=symbol,
            status="live",
            data={},
            error="No L2 book. Open Trader on this symbol, or enable Sim for SIM1.",
        )
    feat = l2_features.compute_feature_dict(book)
    spread = feat.get("spread")
    data = {
        "source": source,
        "imbalance": feat.get("imbalance"),
        "bid_total": feat.get("bid_total"),
        "ask_total": feat.get("ask_total"),
        "bid_heavy": feat.get("bid_heavy"),
        "ask_stacked": feat.get("ask_stacked"),
        "spread_dollars": spread,
        "spread_ticks": _spread_ticks(spread),
        "tick_dollars": SENSOR_TICK_DOLLARS,
        "bids": _levels(list(book.get("bids") or []), SENSOR_BOOK_LEVELS),
        "asks": _levels(list(book.get("asks") or []), SENSOR_BOOK_LEVELS),
        "l1_fallback": bool(book.get("l1_fallback")),
        **_book_rates(symbol),
    }
    return build_envelope(sensor="l2", symbol=symbol, status="live", data=data)


def read_spread(symbol: str) -> dict[str, Any]:
    book, source = get_book(symbol)
    if not book:
        return build_envelope(
            sensor="spread",
            symbol=symbol,
            status="live",
            data={},
            error="No book for spread. Open Trader L2 or Sim SIM1.",
        )
    current = l2_features.spread(book)
    hist = rings.recent_books(symbol)
    minute_ago = None
    now = time.time()
    for snap in reversed(hist):
        if now - float(snap["ts"]) >= 60:
            minute_ago = l2_features.spread(snap)
            break
    if minute_ago is None and len(hist) >= 2:
        minute_ago = l2_features.spread(hist[0])
    direction = None
    if current is not None and minute_ago is not None:
        if current > minute_ago:
            direction = "widening"
        elif current < minute_ago:
            direction = "narrowing"
        else:
            direction = "unchanged"
    return build_envelope(
        sensor="spread",
        symbol=symbol,
        status="live",
        data={
            "source": source,
            "spread_dollars": current,
            "spread_ticks": _spread_ticks(current),
            "prior_spread_dollars": minute_ago,
            "direction": direction,
            "tick_dollars": SENSOR_TICK_DOLLARS,
            "window": "last_minute_or_oldest_snapshot",
        },
    )


def _print_side(row: dict[str, Any]) -> str:
    side = str(row.get("side") or "").lower()
    if side in ("ask", "buy"):
        return "ask"
    if side in ("bid", "sell"):
        return "bid"
    return "unknown"


def read_flow(symbol: str) -> dict[str, Any]:
    prints, tape_source = get_prints(symbol)
    book, book_source = get_book(symbol)
    sides = [_print_side(p) for p in prints]
    sweep = None
    if len(sides) >= SENSOR_FLOW_SWEEP_MIN_PRINTS:
        tail = [s for s in sides[-SENSOR_FLOW_SWEEP_MIN_PRINTS:] if s in ("ask", "bid")]
        if len(tail) >= SENSOR_FLOW_SWEEP_MIN_PRINTS and len(set(tail)) == 1:
            sweep = {"side": tail[0], "prints": len(tail)}
    rates = _book_rates(symbol)
    iceberg = bool(rates.get("replenish_events")) and bool(prints)
    return build_envelope(
        sensor="flow",
        symbol=symbol,
        status="live",
        data={
            "tape_source": tape_source,
            "book_source": book_source,
            "print_count": len(prints),
            "sweep": sweep,
            "iceberg_hint": iceberg,
            "replenish_after_hit": bool(rates.get("replenish_events")),
            "replenish_events": rates.get("replenish_events"),
            "cancel_events": rates.get("cancel_events"),
            "has_book": book is not None,
            "note": "Observations from existing tape/book rings. No new IB subscription.",
        },
        error=None if (prints or book) else "No tape or book yet for flow events.",
    )


def read_liquidity(symbol: str) -> dict[str, Any]:
    avg = peek_avg_volume(symbol)
    book, source = get_book(symbol)
    spread = l2_features.spread(book) if book else None
    quote, q_source = get_quote(symbol)
    allowlisted = False
    try:
        from bot.persist import load_session

        names = [str(s).upper() for s in (load_session().get("symbol_allowlist") or [])]
        allowlisted = symbol in names
    except Exception:
        allowlisted = False
    return build_envelope(
        sensor="liquidity",
        symbol=symbol,
        status="live",
        data={
            "adv": avg,
            "adv_source": "fundamentals_cache" if avg is not None else None,
            "typical_spread_dollars": spread,
            "typical_spread_note": (
                "Current book spread only -- no historical typical-spread series."
            ),
            "liquid_allowlist": allowlisted,
            "allowlist_source": "bot.symbol_allowlist",
            "book_source": source,
            "quote_source": q_source,
            "last": (quote or {}).get("price") or (quote or {}).get("last"),
        },
        error=None if (avg is not None or book or quote) else "No ADV cache, book, or quote.",
    )
