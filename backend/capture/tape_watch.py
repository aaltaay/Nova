"""A recording's tape line: found dead, asked for again, said so (#525).

2026-09-23: auto-record held IPDN and WHLR; at 09:46:40 both recordings' prints
stopped while their quotes and Level 2 kept coming until 10:00, and nothing
said so. A recording's AllLast line ends two ways Nova can see:

* IBKR ends it -- an error on its request id (``ibkr.tape_line``). The line is
  dropped, so the producer reads ``disconnected`` and carries ``ended``;
* it goes silent -- no print for CAPTURE_TAPE_STALE_SEC while the book updated
  within CAPTURE_TAPE_BOOK_FRESH_SEC. A quiet name looks the same, so asking
  again is harmless there; it backs off (CAPTURE_TAPE_RESUBSCRIBE_MIN_SEC) over
  a streak of outages, and a streak is one shout, not one per outage.

Either way the tape -- only the tape; the depth line is left alone -- is asked
for again once IB's 15 s same-instrument rule allows, and the outage is said:
a WARNING, a ``capture_stopped`` row with reason ``tape`` that reads resumed
once a print arrives on the new line, ``reacquired`` on the session, and the
manifest's ``fidelity.tape_losses`` / ``tape_resubscribes``.

This module decides; ``capture.keepalive`` acts (it owns the status rows and
the IBKR calls). State is process memory, one entry per recording symbol.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from capture.constants_capture import (
    CAPTURE_RESUME_BACKOFF_SEC,
    CAPTURE_TAPE_BOOK_FRESH_SEC,
    CAPTURE_TAPE_RENEW_DELAY_SEC,
    CAPTURE_TAPE_RESUBSCRIBE_MIN_SEC,
    CAPTURE_TAPE_STALE_SEC,
)

ET = ZoneInfo("America/New_York")

# Causes, as the manifest's ``tape_losses[].cause`` names them.
CAUSE_IB_ERROR = "ib_error"
CAUSE_STALE = "stale"

# What ``observe`` asks the keepalive to do.
LOST = "lost"          # an outage opened: say so (and drop the line when ``end``)
END = "end"            # asked again, still silent: drop the line once more
RENEW = "renew"        # IB's rule allows it: ask for the tape again
RESUMED = "resumed"    # a print arrived on the new line: the outage is over


@dataclass
class Verdict:
    kind: str
    cause: str | None = None
    detail: str | None = None
    end: bool = False
    repeat: bool = False  # the same streak as the last outage: one shout, not another


@dataclass
class _Line:
    lost_at: float | None = None      # when this outage was found; None while none is open
    cause: str | None = None
    detail: str | None = None
    renew_at: float | None = None     # ask again at or after this
    renewed_at: float | None = None   # the last successful ask in this outage
    failures: int = 0                 # failed asks in this outage
    streak: int = 0                   # asks in this streak of outages: the backoff step
    quiet_until: float = 0.0          # no new silence verdict before this
    resumed_at: float | None = None   # when the last outage ended


_lines: dict[str, _Line] = {}


def reset_for_tests() -> None:
    _lines.clear()


def forget(symbol: str | None = None) -> None:
    """The operator stopped (or started) it, or it stopped recording: start clean."""
    if symbol is None:
        _lines.clear()
    else:
        _lines.pop(symbol.strip().upper(), None)


def keep_only(recording: list[str]) -> None:
    """Drop the state of symbols no longer recording."""
    for sym in [s for s in _lines if s not in recording]:
        _lines.pop(sym, None)


def in_outage(symbol: str) -> bool:
    """True while this watch is bringing the symbol's tape back (the Gateway branch stays out)."""
    line = _lines.get(symbol.strip().upper())
    return bool(line and line.lost_at is not None)


def status(symbol: str) -> dict[str, Any] | None:
    line = _lines.get(symbol.strip().upper())
    if line is None or line.lost_at is None:
        return None
    return {"lost_at": line.lost_at, "cause": line.cause, "detail": line.detail,
            "renew_at": line.renew_at, "renewed_at": line.renewed_at, "failures": line.failures}


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def _clock(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S ET")


def _silence(producer: dict[str, Any], book: dict[str, Any], now: float) -> str | None:
    """Why the line looks dead -- prints silent while the book moves -- else None."""
    since = max(_num(producer.get("last_print_ts")) or 0.0, _num(producer.get("line_since")) or 0.0)
    book_ts = _num(book.get("last_book_ts"))
    if not since or book_ts is None:
        return None
    silent, book_age = now - since, now - book_ts
    if silent < CAPTURE_TAPE_STALE_SEC or book_age > CAPTURE_TAPE_BOOK_FRESH_SEC:
        return None
    last = _num(producer.get("last_print_ts"))
    what = f"No prints since {_clock(last)} ({silent:.0f}s)" if last else f"No prints for {silent:.0f}s"
    return (f"{what} while the book kept updating ({book_age:.0f}s ago) -- the IBKR tape line looks dead; "
            "asking for it again. A quiet name looks the same: this clears on the next print")


def _ended_detail(ended: dict[str, Any]) -> str:
    code = ended.get("code")
    return f"IBKR ended the tape line (error {code}: {ended.get('message')}) -- asking for it again"


def observe(symbol: str, *, now: float, entry: dict[str, Any]) -> Verdict | None:
    """One look at a recording's tape. ``entry`` is its ``capture.mode.status_payload()`` session."""
    line = _lines.setdefault(symbol.strip().upper(), _Line())
    producer = entry.get("producer") or {}
    book = entry.get("book") or {}
    ended = producer.get("ended") if producer.get("state") == "disconnected" else None
    last_print = _num(producer.get("last_print_ts"))

    if line.lost_at is None:
        if ended:
            repeat = _open(line, now, CAUSE_IB_ERROR, _ended_detail(ended))
            line.renew_at = max(now, (_num(ended.get("at")) or now) + CAPTURE_TAPE_RENEW_DELAY_SEC, line.quiet_until)
            return Verdict(LOST, CAUSE_IB_ERROR, line.detail, end=False, repeat=repeat)
        if producer.get("state") == "disconnected" or now < line.quiet_until:
            return None  # a Gateway drop is the keepalive's; a quiet name waits its turn
        detail = _silence(producer, book, now)
        if detail is None:
            return None
        repeat = _open(line, now, CAUSE_STALE, detail)
        line.renew_at = now + CAPTURE_TAPE_RENEW_DELAY_SEC
        return Verdict(LOST, CAUSE_STALE, detail, end=True, repeat=repeat)

    # The dead line was dropped when the outage opened, so a later print on a line
    # that is up came on a new one -- ours, or one a Time & Sales panel opened first.
    back = last_print is not None and last_print >= (line.renewed_at or line.lost_at)
    if back and producer.get("state") != "disconnected":
        # The backoff outlives the outage: a thin name that prints now and then
        # must not be dropped, asked for and shouted about every 90 s.
        line.lost_at = line.cause = line.detail = line.renew_at = line.renewed_at = None
        line.failures, line.resumed_at = 0, now
        return Verdict(RESUMED)
    if line.renew_at is not None:
        return Verdict(RENEW) if now >= line.renew_at else None
    if ended:
        # The new line died too (e.g. IB's tick-by-tick cap again): wait out the backoff.
        line.detail = _ended_detail(ended)
        line.renew_at = max(now + CAPTURE_TAPE_RENEW_DELAY_SEC, line.quiet_until)
        return None
    if now < line.quiet_until:
        return None
    detail = _silence(producer, book, now)
    if detail is None:
        return None
    line.detail = detail
    line.renew_at = now + CAPTURE_TAPE_RENEW_DELAY_SEC
    return Verdict(END, CAUSE_STALE, detail, end=True)


def _open(line: _Line, now: float, cause: str, detail: str) -> bool:
    """Open an outage; True when it continues the last one's streak."""
    repeat = line.resumed_at is not None and now - line.resumed_at <= CAPTURE_TAPE_RESUBSCRIBE_MIN_SEC[-1]
    if not repeat:
        line.streak = 0
    line.lost_at, line.cause, line.detail = now, cause, detail
    line.renewed_at, line.failures = None, 0
    return repeat


def renewed(symbol: str, *, now: float, error: str | None) -> float | None:
    """The keepalive asked again. On failure, when to retry (epoch); on success, None."""
    line = _lines.get(symbol.strip().upper())
    if line is None or line.lost_at is None:
        return None
    if error:
        line.failures += 1
        step = min(line.failures - 1, len(CAPTURE_RESUME_BACKOFF_SEC) - 1)
        line.renew_at = now + CAPTURE_RESUME_BACKOFF_SEC[step]
        return line.renew_at
    step = min(line.streak, len(CAPTURE_TAPE_RESUBSCRIBE_MIN_SEC) - 1)
    line.streak += 1
    line.renewed_at, line.renew_at, line.failures = now, None, 0
    line.quiet_until = now + CAPTURE_TAPE_RESUBSCRIBE_MIN_SEC[step]
    return None
