"""A live tape line gone silent is said in words, and a halt is never "the line may be down" (#722).

2026-10-05: SAIQ's AllLast line stopped at 09:35:42 ET while its Level 2 kept updating, with no IBKR
error, and its Time & Sales sat under a LIVE badge until about 09:42.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from constants_tape import TAPE_SILENT_BOOK_FRESH_SEC, TAPE_SILENT_SEC
from ibkr import tape_silence

ET = ZoneInfo("America/New_York")
LAST = datetime(2026, 10, 5, 9, 35, 42, tzinfo=ET).timestamp()


def read(now, **kw):
    args = {"last_print_ts": LAST, "line_since": LAST - 60, "book_at": now - 1, "halted": False}
    args.update(kw)
    return tape_silence.read(now=now, **args)


def test_a_tape_that_prints_reads_nothing():
    assert read(LAST + TAPE_SILENT_SEC - 1) is None


def test_silent_beside_a_moving_book_may_be_a_dead_line():
    r = read(LAST + 6 * 60)
    assert r["state"] == "silent" and r["since"] == LAST and r["last_print_ts"] == LAST
    assert "No prints since 09:35:42 ET while Level 2 kept updating" in r["text"]
    assert "may be down" in r["text"] and "clears on the next print" in r["text"]


def test_silent_beside_a_quiet_book_is_a_quiet_name():
    now = LAST + 120
    r = read(now, book_at=now - TAPE_SILENT_BOOK_FRESH_SEC - 1)
    assert r["state"] == "quiet" and "Level 2 is quiet too" in r["text"] and "may be down" not in r["text"]


def test_without_a_level_2_line_nothing_is_claimed_about_the_line():
    r = read(LAST + 120, book_at=None)
    assert r["state"] == "quiet" and "no Level 2 line" in r["text"]


def test_a_halt_prints_nothing_and_says_so():
    r = read(LAST + 15, halted=True)
    assert r["state"] == "halted" and r["halted"] is True
    assert r["text"].startswith("Halted: no prints until it reopens")


def test_the_silence_counts_from_the_reopening():
    reopened = LAST + 300
    assert read(reopened + 20, halt_seen_at=reopened) is None
    assert read(reopened + TAPE_SILENT_SEC + 1, halt_seen_at=reopened)["since"] == reopened


def test_a_new_line_counts_from_its_opening():
    opened = LAST + 600
    assert read(opened + 10, line_since=opened) is None
    r = read(opened + 40, last_print_ts=None, line_since=opened)
    assert r["state"] == "silent" and "since the line opened" in r["text"]


def test_an_unknown_halt_is_not_a_halt():
    assert read(LAST + 120, halted=None)["state"] == "silent"


def test_reading_takes_its_facts_from_memory(monkeypatch):
    from ibkr import halt_status
    from ibkr.depth import state as depth_state
    import ibkr.tape_recording as tape_recording

    now = LAST + 90
    monkeypatch.setattr(tape_recording, "producer_status",
                        lambda sym: {"last_print_ts": LAST, "line_since": LAST - 60})
    monkeypatch.setattr(depth_state, "last_book_at", lambda sym: now - 2)
    monkeypatch.setattr(halt_status, "halted_now", lambda syms, now=None: {s: False for s in syms})
    assert tape_silence.reading("saiq", now=now)["state"] == "silent"


def test_a_depth_line_remembers_its_last_book(monkeypatch):
    from ibkr.depth import state as depth_state

    monkeypatch.setattr(depth_state, "is_live", lambda sym: True)
    depth_state.note_book("SAIQ", now=LAST)
    assert depth_state.last_book_at("SAIQ") == LAST
    monkeypatch.setattr(depth_state, "is_live", lambda sym: False)
    assert depth_state.last_book_at("SAIQ") is None
