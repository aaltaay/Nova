"""Nova's own recorded IBKR sessions through the front door (ADR 059, #1064): Level 2 at a moment, prints in a window.

Three stores, all written by the live desk and only ever read here (shapes: ``architecture/schema/agent-desk.md``,
"Recorded sessions, Level 2 and tape through the front door"):

  capture   ``<NOVA_SIM_CAPTURE_DIR>/<day>/<SYMBOL>/`` -- a Session Record: ``manifest.json`` (its segments say where the
            recorder was up), ``l2.jsonl`` (books, at most 50 a second) and ``prints.jsonl``. ``recording_files.py``.
  l2_db     ``l2.db`` ``l2_snapshots`` -- depth sampled while a depth session was open. ``recording_stores.py``.
  archive   ``archive.db`` ``tape_ibkr`` -- every print the desk's tape line saw, 2026-07-15 on. ``recording_stores.py``.

Rules: as of the recording's own clock -- every time out is ET, every time in is ET; a book is never after the moment
asked, nor (in a Session Record) from before the gap that precedes it; a print's ``ts`` is when Nova *received* it
(``exchange_ts`` is IBKR's own whole second, Session Records only). Coverage is stated with every answer, never implied:
what the recording's own segments, sessions and first / last rows say it holds, and what it lost. Each read takes one
heavy-read slot (``slots.py``) and touches the stores read-only (``recording_stores.py``).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_reads import REPO, roots, slots  # noqa: F401  (REPO puts backend/ on sys.path)
from market_reads import recording_files as files
from market_reads import recording_stores as stores

from capture.constants_capture import CAPTURE_PLANNED_STOPS, CAPTURE_SOURCE_IBKR
from capture.segments import gap_rows, recorded_segments, segment_rows
from constants_archive_news import ARCHIVE_COUNTER_TAPE_DROPPED, ARCHIVE_DB_FILENAME
from constants_ibkr import L2_DB_FILENAME
from sale_conditions import row_sets_price, sets_price

ET = ZoneInfo("America/New_York")
DEPTH_SOURCES = ("auto", "capture", "l2_db")
TAPE_SOURCES = ("auto", "capture", "archive")
DEFAULT_MAX_AGE_SEC = 60.0
MAX_AGE_LIMIT_SEC = 3600.0
DEFAULT_ROWS = 200_000
MAX_ROWS = 1_000_000
RECORDED_DAYS = 30
TAPE_COLUMNS = ["time_et", "ts", "receive_ts", "exchange_ts", "price", "size", "exchange", "conditions", "unreported",
                "sets_price", "side", "bid", "ask", "source"]
DEPTH_RULES = ("the newest book at or before the moment asked, no older than max_age_sec; a Session Record is never "
               "read across a gap or outside its recorded stretches; l2_db skips top-of-book-only (l1_fallback) rows; "
               "auto serves the newer of the two stores (a tie: capture)")
TAPE_RULES = ("prints with ts in [start, end), oldest first; ts is when Nova received the print (ib_async stamps "
              "arrival), receive_ts when the desk processed it, exchange_ts IBKR's own whole second (Session Records "
              "only); side (ask | bid | between | unknown) / bid / ask are the desk's own judgement against the book "
              "it held at receipt -- unknown when none was usable, null on a row recorded before the field existed, "
              "never inferred from price; sets_price is the recorded verdict (capture) or judged from the "
              "conditions alone (archive does not store IBKR's unreported flag)")
UNITS = "prices dollars, sizes shares, ts epoch seconds, *_et Eastern time (HH:MM:SS.mmm; ISO with offset in coverage)"


def _day(day: str) -> tuple[date, float, float]:
    """``(date, first epoch, last epoch)`` of the ET calendar day (the folder the recorder files a print under)."""
    d = date.fromisoformat(day)
    return d, datetime(d.year, d.month, d.day, tzinfo=ET).timestamp(), \
        datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=ET).timestamp()


def _clock(day: date, text: str) -> float:
    """Epoch seconds of the ET wall time ``HH:MM[:SS[.fff]]`` on ``day``, built as a timezone-aware wall datetime (never
    midnight plus a duration: that is an hour off after a clock change). ``24:00`` alone is the day's end."""
    refusal = ValueError(f"{text!r} is not an ET clock time: HH:MM or HH:MM:SS (24:00 only as the end of the day)")
    parts = text.strip().split(":")
    try:
        if len(parts) not in (2, 3):
            raise refusal
        hours, minutes = int(parts[0]), int(parts[1])
        seconds = float(parts[2]) if len(parts) == 3 else 0.0
    except ValueError:
        raise refusal from None
    if (hours, minutes, seconds) == (24, 0, 0.0):
        return datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=ET).timestamp()
    if not (0 <= hours < 24 and 0 <= minutes < 60 and 0 <= seconds < 60):
        raise refusal
    # Seconds are added to the wall time, which cannot cross a clock change (those fall on the hour).
    return (datetime(day.year, day.month, day.day, hours, minutes, tzinfo=ET) + timedelta(seconds=seconds)).timestamp()


def _iso(ts: Any) -> Any:
    return datetime.fromtimestamp(float(ts), ET).isoformat(timespec="seconds") if isinstance(ts, (int, float)) else ts


def _time_et(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S.%f")[:-3]


def _symbol(symbol: str) -> str:
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise ValueError("a symbol is required")
    return symbol


def _merge(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, stop in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
        else:
            merged.append((start, stop))
    return merged


def _capture_state(symbol: str, day: str) -> dict[str, Any]:
    """The Session Record's folder, manifest, stretches and gaps; ``usable`` / ``problem`` say whether it can answer."""
    folder = files.session_dir(day, symbol)
    state: dict[str, Any] = {"folder": folder, "usable": False, "problem": None, "spans": [], "coverage": {
        "recorded": folder.is_dir(), "status": None, "stretches": [], "gaps": [], "fidelity": None}}
    if not folder.is_dir():
        state["problem"] = f"no Session Record of {symbol} on {day} (no {folder})"
        return state
    manifest, problem = files.read_manifest(folder)
    if problem and not manifest:
        state["problem"] = problem
        return state
    if manifest.get("source") not in (None, CAPTURE_SOURCE_IBKR):
        state["problem"] = "not a Session Record: synthetic data from the removed SIM1 instrument (ADR 019)"
        return state
    segments = recorded_segments(manifest, folder, live=False)
    rows = segment_rows(segments)
    fidelity = manifest.get("fidelity") if isinstance(manifest.get("fidelity"), dict) else {}
    losses = fidelity.get("tape_losses") if isinstance(fidelity.get("tape_losses"), list) else []
    stretches = [{"start_et": _iso(a), "stop_et": _iso(b), "status": seg.get("status"), "reason": seg.get("reason")}
                 for seg in segments if isinstance(seg, dict) for a, b, _ in segment_rows([seg])]
    state.update(usable=True, spans=_merge([(start, stop) for start, stop, _ in rows]))
    state["coverage"].update(
        status=manifest.get("status"), stretches=sorted(stretches, key=lambda row: row["start_et"]),
        gaps=[{"start_et": _iso(a), "stop_et": _iso(b), "reason": why, "planned": why in CAPTURE_PLANNED_STOPS}
              for a, b, why in gap_rows(segments)],
        fidelity={**{k: fidelity.get(k) for k in ("l2_offered", "l2_coalesced", "l2_max_hz", "tape_resubscribes",
                                                  "timestamp_regressions")},
                  "tape_losses": [{"at_et": _iso(row.get("at")), "cause": row.get("cause")}
                                  for row in losses if isinstance(row, dict)]})
    return state


def _stretch_start(spans: list[tuple[float, float]], at: float) -> float | None:
    return next((start for start, stop in spans if start <= at <= stop), None)


def _recorded_days(symbol: str, source: str, table: str | None = None) -> list[str]:
    """The newest days ``symbol`` is recorded in ``source`` (a stated absence says where to look instead)."""
    try:
        if source == "capture":
            root = roots.sim_capture()
            found = sorted((p.name for p in root.iterdir() if p.is_dir() and (p / symbol).is_dir()), reverse=True)
            return found[:RECORDED_DAYS]
        name = L2_DB_FILENAME if source == "l2_db" else ARCHIVE_DB_FILENAME
        with stores.connect(roots.cache_store(name)) as conn:
            return stores.recent_days(conn, table or "tape_ibkr", symbol, RECORDED_DAYS, ET)
    except (LookupError, OSError):  # maintainer: allow-swallow a store that is not here has no days to list
        return []


def _book(ts: float, bids: list[dict], asks: list[dict], at: float, source: str, **extra: Any) -> dict[str, Any]:
    def best_first(levels: list[dict], bid: bool) -> list[dict]:
        def key(level: dict) -> float:
            try:
                return -float(level["price"]) if bid else float(level["price"])
            except (KeyError, TypeError, ValueError):
                return float("inf")
        return sorted(levels, key=key)

    bids, asks = best_first(bids, True), best_first(asks, False)
    best_bid = float(bids[0]["price"]) if bids else None
    best_ask = float(asks[0]["price"]) if asks else None
    both = best_bid is not None and best_ask is not None
    return {"ts": ts, "time_et": _time_et(ts), "age_sec": round(at - ts, 3), "bids": bids, "asks": asks,
            "best_bid": best_bid, "best_ask": best_ask, "spread": round(best_ask - best_bid, 6) if both else None,
            "mid": round((best_ask + best_bid) / 2, 6) if both else None, "bid_levels": len(bids),
            "ask_levels": len(asks), "source": source, **extra}


def _depth_capture(symbol: str, day: str, at: float, min_ts: float) -> dict[str, Any]:
    state = _capture_state(symbol, day)
    out = {"source": "capture", "covered": False, "reason": state["problem"], "book": None,
           "coverage": state["coverage"]}
    if not state["usable"]:
        return out
    spans = state["spans"]
    start = _stretch_start(spans, at) if spans else None
    out["coverage"]["at_in_stretch"] = None if not spans else start is not None
    if spans and start is None:
        out["reason"] = f"{_iso(at)} is in a gap of the recording or outside it (see coverage.gaps / stretches)"
        return out
    row = files.newest_at_or_before(state["folder"] / "l2.jsonl", at, symbol)
    if row is None:
        out["reason"] = f"no book at or before {_iso(at)} in this Session Record's l2.jsonl"
        return out
    if row["ts"] < min_ts:
        out["reason"] = (f"the newest book at or before {_iso(at)} is from {_iso(row['ts'])}, "
                         f"{at - row['ts']:.0f} s earlier (max_age_sec)")
        return out
    if start is not None and row["ts"] < start:
        out["reason"] = "the newest book before that moment is from before the gap that precedes this recorded stretch"
        return out
    return {**out, "covered": True, "reason": None,
            "book": _book(row["ts"], row.get("bids") or [], row.get("asks") or [], at, "capture")}


def _depth_l2db(symbol: str, day: str, at: float, min_ts: float, lo: float, hi: float) -> dict[str, Any]:
    out: dict[str, Any] = {"source": "l2_db", "covered": False, "reason": None, "book": None, "coverage": None}
    try:
        path = roots.cache_store(L2_DB_FILENAME)
        with stores.connect(path) as conn:
            row = stores.book_at_or_before(conn, symbol, at, min_ts)
            first, last = stores.span(conn, "l2_snapshots", symbol, lo, hi)
            sessions, truncated = stores.sessions(conn, symbol, lo, hi)
            own = row and row["session_id"]
            if own and all(sess["session_id"] != own for sess in sessions):
                sessions = [*sessions, *filter(None, [stores.session(conn, own)])]   # the served book's own session
    except LookupError as exc:
        return {**out, "reason": str(exc)}
    out["coverage"] = {"first_ts": first, "first_et": _iso(first), "last_ts": last, "last_et": _iso(last),
                       "sessions": [{"session_id": s["session_id"], "reason": s["reason"], "setup": s["setup"],
                                     "started_et": _iso(s["started_ts"]), "ended_et": _iso(s["ended_ts"])}
                                    for s in sessions], "sessions_truncated": truncated, "where": str(path.parent)}
    if row is None:
        out["reason"] = (f"no depth snapshot of {symbol} within {at - min_ts:.0f} s before {_iso(at)}"
                         + ("" if first is not None else f"; none on {day} at all"))
        return out
    return {**out, "covered": True, "book": _book(row["ts"], row["bids"], row["asks"], at, "l2_db",
                                                  setup=row["setup"], session_id=row["session_id"])}


def depth(symbol: str, day: str, at: str, source: str = "auto", max_age_sec: float = DEFAULT_MAX_AGE_SEC) -> dict[str, Any]:
    """The Level 2 book of ``symbol`` at ET ``at`` (``HH:MM[:SS]``) on ``day``; see the module rules. Never raises for
    an unrecorded moment: ``covered`` is false and ``reason`` says why."""
    symbol = _symbol(symbol)
    if source not in DEPTH_SOURCES:
        raise ValueError(f"source must be one of {', '.join(DEPTH_SOURCES)}")
    if not 0 < float(max_age_sec) <= MAX_AGE_LIMIT_SEC:
        raise ValueError(f"max_age_sec must be above 0 and at most {MAX_AGE_LIMIT_SEC:.0f}")
    d, lo, hi = _day(day)
    at_ts = _clock(d, at)
    min_ts = at_ts - float(max_age_sec)
    with slots.heavy(f"recorded_depth {symbol} {day} {at}"):
        tried = []
        if source in ("auto", "capture"):
            tried.append(_depth_capture(symbol, day, at_ts, min_ts))
        if source in ("auto", "l2_db"):
            tried.append(_depth_l2db(symbol, day, at_ts, min_ts, lo, hi))
    found = [t for t in tried if t["covered"]]
    best = max(found, key=lambda t: (t["book"]["ts"], t["source"] == "capture"), default=None)
    answer = {"symbol": symbol, "day": day, "at": at, "at_et": _iso(at_ts), "covered": best is not None,
              "source": best["source"] if best else None, "book": best["book"] if best else None,
              "reason": None if best else "; ".join(f"{t['source']}: {t['reason']}" for t in tried),
              "tried": [{"source": t["source"], "covered": t["covered"], "reason": t["reason"],
                         "book_ts": t["book"]["ts"] if t["book"] else None,
                         "book_et": _iso(t["book"]["ts"]) if t["book"] else None,
                         "age_sec": t["book"]["age_sec"] if t["book"] else None} for t in tried],
              "coverage": {t["source"]: t["coverage"] for t in tried}, "rules": DEPTH_RULES, "units": UNITS}
    if best is None:
        answer["recorded_days"] = {t["source"]: _recorded_days(symbol, t["source"], "l2_snapshots") for t in tried}
    return answer


def _tape_frame(rows: list[dict], source: str) -> pd.DataFrame:
    if source == "capture":
        records = [{"ts": r["ts"], "receive_ts": r.get("receive_ts"), "exchange_ts": r.get("exchange_ts"),
                    "price": r.get("price"), "size": r.get("size"), "exchange": r.get("exchange"),
                    "conditions": r.get("conditions"), "unreported": bool(r.get("unreported")),
                    "sets_price": row_sets_price(r), "side": r.get("side"), "bid": r.get("bid"), "ask": r.get("ask")}
                   for r in rows]
    else:
        records = [{"ts": r["ts"], "receive_ts": r["receive_ts"], "exchange_ts": None, "price": r["price"],
                    "size": r["size"], "exchange": r["exchange"] or None, "conditions": r["conditions"] or None,
                    "unreported": None, "sets_price": sets_price(r["conditions"]), "side": r["side"],
                    "bid": r["bid"], "ask": r["ask"]} for r in rows]
    frame = pd.DataFrame.from_records(records, columns=[c for c in TAPE_COLUMNS if c not in ("time_et", "source")])
    frame.insert(0, "time_et", [_time_et(t) for t in frame["ts"]])
    frame["source"] = source
    return frame


def _covered_share(spans: list[tuple[float, float]], lo: float, hi: float) -> float | None:
    if not spans:
        return None
    inside = sum(max(0.0, min(b, hi) - max(a, lo)) for a, b in spans)
    return round(inside / (hi - lo), 4) if hi > lo else None


def tape(symbol: str, day: str, start: str | None = None, end: str | None = None, source: str = "auto",
         limit: int = DEFAULT_ROWS) -> pd.DataFrame:
    """``symbol``'s prints on ``day`` between ET ``start`` (inclusive) and ``end`` (exclusive), oldest first; the whole
    ET day without them. ``attrs`` carry the source served, ``coverage``, ``rules`` and ``units``."""
    symbol = _symbol(symbol)
    if source not in TAPE_SOURCES:
        raise ValueError(f"source must be one of {', '.join(TAPE_SOURCES)}")
    if not 0 < int(limit) <= MAX_ROWS:
        raise ValueError(f"limit must be 1 to {MAX_ROWS}")
    d, day_lo, day_hi = _day(day)
    lo = _clock(d, start) if start else day_lo
    hi = _clock(d, end) if end else day_hi
    if hi <= lo:
        raise ValueError("end must be after start")
    note = None
    with slots.heavy(f"recorded_tape {symbol} {day}"):
        state = _capture_state(symbol, day) if source in ("auto", "capture") else None
        has_capture = bool(state and state["usable"] and (state["folder"] / "prints.jsonl").is_file()
                           and (state["folder"] / "prints.jsonl").stat().st_size > 0)
        served = "capture" if source == "capture" or (source == "auto" and has_capture) else "archive"
        if served == "capture":
            rows, capped = ([], False) if not has_capture else files.rows_between(
                state["folder"] / "prints.jsonl", lo, hi, int(limit), symbol)
            coverage = {**state["coverage"], "covered_share": _covered_share(state["spans"], lo, hi)}
            where = str(state["folder"])
            if not has_capture:
                note = state["problem"] or "this Session Record holds no prints"
            elif source == "auto" and state["coverage"]["gaps"]:
                note = ("the Session Record has gaps (coverage.gaps); source='archive' may hold prints the recording "
                        "missed")
        else:
            try:
                path = roots.cache_store(ARCHIVE_DB_FILENAME)
                with stores.connect(path) as conn:
                    rows, capped = stores.tape_rows(conn, symbol, lo, hi, int(limit))
                    first, last = stores.span(conn, "tape_ibkr", symbol, lo, hi)
                    dropped = stores.counter(conn, ARCHIVE_COUNTER_TAPE_DROPPED)
            except LookupError as exc:
                rows, capped, first, last, dropped, path = [], False, None, None, None, None
                note = str(exc)
            coverage = {"first_ts": first, "first_et": _iso(first), "last_ts": last, "last_et": _iso(last),
                        "dropped_total": dropped,
                        "gaps": "not recorded: the archive is a write log and marks no gap of its own -- a quiet "
                                "stretch and a lost tape line look alike (a Session Record of the symbol-day states "
                                "its gaps)"}
            where = None if path is None else str(path.parent)
    frame = _tape_frame(rows, served)
    frame.attrs.update(symbol=symbol, day=day, start=start, end=end, window_et=[_iso(lo), _iso(hi)], source=served,
                       capped=capped, where=where, coverage=coverage, rules=TAPE_RULES, units=UNITS)
    if note:
        frame.attrs["note"] = note
    if not len(frame):
        frame.attrs["recorded_days"] = {served: _recorded_days(symbol, served)}
    return frame
