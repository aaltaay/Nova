"""A recording whose tape goes silent while its book keeps coming asks IBKR again, and says so (#525).

2026-09-23: IPDN and WHLR recorded quotes and Level 2 until 10:00 but no print
after 09:46:40, and nothing said so. A stale tape beside a fresh book is a dead
line; a stale tape beside a stale book is a quiet name. An IBKR error on the
line is an end too. Either way only the tape is asked for again -- once IB's
15 s rule allows, never in a hot loop -- and the outage is shouted until a
print arrives on the new line.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from capture import keepalive, tape_watch
from capture.constants_capture import (
    CAPTURE_TAPE_LOST,
    CAPTURE_TAPE_RENEW_DELAY_SEC,
    CAPTURE_TAPE_RESUBSCRIBE_MIN_SEC,
    CAPTURE_TAPE_STALE_SEC,
)

ET = ZoneInfo("America/New_York")
LAST_PRINT = datetime(2026, 9, 23, 9, 46, 40, tzinfo=ET).timestamp()


class Desk:
    """One recording and fakes for everything a tick asks of IBKR."""

    def __init__(self, symbol="IPDN"):
        self.symbol = symbol
        self.last_print: float | None = LAST_PRINT
        self.line_since = LAST_PRINT - 600
        self.last_book: float | None = LAST_PRINT
        self.ended: dict | None = None
        self.subscribed = True
        self.ready_flag = True
        self.renew_error: str | None = None
        self.ends: list[tuple[str, str]] = []
        self.renews: list[str] = []
        self.notes: list[dict] = []
        self.acquired: list[str] = []
        self.released: list[str] = []
        self.ops = keepalive.TapeOps(end=self.end, renew=self.renew, note=self.note)

    def end(self, symbol, why):
        self.ends.append((symbol, why))
        self.subscribed = False

    async def renew(self, symbol):
        self.renews.append(symbol)
        if self.renew_error:
            return self.renew_error
        self.subscribed, self.ended = True, None
        self.last_print, self.line_since = None, self.now
        return None

    async def note(self, symbol, **kwargs):
        self.notes.append(kwargs)

    async def acquire(self, symbol):
        self.acquired.append(symbol)

    async def release(self, symbol):
        self.released.append(symbol)

    async def start(self, symbol):
        return {"capture_symbols": [self.symbol]}

    def payload(self):
        producer = {"state": "receiving" if self.subscribed else "disconnected",
                    "last_print_ts": self.last_print, "line_since": self.line_since}
        if not self.subscribed:
            producer["ended"] = self.ended
        return {"capture": True, "capture_symbol": self.symbol, "capture_symbols": [self.symbol],
                "sessions": {self.symbol: {"producer": producer, "book": {"last_book_ts": self.last_book}}}}

    def recorder(self):
        row = {"symbol": self.symbol, "dir": f"F:/x/2026-09-23/{self.symbol}", "counts": {"prints": 24683}}
        return {**row, "sessions": {self.symbol: row}}

    def tick(self, now, *, book_fresh=True):
        self.now = now
        if book_fresh:
            self.last_book = now - 1
        asyncio.run(keepalive.tick(now=now, payload=self.payload(), recorder_status=self.recorder(),
                                   ready=lambda: self.ready_flag, acquire=self.acquire, release=self.release,
                                   start=self.start, tape=self.ops))


def row_of(symbol="IPDN"):
    fields = keepalive.status_fields({}, [symbol])
    return next((r for r in fields["capture_stopped"] if r["symbol"] == symbol), None)


def reacquired(symbol="IPDN"):
    return keepalive.status_fields({}, [symbol])["capture_sessions"][0]["reacquired"]


@pytest.fixture(autouse=True)
def fresh():
    keepalive.reset_for_tests()
    yield
    keepalive.reset_for_tests()


def test_a_silent_tape_beside_a_fresh_book_is_asked_for_again_once_and_said():
    desk = Desk()
    desk.tick(LAST_PRINT + 30)                           # a lull, not a fault
    assert desk.ends == [] and row_of() is None
    found = LAST_PRINT + CAPTURE_TAPE_STALE_SEC + 5
    desk.tick(found)
    assert [s for s, _ in desk.ends] == ["IPDN"]         # the dead line is dropped
    row = row_of()
    assert row["reason"] == CAPTURE_TAPE_LOST and row["resumed"] is False
    assert "No prints since 09:46:40 ET" in row["error"] and "book kept updating" in row["error"]
    assert row["counts"]["prints"] == 24683
    assert desk.notes[0]["loss"]["cause"] == "stale"
    desk.tick(found + 5)                                 # IB's 15 s rule: not yet
    assert desk.renews == [] and desk.acquired == [] and desk.released == []
    desk.tick(found + CAPTURE_TAPE_RENEW_DELAY_SEC)
    assert desk.renews == ["IPDN"] and reacquired() == 1
    assert desk.notes[-1] == {"resubscribed": True}
    assert desk.acquired == [] and desk.released == []  # the depth line was never cycled
    desk.tick(found + CAPTURE_TAPE_RENEW_DELAY_SEC + 5)  # nothing printed yet: no second ask
    assert len(desk.ends) == 1 and desk.renews == ["IPDN"]
    desk.last_print = desk.now + 1                       # a print on the new line
    desk.tick(desk.now + 5)
    assert row_of()["resumed"] is True                   # the shout says it healed
    assert tape_watch.in_outage("IPDN") is False


def test_a_silent_tape_beside_a_silent_book_is_a_quiet_name():
    desk = Desk()
    desk.last_book = LAST_PRINT
    desk.tick(LAST_PRINT + CAPTURE_TAPE_STALE_SEC + 60, book_fresh=False)
    assert desk.ends == [] and desk.renews == [] and row_of() is None and desk.notes == []


def test_asking_again_respects_the_minimum_interval():
    desk = Desk()
    found = LAST_PRINT + CAPTURE_TAPE_STALE_SEC
    desk.tick(found)
    renewed_at = found + CAPTURE_TAPE_RENEW_DELAY_SEC
    desk.tick(renewed_at)                                # asked: the new line opens silent
    assert desk.renews == ["IPDN"]
    desk.tick(renewed_at + CAPTURE_TAPE_STALE_SEC + 1)   # silent past the stale mark, inside the minimum
    assert len(desk.ends) == 1
    desk.tick(renewed_at + CAPTURE_TAPE_RESUBSCRIBE_MIN_SEC[0])
    assert len(desk.ends) == 2                           # a quiet name costs one ask per interval
    second = renewed_at + CAPTURE_TAPE_RESUBSCRIBE_MIN_SEC[0] + CAPTURE_TAPE_RENEW_DELAY_SEC
    desk.tick(second)
    assert desk.renews == ["IPDN", "IPDN"] and reacquired() == 2
    desk.tick(second + CAPTURE_TAPE_RESUBSCRIBE_MIN_SEC[0])
    assert len(desk.ends) == 2                           # and the interval grows while nothing prints
    desk.tick(second + CAPTURE_TAPE_RESUBSCRIBE_MIN_SEC[1])
    assert len(desk.ends) == 3
    assert len([n for n in desk.notes if "loss" in n]) == 1  # one outage, one loss on record


def test_a_line_ibkr_ended_is_asked_for_after_the_guard_and_the_depth_line_is_left_alone():
    desk = Desk("WHLR")
    at = LAST_PRINT + 2
    desk.subscribed = False
    desk.ended = {"at": at, "cause": "ib_error", "code": 10190,
                  "message": "Max number of tick-by-tick requests has been reached.", "req_id": 77}
    desk.tick(at + 1)
    assert desk.ends == []                               # IBKR already ended it; tape_line dropped it
    row = row_of("WHLR")
    assert row["reason"] == CAPTURE_TAPE_LOST and "error 10190" in row["error"]
    assert desk.released == [] and desk.acquired == []  # not the Gateway branch: depth is fine
    desk.tick(at + CAPTURE_TAPE_RENEW_DELAY_SEC - 1)
    assert desk.renews == []
    desk.tick(at + CAPTURE_TAPE_RENEW_DELAY_SEC)
    assert desk.renews == ["WHLR"] and reacquired("WHLR") == 1


def test_a_failed_ask_backs_off_and_says_why():
    desk = Desk()
    found = LAST_PRINT + CAPTURE_TAPE_STALE_SEC
    desk.tick(found)
    desk.renew_error = "Resubscribing in 3s -- please wait"
    desk.tick(found + CAPTURE_TAPE_RENEW_DELAY_SEC)
    assert desk.renews == ["IPDN"] and reacquired() == 0
    assert "asking again failed: Resubscribing" in row_of()["error"]
    desk.tick(found + CAPTURE_TAPE_RENEW_DELAY_SEC + 1)  # backoff, not every tick
    assert desk.renews == ["IPDN"]


def test_ibkr_being_down_costs_no_ask():
    desk = Desk()
    found = LAST_PRINT + CAPTURE_TAPE_STALE_SEC
    desk.tick(found)
    desk.ready_flag = False
    desk.tick(found + CAPTURE_TAPE_RENEW_DELAY_SEC)
    assert desk.renews == []
    desk.ready_flag = True
    desk.tick(found + CAPTURE_TAPE_RENEW_DELAY_SEC + 5)
    assert desk.renews == ["IPDN"]


def test_a_thin_name_that_prints_now_and_then_is_one_shout_with_a_growing_interval():
    desk = Desk()
    found = LAST_PRINT + CAPTURE_TAPE_STALE_SEC
    desk.tick(found)
    first_at = row_of()["at"]
    renewed_at = found + CAPTURE_TAPE_RENEW_DELAY_SEC
    desk.tick(renewed_at)
    desk.last_print = renewed_at + 10                    # it trades again, once
    desk.tick(renewed_at + 15)
    assert row_of()["resumed"] is True
    desk.tick(desk.last_print + CAPTURE_TAPE_STALE_SEC)  # silent again, inside the first interval
    assert len(desk.ends) == 1
    again = renewed_at + CAPTURE_TAPE_RESUBSCRIBE_MIN_SEC[0]
    desk.tick(again)
    assert len(desk.ends) == 2
    row = row_of()
    assert row["at"] == first_at and row["resumed"] is False  # the same toast, brought back up
    desk.tick(again + CAPTURE_TAPE_RENEW_DELAY_SEC)
    desk.last_print = desk.now + 1
    desk.tick(desk.now + 5)
    desk.tick(desk.now + CAPTURE_TAPE_RESUBSCRIBE_MIN_SEC[0])   # the interval grew
    assert len(desk.ends) == 2


def test_prints_on_a_line_a_panel_opened_first_end_the_outage_without_an_ask():
    desk = Desk()
    found = LAST_PRINT + CAPTURE_TAPE_STALE_SEC
    desk.tick(found)
    desk.subscribed, desk.last_print = True, found + 3     # a Time & Sales panel asked first
    desk.tick(found + 5)
    assert row_of()["resumed"] is True and desk.renews == [] and reacquired() == 0


def test_an_operator_stop_forgets_the_outage():
    desk = Desk()
    desk.tick(LAST_PRINT + CAPTURE_TAPE_STALE_SEC)
    keepalive.operator_stopped("IPDN")
    assert tape_watch.in_outage("IPDN") is False and row_of() is None
