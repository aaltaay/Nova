"""What did the price do after a big seller (or buyer) on Level 2? (#984; the tracker is ``big_seller.py``)

The book watcher runs over a Session Record's books and prints (``hidden_study.read``, which also keeps the
mids and the counted prints), keeping every ``big`` event. Each called wall is measured from two moments: when
it was **called**, and when it **ended** (taken, pulled or out of view). Over each horizon: the mid's move in
basis points **toward a flush** -- down after a seller, up after a buyer -- and whether a counted print went
through the wall's price (the seller taken out, the buyer broken). A horizon past the end of its recorded
stretch is not measured, and a mid needs a book in the same stretch: a gap is never read as a price.

The groups: how the wall ended (``taken``, ``pulled``, ``lost``, or ``open`` when the recording ended first), and
how heavy it was against the stock's pace when called (``clear_sec`` under ``BREAKABLE_SEC`` against at or over
it; ``none`` without a pace). The **baseline** is the same recordings' every whole minute with a book, signed
the same way, so a flush is read against how the mid moved anyway. The group by how it ended looks ahead from
the call: it describes what came with each ending, never a rule anyone could have traded. Moves overlap
between events, so ``t`` (the mean over its standard error) is a guide, never a proof.

Pure apart from the recordings it is handed. Owner of no file; ``tools/big_seller_study.py`` prints it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from book_watch.hidden_study import Recorded, _break_after, _mid, _span_end, _stats
from book_watch.hidden_study import read as read_recording

SCHEMA_VERSION = 1
HORIZONS_SEC = (10, 30, 60, 300)
# A wall the last minute's lit volume would trade in under this many seconds is "breakable", else "heavy".
BREAKABLE_SEC = 60.0
ENDS = {"eaten": "taken", "pulled": "pulled", "lost": "lost"}
SIDES = ("ask", "bid")


@dataclass
class BigRecorded:
    """One recording: what ``hidden_study.read`` keeps, plus the walls' first and last words."""

    rec: Recorded
    called: list[dict[str, Any]] = field(default_factory=list)
    ended: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def date(self) -> str:
        return self.rec.date

    @property
    def symbol(self) -> str:
        return self.rec.symbol


def read(directory: Path, *, spans: list[tuple[float, float]] | None = None, num_rows: int = 10,
         restarts: Iterable[float] = ()) -> BigRecorded:
    """Run the watcher over one recording directory, keeping every big seller's and buyer's call and end. At each
    of ``restarts`` (``hidden_study.recording_restarts``) the watcher starts afresh: a wall seen before a recording
    gap is never held across it -- one shown at 10:00 and again at 10:20 would read as held for 20 minutes."""
    walls: list[dict[str, Any]] = []

    def keep(events: list[dict[str, Any]]) -> None:
        walls.extend(e for e in events if e.get("event") == "big")

    rec = read_recording(Path(directory), spans=spans, num_rows=num_rows, on_events=keep, restarts=restarts)
    out = BigRecorded(rec)
    for w in walls:
        if w["state"] == "holding":
            out.called.append(w)
        elif w["state"] in ENDS:
            out.ended[w["id"]] = w
    return out


def _toward(side: str, mid0: float, mid1: float) -> float:
    move = (mid1 - mid0) / mid0 * 1e4
    return -move if side == "ask" else move


def _measure(rec: Recorded, side: str, price: float, t0: float) -> dict[str, Any] | None:
    """From ``t0``: per horizon, the mid's move toward a flush and whether a print went through ``price``."""
    end = _span_end(rec, t0)
    if end is None:
        return None
    start = next(a for a, b in rec.spans if a <= t0 <= b)
    mid0 = _mid(rec, t0, start)
    brk = _break_after(rec, side, price, t0, max(HORIZONS_SEC))
    out: dict[str, Any] = {}
    for h in HORIZONS_SEC:
        if t0 + h > end:
            continue
        mid1 = _mid(rec, t0 + h, start)
        toward = _toward(side, mid0, mid1) if mid0 and mid1 else None
        out[str(h)] = {"broke": brk is not None and brk - t0 <= h, "flush_bp": toward}
    return out


def events(br: BigRecorded) -> list[dict[str, Any]]:
    """Every called wall of one recording, measured from its call and from its end."""
    out: list[dict[str, Any]] = []
    for w in br.called:
        t0 = w.get("called_ts")
        if t0 is None:
            continue
        end = br.ended.get(w["id"])
        clear = w.get("clear_sec")
        ev: dict[str, Any] = {
            "date": br.date, "symbol": br.symbol, "side": w["side"], "price": w["price"], "at": t0,
            "size": w["size_now"], "multiple": w.get("multiple"), "clear_sec": clear,
            "weight": "none" if clear is None else ("breakable" if clear < BREAKABLE_SEC else "heavy"),
            "ended": ENDS[end["state"]] if end else "open", "on_approach": end.get("on_approach") if end else None,
            "ended_at": end.get("ended_ts") if end else None,
            "from_call": _measure(br.rec, w["side"], w["price"], t0) or {},
            "from_end": (_measure(br.rec, w["side"], w["price"], end["ended_ts"]) or {})
            if end and end.get("ended_ts") is not None else {},
        }
        out.append(ev)
    return out


def baseline(recs: Iterable[BigRecorded]) -> dict[str, list[float]]:
    """Every whole minute with a book: the mid's move over each horizon, up positive (a seller's flush is -)."""
    moves: dict[str, list[float]] = {str(h): [] for h in HORIZONS_SEC}
    for br in recs:
        rec = br.rec
        for a, b in rec.spans:
            t = float(int(a) // 60 * 60 + 60)
            while t < b:
                mid0 = _mid(rec, t, a)
                for h in HORIZONS_SEC:
                    if t + h > b:
                        continue
                    mid1 = _mid(rec, t + h, a)
                    if mid0 and mid1:
                        moves[str(h)].append((mid1 - mid0) / mid0 * 1e4)
                t += 60.0
    return moves


def _block(rows: list[dict[str, Any]], anchor: str) -> dict[str, Any]:
    block: dict[str, Any] = {"n": len(rows), "horizons": {}}
    for h in HORIZONS_SEC:
        got = [e[anchor][str(h)] for e in rows if str(h) in e[anchor]]
        broke = [g["broke"] for g in got]
        flush = [g["flush_bp"] for g in got if g["flush_bp"] is not None]
        block["horizons"][str(h)] = {
            "measured": len(got),
            "broke_pct": round(100 * sum(broke) / len(broke), 1) if broke else None,
            "flushed_pct": round(100 * sum(1 for f in flush if f > 0) / len(flush), 1) if flush else None,
            "flush_bp": _stats(flush),
        }
    return block


def summarize(evs: list[dict[str, Any]]) -> dict[str, Any]:
    """Per side: every wall from its call, by how it ended (from the call and from the end), and by its weight."""
    out: dict[str, Any] = {}
    for side in SIDES:
        rows = [e for e in evs if e["side"] == side]
        out[side] = {
            "all": _block(rows, "from_call"),
            "by_end": {k: {"from_call": _block([e for e in rows if e["ended"] == k], "from_call"),
                           "from_end": _block([e for e in rows if e["ended"] == k], "from_end")}
                       for k in ("taken", "pulled", "lost", "open")},
            "on_approach": _block([e for e in rows if e["on_approach"] is True], "from_end"),
            "by_weight": {k: _block([e for e in rows if e["weight"] == k], "from_call")
                          for k in ("breakable", "heavy", "none")},
        }
    return out


def study(recs: Iterable[BigRecorded]) -> dict[str, Any]:
    recs = list(recs)
    evs = [e for r in recs for e in events(r)]
    base = baseline(recs)
    by_day: dict[str, list[dict[str, Any]]] = {}
    for e in evs:
        by_day.setdefault(e["date"], []).append(e)
    return {
        "schema_version": SCHEMA_VERSION,
        "horizons_sec": list(HORIZONS_SEC),
        "breakable_sec": BREAKABLE_SEC,
        "recordings": [{"date": r.date, "symbol": r.symbol, "books": r.rec.books, "prints": r.rec.prints,
                        "depth_hours": round(r.rec.depth_hours, 2), "walls": len(r.called)} for r in recs],
        "depth_hours": round(sum(r.rec.depth_hours for r in recs), 2),
        # Signed as a seller's flush (down positive); a buyer's is the same numbers with the sign turned.
        "baseline_seller": {h: {"flushed_pct": round(100 * sum(1 for m in v if m < 0) / len(v), 1) if v else None,
                                "flush_bp": _stats([-m for m in v])} for h, v in base.items()},
        "groups": summarize(evs),
        "by_day": {d: summarize(v) for d, v in sorted(by_day.items())},
        "events": evs,
    }
