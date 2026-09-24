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
from capture.constants_capture import CAPTURE_L2_LOAD_LIMIT, CAPTURE_NOT_IBKR_REASON
from capture.schema import read_manifest
from capture.sessions import is_ibkr_source
from ibkr.depth.book import sort_levels
from sale_conditions import row_sets_price, tape_flags
from sim.capture_charts import chart_bars  # noqa: F401 -- the player's chart API (split out)
from sim.capture_spans import load_spans, newest_in_span, recording_here, span_start
from sim.capture_reader import read_jsonl as _read_jsonl, usable_rows, new_diagnostics, sample_l2
from sim.prior_close import previous_close, recorded_close

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

@dataclass
class CaptureData:
    key: str
    symbol: str
    prints: list[dict]
    quotes: list[dict]
    l2: list[dict]
    print_keys: list[float]
    quote_keys: list[float]
    l2_keys: list[float]
    # Candles built from the prints, per timeframe (``capture_charts``; stored bar files are never read, #535).
    print_bar_cache: dict = field(default_factory=dict)
    # The prints that set a price, filtered once on the first chart read (``capture_charts``).
    price_prints: list | None = None
    last_emit: float = 0.0
    # Recorded stretches ``[(start, stop)]``; empty means unknown (every read unbounded).
    spans: list = field(default_factory=list)
    # The replayed session's previous close (``sim.prior_close``: the recorded tick 9 first); None unknown.
    prev_close: float | None = None


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
        if not is_ibkr_source(_manifest):
            # ADR 019 removed the synthetic instrument; its old directories are not recordings (C21).
            return failure(CAPTURE_NOT_IBKR_REASON, diagnostics)
        def read(name: str, kind: str) -> list[dict]:
            return usable_rows(_read_jsonl(root / (name + ".jsonl"), diagnostics), kind, symbol, diagnostics)
        prints = read("prints", "prints")
        quotes = read("quotes", "quotes")
        l2 = sample_l2(read("l2", "l2"), CAPTURE_L2_LOAD_LIMIT, diagnostics)
    except ValueError as exc:
        return failure(str(exc), diagnostics)
    if not prints and not quotes:
        return failure("Capture contains no usable prints or quotes; "
                       f"discarded {diagnostics['malformed_rows']} malformed, "
                       f"{diagnostics['invalid_timestamp_rows']} invalid timestamp and "
                       f"{diagnostics['invalid_rows']} invalid payload rows", diagnostics)
    state = CaptureData(key, symbol.upper(), prints, quotes, l2,
                        [_ts(r) for r in prints], [_ts(r) for r in quotes], [_ts(r) for r in l2])
    event_keys = state.print_keys + state.quote_keys
    first_ts, last_ts = min(event_keys), max(event_keys)
    segments, state.spans = load_spans(_manifest, root, live=recording_here(root),
                                       first_ts=first_ts, last_ts=last_ts)
    state.prev_close = previous_close(symbol, date, recorded=recorded_close(quotes, date))
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
        },
        "first_ts": first_ts,
        "last_ts": last_ts,
        # Recorded stretches (with why each ended) so the scrubber can draw
        # them against the session and a gap as a gap -- the one still being
        # written included (``stopped_et`` null while this process records it,
        # C41) and data written past the last segment (``unlisted``, R13).
        "segments": segments,
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


def _asof_index(keys: list[float], asof: float) -> int:
    if not keys:
        return -1
    return bisect.bisect_right(keys, asof) - 1


def _bounded_index(keys: list[float], state: CaptureData, t: float) -> int:
    """Newest row at or before ``t`` -- inside ``t``'s recorded stretch when stretches are known."""
    return newest_in_span(keys, state.spans, t) if state.spans else _asof_index(keys, t)


def _span_floor(keys: list[float], state: CaptureData, t: float) -> int:
    """First row index inside ``t``'s stretch (0 when stretches are unknown)."""
    start = span_start(state.spans, t) if state.spans else None
    return bisect.bisect_left(keys, start) if start is not None else 0


def covered(asof: float | None = None, *, state: CaptureData | None = None) -> bool:
    """The moment falls inside a recorded stretch (always, when stretches are unknown)."""
    state = state or _state
    if state is None:
        return False
    t = asof if asof is not None else asof_unix()
    return not state.spans or span_start(state.spans, t) is not None


def has_prints() -> bool:
    state = _state
    return bool(state and state.prints)


def recent_prints(limit: int = 40, *, state: CaptureData | None = None) -> list[dict[str, Any]]:
    state = state or _state
    if state is None or not state.prints:
        return []
    asof = asof_unix()
    # The tape is the playhead's own stretch: in a gap it is empty, and it never
    # reaches back across the gap before it (R11).
    i = _bounded_index(state.print_keys, state, asof + 1e-6)
    if i < 0:
        return []
    cap = max(1, int(limit))
    floor = _span_floor(state.print_keys, state, asof)
    chunk = state.prints[max(floor, i - cap + 1) : i + 1]
    return [_print_payload(p) for p in chunk]


def _print_payload(p: dict[str, Any]) -> dict[str, Any]:
    ts = _ts(p)
    return {
        "type": "print",
        "symbol": str(p.get("symbol") or "").upper(),
        "time": datetime.fromtimestamp(ts, tz=ET).astimezone(timezone.utc).isoformat(),
        "price": float(p.get("price") or 0),
        "size": int(p["size"]) if p.get("size") is not None else None,
        "exchange": str(p.get("exchange") or ""),
        "conditions": str(p.get("conditions") or ""),
        **tape_flags(p),
        "side": p.get("side"),
        "bid": p.get("bid"),
        "ask": p.get("ask"),
    }


def last_trade(*, state: CaptureData | None = None) -> dict[str, Any] | None:
    """The newest print at the playhead that sets a price, as a tape payload; ``None`` in a gap.

    An odd lot or an average-price print is on the tape but never the capture's
    last trade (#511): the quote card's latest trade reads this, not the newest print.
    """
    state = state or _state
    if state is None or not state.prints:
        return None
    asof = asof_unix()
    i = _bounded_index(state.print_keys, state, asof + 1e-6)
    floor = _span_floor(state.print_keys, state, asof)
    while i >= max(0, floor):
        if row_sets_price(state.prints[i]):
            return _print_payload(state.prints[i])
        i -= 1
    return None


def quote_at(asof: float | None = None, *, state: CaptureData | None = None) -> dict[str, Any] | None:
    state = state or _state
    if state is None:
        return None
    t = asof if asof is not None else asof_unix()
    if state.quotes:
        i = _bounded_index(state.quote_keys, state, t)
        if i >= 0:
            row = state.quotes[i]
            # The recorder's quote rows carry the top of book, not a last (R12):
            # the last is the newest reported print, never a zero.
            recorded_last = row.get("last") or row.get("price")
            last = float(recorded_last) if recorded_last else last_print_at(t, state=state)
            return {
                "symbol": str(row.get("symbol") or "").upper(),
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "last": last,
                # One previous close per load, whichever row is read (#542).
                "prev_close": state.prev_close,
                "bid_size": row.get("bid_size"),
                "ask_size": row.get("ask_size"),
                "volume": row.get("volume"),
                "ts": _ts(row),
                "source": "capture",
            }
    i = _bounded_index(state.print_keys, state, t)
    if i < 0:
        return None
    row = state.prints[i]
    px = float(row.get("price") or 0)
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "bid": row.get("bid"),
        "ask": row.get("ask"),
        "last": px,
        "prev_close": state.prev_close,
        "bid_size": None,
        "ask_size": None,
        "volume": None,
        "ts": _ts(row),
        "source": "capture",
    }


def last_print_at(asof: float, *, state: CaptureData | None = None) -> float | None:
    """Price of the last print that sets a price at or before ``asof``, inside its recorded stretch.

    A volume-only print -- odd lot, average price, derivatively priced, or
    flagged ``unreported`` (``sale_conditions``; R24, #511) -- never sets the
    last, and a gap has none (R11): a practice order is refused there.
    """
    state = state or _state
    if state is None or not state.prints:
        return None
    i = _bounded_index(state.print_keys, state, asof)
    floor = _span_floor(state.print_keys, state, asof)
    while i >= max(0, floor):
        row = state.prints[i]
        if row_sets_price(row):
            return float(row["price"])
        i -= 1
    return None


def book_at(asof: float | None = None, *, state: CaptureData | None = None) -> dict[str, Any] | None:
    state = state or _state
    if state is None or not state.l2:
        return None
    t = asof if asof is not None else asof_unix()
    i = _bounded_index(state.l2_keys, state, t)
    if i < 0:
        if not state.spans:
            return None
        # Nothing recorded for this moment (a gap, or before this stretch's first
        # book): an explicit empty book, so the last one never stands in for it (R11).
        return {"symbol": state.symbol, "bids": [], "asks": [], "ts": t,
                "source": "capture", "recorded": False}
    row = state.l2[i]
    # Books recorded before #540 can be out of price order (ib_async's row
    # handling); best price first, so the ladder and the top of book are right.
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "bids": sort_levels(list(row.get("bids") or []), bid=True),
        "asks": sort_levels(list(row.get("asks") or []), bid=False),
        "ts": _ts(row),
        "source": "capture",
    }


def replay_quote(*, state: CaptureData | None = None) -> dict[str, Any] | None:
    """The loaded capture's market at the playhead, for the Sim clock payload (R10).

    The quote head and the ticket read it on every clock poll, so a seek moves
    them with the playhead. In a gap ``covered`` is false and every price is
    null -- a stated absence, never the market from before the gap.
    """
    state = state or _state
    if state is None:
        return None
    t = asof_unix()
    inside = covered(t, state=state)
    quote = quote_at(t, state=state) if inside else None
    return {
        "symbol": state.symbol,
        "ts": t,
        "covered": inside,
        "last": last_print_at(t, state=state) if inside else None,
        "bid": quote.get("bid") if quote else None,
        "ask": quote.get("ask") if quote else None,
        "bid_size": quote.get("bid_size") if quote else None,
        "ask_size": quote.get("ask_size") if quote else None,
        "prev_close": state.prev_close,
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
