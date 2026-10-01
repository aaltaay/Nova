"""Which clock each EDGAR ``acceptanceDateTime`` is on. Pure: no I/O.

SEC's bulk submissions JSON writes every acceptance time with a ``Z``. Most rows are UTC, but some
filers' JSON holds Eastern wall time behind the same ``Z`` -- about 30% of 2021's filings, 0.5% of
2026's. Read as UTC those rows land 4-5 hours early, often in the wrong session: an after-close
release reads as intraday. The clock belongs to a filer's JSON, not to the filing (one filing filed
for several co-registrants can read UTC in one of their JSON files and Eastern in another), and
within one JSON it comes in long runs. A row is placed by the first of:

  1. its own time. EDGAR accepts filings 06:00-22:00 ET and dates one accepted after 17:30 ET on
     the next business day (Regulation S-T Rule 13):
       hours        a raw 06:00 up to 10:00 (EDT dates) / 11:00 (EST) is before 06:00 ET read as
                    UTC, so it is Eastern; a raw 22:00 up to 02:00 / 03:00 is after 22:00 ET read
                    as Eastern, so it is UTC
       filing date  a raw 17:31 up to 21:30 / 22:30 is before 17:30 ET read as UTC (dated that
                    day) and after it read as Eastern (dated the next weekday). Only forms dated by
                    the 17:30 rule vote: Forms 3/4/5 and Schedules 13D/G are dated the same day
                    until 22:00.
  2. its neighbours: the majority of the rows rule 1 placed in the same JSON part within 180 days,
     then 730 days, then the whole part (a tie is no majority);
  3. the majority of the filer's other parts, else UTC, the clock of most rows in every year.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC, EASTERN = "utc", "et"
NEIGHBOUR_DAYS = (180, 730)
EVIDENCE = ("hours", "filing_date", "near_180d", "near_730d", "part", "filer", "default")  # what places a row, strongest first

# Forms dated by the 17:30 ET rule. A list, not "everything but Forms 3/4/5 and 13D/G": a form with
# its own cutoff (a Rule 462(b) registration, S-1MEF, is dated the same day until 22:00) must not vote.
DATED_BY_1730 = frozenset({
    "8-K", "8-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A", "6-K", "6-K/A", "20-F", "20-F/A", "40-F", "40-F/A",
    "10-D", "10-D/A", "11-K", "NT 10-K", "NT 10-Q", "DEF 14A", "DEFA14A", "PRE 14A", "DEFM14A", "DEF 14C",
    "PRE 14C", "S-1", "S-1/A", "S-3", "S-3/A", "S-3ASR", "S-4", "S-4/A", "S-8", "S-8 POS", "POS AM", "F-1",
    "F-1/A", "F-3", "F-4", "424B1", "424B2", "424B3", "424B4", "424B5", "424B7", "FWP", "425", "SC TO-T",
    "SC TO-I", "SC TO-C", "SC 14D9", "8-A12B", "8-A12G", "15-12B", "15-12G", "15-15D",
})

Row = tuple[str, str, str | None]   # (form, raw acceptanceDateTime, filingDate) as the JSON holds them


@lru_cache(maxsize=None)
def _behind(day: str) -> int:
    """Hours Eastern time is behind UTC on an ISO date: 4 (EDT) or 5 (EST)."""
    noon = datetime.fromisoformat(day).replace(hour=12, tzinfo=ET)
    return -int(noon.utcoffset().total_seconds()) // 3600


@lru_cache(maxsize=None)
def _weekday_after(day: str) -> tuple[bool, str]:
    """(``day`` is a weekday, the next weekday) for an ISO date."""
    d = date.fromisoformat(day)
    n = d + timedelta(days=1)
    while n.weekday() >= 5:
        n += timedelta(days=1)
    return d.weekday() < 5, n.isoformat()


def own_clock(form: str, raw: str, filing_date: str | None) -> tuple[str, str]:
    """``(clock, rule)`` from one row's own raw time and filing date; ``('', '')`` when it cannot say."""
    if len(raw) < 19:
        return "", ""
    day, hm = raw[:10], raw[11:16]
    h = _behind(day)
    if "06:00" <= hm < f"{6 + h:02d}:00":
        return EASTERN, "hours"
    if hm >= "22:00" or hm < f"{h - 2:02d}:00":
        return UTC, "hours"
    if filing_date and form in DATED_BY_1730 and "17:31" <= hm < f"{17 + h}:30":
        weekday, nxt = _weekday_after(day)
        if weekday and filing_date == day:
            return UTC, "filing_date"
        if weekday and filing_date == nxt:
            return EASTERN, "filing_date"
    return "", ""


def _majority(n: int, n_et: int) -> str:
    if 2 * n_et > n:
        return EASTERN
    if 2 * n_et < n:
        return UTC
    return ""


class _Part:
    """One JSON part's rows, with the ones their own time placed kept by day for neighbour votes."""

    def __init__(self, rows: list[Row]):
        self.rows = rows
        self.own = [own_clock(*r) for r in rows]
        votes = sorted((date.fromisoformat(r[1][:10]).toordinal(), c == EASTERN)
                       for r, (c, _) in zip(rows, self.own, strict=True) if c)
        self.days = [d for d, _ in votes]
        self.et_before = [0]          # et_before[k]: Eastern votes among the first k
        for _, is_et in votes:
            self.et_before.append(self.et_before[-1] + is_et)

    def neighbours(self, raw: str) -> tuple[str, str]:
        day = date.fromisoformat(raw[:10]).toordinal()
        for span in NEIGHBOUR_DAYS:
            lo, hi = bisect_left(self.days, day - span), bisect_right(self.days, day + span)
            clock = _majority(hi - lo, self.et_before[hi] - self.et_before[lo])
            if clock:
                return clock, f"near_{span}d"
        clock = _majority(len(self.days), self.et_before[-1])
        return (clock, "part") if clock else ("", "")


def clocks(parts: list[list[Row]]) -> list[list[tuple[str, str]]]:
    """``(clock, how)`` for every row of one filer's JSON parts (the recent block, then each file).

    ``how`` names what placed the row: ``hours`` / ``filing_date`` (its own time), ``near_180d`` /
    ``near_730d`` / ``part`` (its neighbours), ``filer`` (the filer's other parts) or ``default``
    (no evidence anywhere: UTC). A row without a full raw time is ``('', '')``.
    """
    placed = [_Part(rows) for rows in parts]
    filer = _majority(sum(len(p.days) for p in placed), sum(p.et_before[-1] for p in placed))
    out = []
    for p in placed:
        marks = []
        for (_form, raw, _fd), own in zip(p.rows, p.own, strict=True):
            if len(raw) < 19:
                marks.append(("", ""))
            elif own[0]:
                marks.append(own)
            else:
                near = p.neighbours(raw)
                marks.append(near if near[0] else (filer, "filer") if filer else (UTC, "default"))
        out.append(marks)
    return out


def accepted_ts(raw: str, clock: str) -> float:
    """Epoch seconds of a raw acceptance time read on ``clock``."""
    wall = datetime.fromisoformat(raw[:19])
    return wall.replace(tzinfo=ET if clock == EASTERN else timezone.utc).timestamp()
