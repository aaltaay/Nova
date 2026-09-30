"""Run the book watcher over a Session Record (ADR 033): the same detector as live.

Reads ``l2.jsonl`` and ``prints.jsonl`` from one recording directory, merged in
arrival order (a book row's ``ts`` is its receipt; a print's ``receive_ts``,
else ``ts``). Recordings made before ADR 033 kept at most 8 books a second, so
their drops span longer gaps: the replay says how many books it read per second.
A print's sale conditions ride along, so a cross print is never counted hidden
(hidden.py).
"""
from __future__ import annotations

import heapq
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from book_watch.book import lit_print
from book_watch.detector import SymbolWatch


def _rows(path: Path, kind: str) -> Iterator[tuple[float, int, str, dict[str, Any]]]:
    if not path.is_file():
        return
    order = 0 if kind == "book" else 1
    with path.open("rb") as stream:
        for raw in stream:
            try:
                row = json.loads(raw)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(row, dict):
                continue
            ts = row.get("receive_ts") if kind == "print" else None
            ts = ts if isinstance(ts, (int, float)) else row.get("ts")
            if not isinstance(ts, (int, float)):
                continue
            yield float(ts), order, kind, row


def merged_rows(directory: Path) -> Iterator[tuple[float, int, str, dict[str, Any]]]:
    """A recording's books and prints in arrival order: (ts, order, "book" | "print", row)."""
    directory = Path(directory)
    return heapq.merge(_rows(directory / "l2.jsonl", "book"), _rows(directory / "prints.jsonl", "print"),
                       key=lambda item: (item[0], item[1]))


def feed(watch: SymbolWatch, kind: str, ts: float, row: dict[str, Any]) -> list[dict[str, Any]]:
    """One recorded row into a watch, as the live worker hands it one."""
    if kind == "book":
        return watch.on_book(ts, row.get("bids") or [], row.get("asks") or [])
    return watch.on_print(ts, row.get("price"), row.get("size"), lit=lit_print(row),
                          conditions=row.get("conditions"))


def replay(directory: Path, *, num_rows: int = 10, symbol: str | None = None) -> dict[str, Any]:
    """Every pull, flag, hidden stretch and minute the watcher would have raised, plus totals."""
    directory = Path(directory)
    sym = (symbol or directory.name).upper()
    watch = SymbolWatch(sym, num_rows=num_rows)
    events: list[dict[str, Any]] = []
    first = last = None
    for ts, _order, kind, row in merged_rows(directory):
        first = ts if first is None else first
        last = ts
        events += feed(watch, kind, ts, row)
    events += watch.flush()
    span = (last - first) if first is not None and last is not None else 0.0
    minutes = [e for e in events if e["event"] == "minute"]
    return {
        "symbol": sym, "dir": str(directory), "first_ts": first, "last_ts": last,
        "books": watch.books, "prints": watch.prints_seen,
        "books_per_sec": round(watch.books / span, 2) if span > 0 else None,
        "pulled_shares": sum(m["pulled_shares"] for m in minutes),
        "filled_shares": sum(m["filled_shares"] for m in minutes),
        "pulls": sum(m["pulls"] for m in minutes), "fills": sum(m["fills"] for m in minutes),
        "large_pulls": [e for e in events if e["event"] == "pull"],
        "drops": [e for e in events if e["event"] == "drop"],
        "flags": [e for e in events if e["event"] == "flag"],
        # The last word on each hidden seller or buyer (every update is an event; the newest wins).
        "hidden": list({e["id"]: e for e in events if e["event"] == "hidden"}.values()),
        "minutes": minutes,
    }
