"""The prints the PC already holds for a Time & Sales socket that asks (``?recent=<n>[&after=<seq>]``).

Operator report 2026-11-17: the phone's tape "was not moving". A socket got only the prints that arrived after it
opened, so a fresh screen sat empty on a stock that prints every 20 to 60 s, and a socket that dropped and came
back never got what it had missed. The line itself stays up with its lane (ADR 071), and every print it delivers
is kept in the sensor ring, so the PC can say what the socket did not see.

Only the line's own stretch is sent: prints received since the line last opened. An older print in the ring is from
before a gap that would not show on the tape. Wire: ``architecture/schema/execution.md``.
"""
from __future__ import annotations

from typing import Any, Mapping

from constants_tape import TAPE_RECENT_MAX


def asked(params: Mapping[str, Any]) -> tuple[int, int | None]:
    """``(n, after)`` from a socket's query: 0 when it did not ask; ``after`` None for the newest *n*."""
    n = _whole(params.get("recent"))
    if n is None or n <= 0:
        return 0, None
    return min(n, TAPE_RECENT_MAX), _whole(params.get("after"))


def _whole(raw: Any) -> int | None:
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return None


def held(symbol: str, n: int, after: int | None) -> list[dict[str, Any]]:
    """The prints to send, oldest first. Call it with the socket's queue, with no wait between (no print is then
    in both, and none in neither). Empty when the socket did not ask or the line's opening is unknown."""
    if n <= 0:
        return []
    from ibkr.tape_recording import producer_status
    from sensors import rings

    since = producer_status(symbol).get("line_since")
    if since is None:
        return []  # no line of this process: nothing here is proven to be one unbroken stretch
    rows = [p for p in rings.recent_prints(symbol) if _of_this_line(p, float(since))]
    if after is not None:
        rows = [p for p in rows if p["seq"] > after]
        return rows[-TAPE_RECENT_MAX:]
    return rows[-n:]


def _of_this_line(row: Mapping[str, Any], since: float) -> bool:
    """A live IBKR print with its place in the tape, received since the line opened (never a replay's print)."""
    if row.get("source") != "ibkr" or not isinstance(row.get("seq"), int):
        return False
    received = row.get("receive_ts")
    return isinstance(received, (int, float)) and received >= since
