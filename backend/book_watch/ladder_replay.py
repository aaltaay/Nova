"""The book watcher on a Sim replay ladder (#617, ADR 033 amendment).

Feeds the shared ``SymbolWatch`` detector over the loaded recording's own books and prints up to the
Sim playhead (never past it, and never calling ``flush()``) and supplies the same ``book_watch`` frame
contract to both the capture depth socket (``book_watch/ladder.py``) and the historical replay
snapshot (``sim/history_playback.py``).

Missing depth, missing tape, Level 1/NBBO-only windows, single-venue exchange books, pre-first-book
moments and recording gaps report ``watching: false`` with a plain-English ``reason`` and ``sides: None``,
never zero totals or guessed pulls/trades. No state carries across a recording gap or rewind.

Owner: this module's in-memory replay state (rebuilt on rewind, gap, jump or source change). Not persisted.
"""
from __future__ import annotations

import bisect
from collections import OrderedDict
import sqlite3
import threading
from typing import Any

from book_watch import live
from book_watch.book import lit_print
from book_watch.constants_book_watch import (
    BOOK_WATCH_BIG_REPLAY_LOOKBACK_SEC,
    BOOK_WATCH_IDLE_SEC,
    BOOK_WATCH_LADDER_MEMORY_SEC,
    BOOK_WATCH_MATCH_SLACK_SEC,
    BOOK_WATCH_NOTE,
    BOOK_WATCH_OFF_REASON,
    BOOK_WATCH_SCHEMA_VERSION,
    BOOK_WATCH_STATS_WINDOW_SEC,
)
from book_watch.detector import SymbolWatch

BOOK_WATCH_REPLAY_LOOKBACK_SEC = BOOK_WATCH_BIG_REPLAY_LOOKBACK_SEC
_HIST_CACHE_MAX = 64

_lock = threading.Lock()
_capture_state: dict[str, Any] | None = None
_epoch = 0
_hist_cache: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()


def _num_rows() -> int:
    from constants import IBKR_DEPTH_NUM_ROWS

    return int(IBKR_DEPTH_NUM_ROWS)


def _playhead_now() -> float:
    from sim import capture_player

    return capture_player.asof_unix()


def _big_float(symbol: str) -> dict[str, Any] | None:
    from book_watch.ladder import big_float

    return big_float(symbol)


def absent_frame(now: float, reason: str, *, source: str = "replay") -> dict[str, Any]:
    """A ``book_watch`` frame stating why annotations are unavailable at ``now``."""
    return {
        "schema_version": BOOK_WATCH_SCHEMA_VERSION, "source": source, "now": round(float(now), 3),
        "reset": True, "seq": 0, "watching": False, "reason": reason,
        "window_sec": BOOK_WATCH_STATS_WINDOW_SEC, "sides": None,
        "drops": [], "hidden": [], "big": [], "big_float": None, "note": BOOK_WATCH_NOTE,
    }


def _absent_view(now: float, reason: str) -> dict[str, Any]:
    return {"watching": False, "reason": reason, "now": float(now), "source": "replay"}


def _span_at(spans: list[Any], t: float) -> tuple[float, float] | None:
    for start, stop in spans:
        if start <= t <= stop:
            return float(start), float(stop)
        if start > t:
            break
    return None


def _start_capture(data: Any, playhead: float, stretch_start: float, lookback: float,
                   num_rows: int, epoch: int) -> dict[str, Any]:
    start = max(stretch_start, playhead - lookback)
    print_from = max(stretch_start, start - BOOK_WATCH_MATCH_SLACK_SEC)
    sym = str(data.symbol).upper()
    return {
        "data_id": id(data), "key": data.key, "symbol": sym, "span_start": stretch_start,
        "num_rows": num_rows, "epoch": epoch, "watch": SymbolWatch(sym, num_rows=num_rows),
        "fed_to": start, "book_i": bisect.bisect_left(data.l2_keys, start),
        "print_i": bisect.bisect_left(data.print_keys, print_from),
        "last_book_ts": None, "l1_fallback": False,
    }


def _feed_capture(st: dict[str, Any], data: Any, playhead: float) -> None:
    watch: SymbolWatch = st["watch"]
    bi, pi = st["book_i"], st["print_i"]
    b_end = bisect.bisect_right(data.l2_keys, playhead)
    p_end = bisect.bisect_right(data.print_keys, playhead)
    while bi < b_end or pi < p_end:
        if pi >= p_end or (bi < b_end and data.l2_keys[bi] <= data.print_keys[pi]):
            ts, row = float(data.l2_keys[bi]), data.l2[bi]
            bi += 1
            if row.get("l1_fallback") or row.get("recorded") is False:
                watch.tick(ts)
                watch.pending.clear()
                watch.big.lose_waiting("reset")
                watch.reset()
                st["l1_fallback"] = True
                st["last_book_ts"] = None
                continue
            if st["last_book_ts"] is not None and ts - st["last_book_ts"] > BOOK_WATCH_IDLE_SEC:
                watch.tick(ts)
                watch.reset()
            st["l1_fallback"] = False
            st["last_book_ts"] = ts
            watch.on_book(ts, row.get("bids") or [], row.get("asks") or [])
            continue
        ts, row = float(data.print_keys[pi]), data.prints[pi]
        pi += 1
        if st["last_book_ts"] is not None:
            watch.on_print(ts, row.get("price"), row.get("size"), lit=lit_print(row),
                           conditions=row.get("conditions"))
    watch.tick(playhead)
    st["book_i"], st["print_i"], st["fed_to"] = b_end, p_end, playhead


def _watch_view(watch: SymbolWatch, now: float, after_seq: int | None, after_hidden: int | None,
                *, epoch: int, force_reset: bool = False) -> dict[str, Any]:
    cutoff = now - BOOK_WATCH_LADDER_MEMORY_SEC
    if force_reset or after_seq is None or after_seq > watch.drop_seq:
        drops = [dict(d) for d in watch.drops if cutoff <= d["ts"] <= now]
    else:
        drops = [dict(d) for d in watch.drops if d["seq"] > after_seq and d["ts"] <= now]
    kept = watch.hidden.kept
    if force_reset or after_hidden is None or after_hidden > watch.hidden.seq:
        latest = {h["id"]: h for h in kept if h["ts"] <= now}
        hidden = sorted(
            (dict(h) for h in latest.values() if h["state"] == "holding" or h["ts"] >= cutoff),
            key=lambda h: h["seq"],
        )
    else:
        hidden = [dict(h) for h in kept if h["seq"] > after_hidden and h["ts"] <= now]
    big_got = watch.big.reading(now)
    return {
        "source": "replay", "now": now, "epoch": epoch, "seq": watch.drop_seq,
        "hidden_seq": watch.hidden.seq, "hidden": hidden,
        "big_version": watch.big.version, "big_holding": watch.big.holding(),
        "big_items": big_got["sellers"] + big_got["buyers"],
        "watching": watch.last_book_ts is not None and now - watch.last_book_ts <= BOOK_WATCH_IDLE_SEC,
        "reason": None, "window_sec": BOOK_WATCH_STATS_WINDOW_SEC,
        "sides": watch.side_totals(now), "drops": drops,
    }


def ladder_view(symbol: str, after_seq: int | None = None, now: float | None = None,
                after_hidden: int | None = None, *, num_rows: int | None = None,
                lookback: float = BOOK_WATCH_REPLAY_LOOKBACK_SEC,
                epoch: int | None = None) -> dict[str, Any]:
    """The replay ladder's view at ``now`` (default: the Sim playhead) for ``symbol``."""
    global _capture_state, _epoch
    sym = (symbol or "").strip().upper()
    playhead = float(_playhead_now() if now is None else now)
    if not live.enabled():
        return _absent_view(playhead, BOOK_WATCH_OFF_REASON)
    from sim import capture_player

    data = capture_player.snapshot()
    if data is None:
        return _absent_view(playhead, f"No Session Record of {sym} is loaded.")
    if str(data.symbol).upper() != sym:
        return _absent_view(playhead, f"No Session Record of {sym} is loaded ({data.symbol} is loaded).")
    if not data.l2:
        return _absent_view(playhead, f"The loaded Session Record of {sym} kept no Level 2 book.")
    if not data.prints:
        return _absent_view(
            playhead,
            f"The loaded Session Record of {sym} kept no Time & Sales prints, so book drops cannot be judged traded or pulled.",
        )
    spans = list(getattr(data, "spans", None) or [])
    if spans:
        span = _span_at(spans, playhead)
        if span is None:
            with _lock:
                _capture_state = None
            return _absent_view(playhead, "The playhead is between recorded stretches: nothing was recorded here.")
        stretch_start, stretch_stop = span
        if bisect.bisect_left(data.print_keys, stretch_start) >= bisect.bisect_right(data.print_keys, stretch_stop):
            return _absent_view(
                playhead,
                f"The loaded Session Record of {sym} kept no Time & Sales prints in this stretch, so book drops cannot be judged traded or pulled.",
            )
    else:
        stretch_start = float("-inf")

    b_first = bisect.bisect_left(data.l2_keys, stretch_start)
    b_end = bisect.bisect_right(data.l2_keys, playhead)
    if b_end <= b_first:
        return _absent_view(playhead, "The recording holds no Level 2 book at or before this moment yet.")

    rows = num_rows if num_rows is not None else _num_rows()
    with _lock:
        st = _capture_state
        if (st is None or st["data_id"] != id(data) or st["key"] != data.key
                or st["num_rows"] != rows or st["span_start"] != stretch_start
                or playhead < st["fed_to"] or playhead - st["fed_to"] > lookback):
            _epoch += 1
            st = _start_capture(data, playhead, stretch_start, lookback, rows, _epoch)
        _feed_capture(st, data, playhead)
        _capture_state = st
        if st["l1_fallback"]:
            return _absent_view(
                playhead,
                "Level 1 top-of-book only at this moment -- Level 2 depth is required to watch book pulls and trades.",
            )
        last = st["last_book_ts"]
        if last is None:
            return _absent_view(playhead, "The recording holds no Level 2 book at or before this moment yet.")
        age = playhead - last
        if age > BOOK_WATCH_IDLE_SEC:
            return _absent_view(playhead, f"The recording holds no Level 2 book for {age:.0f} s before the playhead.")
        force_reset = epoch is not None and epoch != st["epoch"]
        return _watch_view(st["watch"], playhead, after_seq, after_hidden, epoch=st["epoch"], force_reset=force_reset)


def _read_l2_archive_trades(symbol: str, start_ts: float, end_ts: float) -> list[dict[str, Any]]:
    """Replay-safe read of ``tape_trades`` from ``l2.db``: never flushes the live batch or creates the DB."""
    from l2.db import db_path, get_connection

    if not db_path().exists():
        return []
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT ts, receive_ts, price, size, exchange, conditions, unreported
            FROM tape_trades
            WHERE symbol = ? AND ts >= ? AND ts <= ?
            ORDER BY ts ASC
            """,
            (symbol.upper(), start_ts, end_ts),
        ).fetchall()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        if d.get("unreported") is not None:
            d["unreported"] = bool(d["unreported"])
        out.append(d)
    return out


def _selection_prints(selected: Any, start_ts: float, end_ts: float) -> list[dict[str, Any]]:
    """Prints from the historical selection inside ``[start_ts, end_ts]`` when ``tape_trades`` has none."""
    if selected is None or not selected.prints:
        return []
    lo = bisect.bisect_left(selected.keys, start_ts)
    hi = bisect.bisect_right(selected.keys, end_ts)
    return [dict(row) for row in selected.prints[lo:hi]]


def _contiguous_depth_stretch(snapshots: list[dict[str, Any]], session_id: str | None) -> list[dict[str, Any]]:
    """The unbroken stretch of depth snapshots ending at the last snapshot before ``cutoff``."""
    stretch: list[dict[str, Any]] = []
    for snap in reversed(snapshots):
        if snap.get("l1_fallback"):
            break
        if session_id is not None and snap.get("session_id") not in (None, session_id):
            break
        ts = float(snap["ts"])
        if stretch and float(stretch[-1]["ts"]) - ts > BOOK_WATCH_IDLE_SEC:
            break
        stretch.append(snap)
    stretch.reverse()
    return stretch


def historical_frame(symbol: str, selected: Any, cutoff: float, book: dict[str, Any] | None,
                     in_range: Any) -> dict[str, Any]:
    """The ``book_watch`` frame for ``GET /api/sim/history/snapshot/{symbol}`` at ``cutoff``."""
    sym = (symbol or "").strip().upper()
    now = float(cutoff)
    if not live.enabled():
        return absent_frame(now, BOOK_WATCH_OFF_REASON)
    if selected is None or str(selected.spec.get("symbol") or "").upper() != sym:
        return absent_frame(now, f"No historical replay of {sym} is loaded.")
    if book is None:
        return absent_frame(now, "Level 2 was not recorded for this moment.")
    source = book.get("source")
    if source == "massive_nbbo":
        return absent_frame(now, "Best bid / ask (NBBO) only -- the Massive files hold no Level 2 depth to watch.")
    if source == "exchange_book":
        return absent_frame(
            now,
            "Single-venue exchange book only -- book pulls and trades require consolidated Level 2 depth.",
        )
    if book.get("l1_fallback"):
        return absent_frame(
            now,
            "Level 1 top-of-book only at this moment -- Level 2 depth is required to watch book pulls and trades.",
        )

    cache_key = (id(selected), sym, book.get("session_id"), round(now, 3))
    with _lock:
        if cache_key in _hist_cache:
            _hist_cache.move_to_end(cache_key)
            return dict(_hist_cache[cache_key])

    try:
        from l2.store import get_snapshots_between

        start_ts = now - BOOK_WATCH_REPLAY_LOOKBACK_SEC
        snapshots = get_snapshots_between(sym, start_ts, now)
        stretch = _contiguous_depth_stretch(snapshots, book.get("session_id"))
        if not stretch or now - float(stretch[-1]["ts"]) > BOOK_WATCH_IDLE_SEC:
            frame = absent_frame(now, "Level 2 was not recorded for this moment.")
        else:
            stretch_start = float(stretch[0]["ts"])
            print_from = stretch_start - BOOK_WATCH_MATCH_SLACK_SEC
            prints = _read_l2_archive_trades(sym, print_from, now)
            if not prints and in_range is not None:
                prints = _selection_prints(selected, max(float(in_range[0]), print_from), now)
            if not prints:
                frame = absent_frame(
                    now,
                    "No Time & Sales prints were recorded for this moment, so book drops cannot be judged traded or pulled.",
                )
            else:
                watch = SymbolWatch(sym, num_rows=_num_rows())
                events: list[tuple[float, int, str, dict[str, Any]]] = [
                    (float(b["ts"]), 0, "book", b) for b in stretch
                ]
                for p in prints:
                    pts = p.get("receive_ts") if isinstance(p.get("receive_ts"), (int, float)) else p.get("ts")
                    if isinstance(pts, (int, float)) and pts <= now:
                        events.append((float(pts), 1, "print", p))
                events.sort(key=lambda item: (item[0], item[1]))
                for ts, _order, kind, row in events:
                    if kind == "book":
                        watch.on_book(ts, row.get("bids") or [], row.get("asks") or [])
                    else:
                        watch.on_print(ts, row.get("price"), row.get("size"), lit=lit_print(row),
                                       conditions=row.get("conditions"))
                watch.tick(now)
                view = _watch_view(watch, now, None, None, epoch=1, force_reset=True)
                frame = {
                    "schema_version": BOOK_WATCH_SCHEMA_VERSION, "source": "replay", "now": round(now, 3),
                    "reset": True, "seq": view["seq"], "watching": view["watching"], "reason": None,
                    "window_sec": view["window_sec"], "sides": view["sides"], "drops": view["drops"],
                    "hidden": view["hidden"], "big": view["big_items"], "big_float": _big_float(sym),
                    "note": BOOK_WATCH_NOTE,
                }
    except (sqlite3.Error, OSError, ImportError, ValueError, TypeError, KeyError):
        frame = absent_frame(now, "Recorded Level 2 archive is unavailable.")

    with _lock:
        _hist_cache[cache_key] = frame
        _hist_cache.move_to_end(cache_key)
        while len(_hist_cache) > _HIST_CACHE_MAX:
            _hist_cache.popitem(last=False)
    return dict(frame)


def clear_history_cache() -> None:
    with _lock:
        _hist_cache.clear()


def reset_for_tests() -> None:
    global _capture_state, _epoch
    with _lock:
        _capture_state = None
        _epoch = 0
        _hist_cache.clear()
