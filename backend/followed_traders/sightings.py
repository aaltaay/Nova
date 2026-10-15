"""When each trader was last on the stream's bar, and when the bar went on without them, from the feed's read log. Pure.

The feed closes a trade only when it reads the trader's slot without the position, so a trader whose show ends with a
position on the bar keeps it open all day. Off air every trade is closed (operator, 2026-10-14), so a trader's sighting
says when theirs closed (``view.closed_on_leaving``). No name or time is fixed here: whoever the bar reads -- the
regulars, the next show's hosts, someone standing in -- is who is on it. Shapes:
architecture/schema/followed-traders.md ("A trader who left the bar").
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from followed_traders.reads import clock_ts

# A name tag as a name: the reader's empty or garbled reads of a guest's caption are nobody (2026-10-14: 222 lines read
# the name "" off a guest's lower third).
NAME_TAG_RE = re.compile(r"^[A-Z][A-Z0-9]{1,15}$")


def sightings(log: list[dict[str, Any]], *, date: str, traders: Iterable[str], latest_clock: str | None,
              left_after_sec: float) -> dict[str, dict[str, float | None]]:
    """``{name: {last_ts, left_ts}}`` for each of ``traders`` the log read at least once (``feed.parse_reads``).

    Anyone else read on the bar counts as someone else, so a new host -- one standing in for a regular, with no trade
    yet -- shows the regular left as well as the next show's hosts do. ``latest_clock`` is the capture's on-screen
    clock when the day is today (the newest read, which the log only records when it changed), else None.
    """
    known = list(dict.fromkeys(traders))
    times = [clock_ts(date, line["clock"]) for line in log]
    newest = max([*times, *([clock_ts(date, latest_clock)] if latest_clock else [])], default=None)
    read = [{canonical(name, known) for name in line["traders"] if NAME_TAG_RE.match(name)} for line in log]
    last_line: dict[str, int] = {}
    for i, names in enumerate(read):
        for name in names:
            last_line[name] = i
    out: dict[str, dict[str, float | None]] = {}
    for name in known:
        i = last_line.get(name)
        if i is None:
            continue  # never read: no sighting, no claim
        last_ts = times[i + 1] if i + 1 < len(times) else newest
        if i + 1 < len(log) and log[i + 1].get("unread_before"):
            # The feed could not read the bar after their last line (a restart, a stream it could not use): they were
            # last seen at that line, and when they left is not known from there on (2026-10-15, 10:54 to 11:04).
            last_ts = times[i]
        # Every later line is without them, so any name on it is someone else on the bar.
        left_ts = next((times[j] for j in range(i + 1, len(read)) if read[j]), None)
        if left_ts is not None and (newest is None or newest - left_ts < left_after_sec):
            left_ts = None
        out[name] = {"last_ts": last_ts, "left_ts": left_ts}
    return out


def canonical(name: str, known: list[str]) -> str:
    """A name tag as read ("TJOE", "CHERLF") mapped onto one of ``known`` the way the feed's tracker maps it: a stray
    letter or two beside a short name, or one wrong letter in a name of five or more; else the name as read."""
    if not name or name in known:
        return name
    for k in known:
        if (k in name and len(name) - len(k) <= 2) or (len(k) >= 5 and _one_edit_apart(k, name)):
            return k
    return name


def _one_edit_apart(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))
