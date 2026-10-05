"""A live tape line gone silent, said in words (#722).

2026-10-05 09:35:42 ET: the AllLast lines of SAIQ (a Trader tab) and VEEA (a Session Record)
stopped together while both books kept updating, with no IBKR error and no farm notice. SAIQ's
Time & Sales sat on its last print under a LIVE badge until about 09:42, and the operator traded
it blind: "time and sale is fully frozen". The socket's only frame was its idle ``ping``.

A reading is ``{schema_version: 1, state: "halted" | "silent" | "quiet", since, last_print_ts,
book_at, halted, text}`` (epoch seconds; each ``null`` when not known), or ``None`` while the tape
prints:

* ``halted`` -- the symbol is halted now (``halt_status.halted_now``): a halt prints nothing, so
  this is never "the line may be down";
* ``silent`` -- no print for TAPE_SILENT_SEC while the line's Level 2 delivered a book within
  TAPE_SILENT_BOOK_FRESH_SEC: the tape line may be down. A quiet name looks the same, so the words
  say so and clear on the next print;
* ``quiet`` -- no print for TAPE_SILENT_SEC and the book is quiet too, or there is no Level 2
  line to compare.

The silence counts from the newest of the last print, the line's opening and the last moment the
symbol was seen halted (the caller keeps that one), so a reopening is not read as a dead line. A
reading is a description; nothing here asks IBKR for anything.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_tape import TAPE_SILENT_BOOK_FRESH_SEC, TAPE_SILENT_SEC

ET = ZoneInfo("America/New_York")

HALTED = "halted"
SILENT = "silent"
QUIET = "quiet"


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def _clock(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S ET")


def read(
    *,
    now: float,
    last_print_ts: float | None,
    line_since: float | None,
    book_at: float | None,
    halted: bool | None,
    halt_seen_at: float | None = None,
) -> dict[str, Any] | None:
    """The line's silence now, or None while it prints (pure)."""
    last = _num(last_print_ts)
    since = max(last or 0.0, _num(line_since) or 0.0, _num(halt_seen_at) or 0.0)
    if not since:
        return None
    book = _num(book_at)
    no_print = f"No prints since {_clock(last)}" if last else "No prints since the line opened"
    if halted is True:
        state = HALTED
        text = f"Halted: no prints until it reopens. {no_print}."
    elif now - since < TAPE_SILENT_SEC:
        return None
    elif book is not None and now - book <= TAPE_SILENT_BOOK_FRESH_SEC:
        state = SILENT
        text = (f"{no_print} while Level 2 kept updating: IBKR's tape line may be down. "
                "A quiet name looks the same; this clears on the next print.")
    elif book is not None:
        state = QUIET
        text = f"{no_print}; Level 2 is quiet too."
    else:
        state = QUIET
        text = f"{no_print}; no Level 2 line to compare with."
    return {
        "schema_version": 1,
        "state": state,
        "since": since,
        "last_print_ts": last,
        "book_at": book,
        "halted": halted,
        "text": text,
    }


def reading(symbol: str, *, now: float | None = None, halt_seen_at: float | None = None) -> dict[str, Any] | None:
    """``read`` for a live line from what Nova holds in memory: no IBKR request, no wait."""
    from ibkr import halt_status
    from ibkr.depth import state as depth_state
    from ibkr.tape_recording import producer_status

    sym = (symbol or "").strip().upper()
    ts = time.time() if now is None else float(now)
    producer = producer_status(sym)
    return read(
        now=ts,
        last_print_ts=producer.get("last_print_ts"),
        line_since=producer.get("line_since"),
        book_at=depth_state.last_book_at(sym),
        halted=halt_status.halted_now([sym], now=ts).get(sym),
        halt_seen_at=halt_seen_at,
    )
