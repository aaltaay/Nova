"""Claude's eye (ADR 068 decision 12): every symbol the scanner follows at once, spikes first.

Read-only, over what Nova already holds -- the scanner's rows (``runtime_state``, ``scanner_surface``), the setup
scanner's universe (HOD Momo's active set), IBKR's Level 1 lines (``ibkr.ticks``) and the Level 1 samples
``hod_momo_metrics`` keeps (each the day volume and the last that came with it). Nothing here opens a line or
asks IBKR for anything.

Owner: the spike events (in memory; a restart starts the list empty). A symbol is listed once when it starts spiking
and again only after it stopped; the watcher scans every ``AGENT_EYE_SCAN_SEC`` while the seat is on, and every read
scans too.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from agent_trader.constants_agent_trader import (
    AGENT_EYE_EVENTS_KEEP,
    AGENT_EYE_EVENTS_MAX_AGE_SEC,
    AGENT_EYE_SCAN_SEC,
    AGENT_EYE_SPIKE_MIN_DOLLARS,
    AGENT_EYE_SPIKE_MOVE_PCT,
    AGENT_EYE_SPIKE_SECONDS,
    AGENT_EYE_WAIT_MAX_SEC,
    AGENT_EYE_WINDOWS_SEC,
    AGENT_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

_CATALYST_KEYS = ("verdict", "category", "strength", "title", "published_ts")
_lock = threading.Lock()
_events: list[dict[str, Any]] = []
_spiking: set[str] = set()
_scanned_at = 0.0


def reset_for_tests() -> None:
    global _scanned_at
    with _lock:
        _events.clear()
        _spiking.clear()
        _scanned_at = 0.0


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out > 0 else None


def universe() -> dict[str, list[str]]:
    """symbol -> the lists it is on: every live Gappers, Gainers and After Hours row, and the setups universe."""
    from hod_momo_active import get_active_symbols
    from runtime_state import get_runtime_state

    state = get_runtime_state()
    out: dict[str, list[str]] = {}
    tables = (("gappers", state.gapper_cache), ("gainers", state.gainer_cache),
              ("afterhours", state.afterhours_cache))
    for name, rows in tables:
        for row in rows or []:
            sym = str(row.get("symbol") or "").strip().upper()
            if sym and name not in out.setdefault(sym, []):
                out[sym].append(name)
    for sym in get_active_symbols():
        sym = str(sym or "").strip().upper()
        if sym and "setups" not in out.setdefault(sym, []):
            out[sym].append("setups")
    return out


def _scanner_rows(symbols: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    """The scanner's own row for each symbol (a bare one for the setups-only), decorated as every client sees it:
    blocklisted symbols are left out, float and halt filled in."""
    from runtime_state import get_runtime_state
    from scanner_surface import surface_rows

    state = get_runtime_state()
    rows: dict[str, dict[str, Any]] = {}
    for table in (state.afterhours_cache, state.gainer_cache, state.gapper_cache):   # a Gappers row wins
        for row in table or []:
            sym = str(row.get("symbol") or "").strip().upper()
            if sym in symbols:
                rows[sym] = row
    bare = [{"symbol": s} for s in symbols if s not in rows]
    return {str(r.get("symbol") or "").upper(): r for r in surface_rows([*rows.values(), *bare])}


def _windows(sym: str, now: float) -> dict[str, dict[str, Any] | None]:
    from hod_momo_metrics import window_trades

    out: dict[str, dict[str, Any] | None] = {}
    for seconds in AGENT_EYE_WINDOWS_SEC:
        read = window_trades(sym, seconds, now)
        if read is None:
            out[str(seconds)] = None
            continue
        then, last, shares, dollars = read
        out[str(seconds)] = {"pct": (last / then - 1.0) * 100.0, "shares": shares, "dollars": dollars}
    return out


def spike_of(window: dict[str, Any] | None) -> dict[str, Any] | None:
    """The spike rule on the 60-second window: a move this large either way, with this much traded."""
    if not window or window.get("pct") is None or window.get("dollars") is None:
        return None
    pct, dollars = float(window["pct"]), float(window["dollars"])
    if abs(pct) < AGENT_EYE_SPIKE_MOVE_PCT or dollars < AGENT_EYE_SPIKE_MIN_DOLLARS:
        return None
    return {"direction": "up" if pct > 0 else "down", "pct": pct, "dollars": dollars}


def _row(sym: str, lists: list[str], scanner: dict[str, Any], quote: dict[str, Any], now: float) -> dict[str, Any]:
    from agent_trader import bands
    from catalysts import board
    from constants_ibkr import IBKR_QUOTE_QUALITY_CLOSE_FALLBACK
    from ibkr import ticks

    last = None if quote.get("quote_quality") == IBKR_QUOTE_QUALITY_CLOSE_FALLBACK else _num(quote.get("price"))
    prev = _num(quote.get("prev_close")) or _num(scanner.get("previous_close")) or _num(scanner.get("prev_close"))
    bid, ask = (_num(v) for v in ticks.bid_ask(sym))
    spread = ask - bid if bid is not None and ask is not None and ask >= bid else None
    windows = _windows(sym, now)
    stamped = {"symbol": sym}
    board.stamp_row(stamped)
    catalyst = stamped.get("catalyst")
    return {
        "symbol": sym, "lists": lists, "last": last, "prev_close": prev,
        "day_pct": (last / prev - 1.0) * 100.0 if last is not None and prev is not None else None,
        "windows": windows, "spike": spike_of(windows.get(str(AGENT_EYE_SPIKE_SECONDS))),
        "float_shares": scanner.get("float_shares"), "bid": bid, "ask": ask, "spread": spread,
        "spread_pct": spread / ((ask + bid) / 2.0) * 100.0 if spread is not None else None,
        "halted": scanner.get("halted"), "luld": bands.of(sym, last),
        "catalyst": {k: catalyst.get(k) for k in _CATALYST_KEYS} if isinstance(catalyst, dict) else None,
    }


def rank_key(row: dict[str, Any]) -> tuple:
    """Spikes first (largest move first), then the 60-second move's size, then the day move."""
    spike = row.get("spike")
    win = (row.get("windows") or {}).get(str(AGENT_EYE_SPIKE_SECONDS)) or {}
    move = win.get("pct")
    day = row.get("day_pct")
    return (spike is None, -abs(spike["pct"]) if spike else 0.0, move is None, -abs(move or 0.0),
            day is None, -(day or 0.0), row["symbol"])


def rows(now: float | None = None) -> list[dict[str, Any]]:
    """Every symbol's row, ranked."""
    from ibkr import ticks

    t = time.time() if now is None else float(now)
    symbols = universe()
    scanner = _scanner_rows(symbols)
    quotes = ticks.last_quotes(list(scanner))
    out = []
    for sym, row in scanner.items():
        try:
            out.append(_row(sym, symbols.get(sym, []), row, quotes.get(sym) or {}, t))
        except Exception:
            logger.warning("AGENT eye: %s could not be read", sym, exc_info=True)
    return sorted(out, key=rank_key)


def note_spikes(ranked: list[dict[str, Any]], now: float) -> None:
    """List each symbol once when it starts spiking; forget events past their age."""
    with _lock:
        live = {r["symbol"] for r in ranked if r.get("spike")}
        for r in ranked:
            if r.get("spike") and r["symbol"] not in _spiking:
                _events.append({"symbol": r["symbol"], "at": now, "direction": r["spike"]["direction"],
                                "pct": r["spike"]["pct"], "dollars": r["spike"]["dollars"], "last": r.get("last")})
        _spiking.clear()
        _spiking.update(live)
        kept = [e for e in _events if now - float(e["at"]) <= AGENT_EYE_EVENTS_MAX_AGE_SEC]
        _events[:] = kept[-AGENT_EYE_EVENTS_KEEP:]


def events() -> list[dict[str, Any]]:
    """Spike events, newest first."""
    with _lock:
        return [dict(e) for e in reversed(_events)]


def scan(now: float | None = None) -> list[dict[str, Any]]:
    global _scanned_at
    t = time.time() if now is None else float(now)
    ranked = rows(t)
    note_spikes(ranked, t)
    _scanned_at = t
    return ranked


def scan_due(now: float) -> bool:
    return now - _scanned_at >= AGENT_EYE_SCAN_SEC


def view(ranked: list[dict[str, Any]], now: float) -> dict[str, Any]:
    from agent_trader import lines

    return {
        "schema_version": AGENT_SCHEMA_VERSION, "generated_at": now, "source": "ibkr",
        "rule": {"move_pct": AGENT_EYE_SPIKE_MOVE_PCT, "seconds": AGENT_EYE_SPIKE_SECONDS,
                 "min_dollars": AGENT_EYE_SPIKE_MIN_DOLLARS},
        "line": lines.held_symbol(), "universe": len(ranked), "spikes": events(), "symbols": ranked,
    }


async def eye(wait: float = 0.0, after: float | None = None) -> dict[str, Any]:
    """The eye now; with ``wait``, once a spike event newer than ``after`` is listed or ``wait`` runs out."""
    deadline = time.monotonic() + min(max(float(wait), 0.0), AGENT_EYE_WAIT_MAX_SEC)
    since = time.time() if after is None else float(after)
    while True:
        t = time.time()
        ranked = await asyncio.to_thread(scan, t)
        if wait <= 0 or time.monotonic() >= deadline or any(float(e["at"]) > since for e in events()):
            return view(ranked, t)
        await asyncio.sleep(AGENT_EYE_SCAN_SEC)
