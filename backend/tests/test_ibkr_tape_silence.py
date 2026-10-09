"""A live tape line gone silent is said in words, and a halt is never "the line may be down" (#722).

2026-10-05: SAIQ's AllLast line stopped at 09:35:42 ET while its Level 2 kept updating, with no IBKR
error, and its Time & Sales sat under a LIVE badge until about 09:42.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from constants_tape import TAPE_DEAD_L1_LEAD_SEC, TAPE_SILENT_BOOK_FRESH_SEC, TAPE_SILENT_SEC
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


# -- dead or quiet: the Level 1 line is the witness (#722) ---------------------------------------
# On 2026-10-05 SAIQ's Level 1 counted 1,381 RTVolume updates (2.5M shares) in the 332 s its tape
# printed nothing, and VEEA's 1,645 (1.05M) in 574 s: both lines were dead, not quiet.

EXCHANGE = datetime(2026, 10, 5, 9, 35, 42, tzinfo=ET).timestamp()   # the print's IBKR second
ARRIVAL = EXCHANGE + 0.388                                           # its arrival on the desk


def dead_read(now, **kw):
    args = {"last_print_ts": ARRIVAL, "last_print_exchange_ts": EXCHANGE, "line_since": ARRIVAL - 60,
            "book_at": now - 1, "halted": False, "l1_fresh": True}
    args.update(kw)
    return tape_silence.read(now=now, **args)


def test_level_1_trades_after_the_last_print_make_the_line_dead():
    now = ARRIVAL + 60
    r = dead_read(now, l1_trade_at=EXCHANGE + 28)
    assert r["schema_version"] == 2 and r["state"] == "dead" and r["l1_trade_ts"] == EXCHANGE + 28
    assert r["text"].startswith("No prints since 09:35:42 ET while Level 1 shows trades up to 09:36:10 ET")
    assert "down, not quiet" in r["text"]


def test_the_print_is_compared_by_ibkrs_second_with_a_few_seconds_lead():
    now = ARRIVAL + 60
    assert dead_read(now, l1_trade_at=EXCHANGE + TAPE_DEAD_L1_LEAD_SEC - 1)["state"] == "quiet"
    assert dead_read(now, l1_trade_at=EXCHANGE + TAPE_DEAD_L1_LEAD_SEC)["state"] == "dead"


def test_level_1_updating_with_no_trade_since_is_a_quiet_name_even_beside_a_moving_book():
    r = dead_read(ARRIVAL + 60, l1_trade_at=EXCHANGE)
    assert r["state"] == "quiet" and "Level 1 shows no trade since either" in r["text"]


def test_a_level_1_line_that_stopped_updating_cannot_call_it_quiet():
    r = dead_read(ARRIVAL + 60, l1_trade_at=EXCHANGE, l1_fresh=False)
    assert r["state"] == "silent" and "may be down" in r["text"]


def test_a_new_line_is_dead_only_on_trades_after_it_opened():
    opened = ARRIVAL + 240                                  # VEEA asked for again at 09:39:42
    now = opened + 60
    assert dead_read(now, line_since=opened, l1_trade_at=opened - 30)["state"] == "quiet"
    assert dead_read(now, line_since=opened, l1_trade_at=opened + 20)["state"] == "dead"


def test_a_halt_is_never_dead():
    assert dead_read(ARRIVAL + 60, l1_trade_at=EXCHANGE + 28, halted=True)["state"] == "halted"


def test_lines_silent_in_the_same_second_and_a_farm_notice_are_named():
    notice = {"ts": EXCHANGE + 139, "code": 2105, "notice": "broken", "farm": "ushmds", "farm_type": "HMDS",
              "message": "HMDS data farm connection is broken:ushmds", "symbol": None}
    r = dead_read(ARRIVAL + 200, l1_trade_at=EXCHANGE + 150, pipeline=["VEEA"], notice=notice)
    assert r["pipeline"] == ["VEEA"] and r["notice"] == notice
    assert "VEEA stopped printing in the same second: one IBKR tick-by-tick event" in r["text"]
    assert r["text"].endswith("IBKR said 2105 (broken ushmds) at 09:38:01 ET.")
    quiet = dead_read(ARRIVAL + 200, l1_trade_at=EXCHANGE, pipeline=["VEEA"], notice=notice)
    assert quiet["state"] == "quiet" and quiet["pipeline"] == [] and quiet["notice"] is None


class _Ticker:
    def __init__(self, last_ts=None, rt_time=None):
        self.lastTimestamp = last_ts
        self.rtTime = rt_time


def test_the_level_1_trade_clock_is_the_newest_of_tick_45_and_rtvolume(monkeypatch):
    from ibkr import ticks

    tick45 = datetime(2026, 10, 5, 9, 36, 9, tzinfo=ET)
    rt = datetime(2026, 10, 5, 9, 36, 10, 250000, tzinfo=ET)
    monkeypatch.setattr(ticks, "get_ticker", lambda sym: _Ticker(tick45, rt) if sym == "SAIQ" else None)
    assert tape_silence.l1_trade_at("SAIQ") == rt.timestamp()
    assert tape_silence.l1_trade_at("VEEA") is None
    monkeypatch.setattr(ticks, "get_ticker", lambda sym: _Ticker())
    assert tape_silence.l1_trade_at("SAIQ") is None


def _lines(monkeypatch, last_prints, halted=()):
    from ibkr import halt_status, tape_stream
    import ibkr.tape_recording as tape_recording

    monkeypatch.setattr(tape_stream, "live_symbols", lambda: sorted(last_prints))
    monkeypatch.setattr(tape_recording, "producer_status",
                        lambda sym: {"last_print_ts": last_prints.get(sym), "line_since": ARRIVAL - 600,
                                     "last_print_exchange_ts": EXCHANGE if sym in last_prints else None})
    monkeypatch.setattr(halt_status, "halted_now", lambda syms, now=None: {s: s in halted for s in syms})


def test_pipeline_peers_are_live_lines_silent_since_the_same_second(monkeypatch):
    _lines(monkeypatch, {"SAIQ": ARRIVAL, "VEEA": ARRIVAL - 0.002, "MI": ARRIVAL - 101, "GOW": ARRIVAL + 0.5,
                         "ACB": ARRIVAL + 30}, halted=("GOW",))
    assert tape_silence.pipeline_peers("saiq") == ["VEEA"]
    _lines(monkeypatch, {"SAIQ": None, "VEEA": ARRIVAL})
    assert tape_silence.pipeline_peers("SAIQ") == []


def test_a_dead_line_is_logged_and_recorded_once_per_silence(monkeypatch, caplog):
    from ibkr import farm_notices, ticks
    from ibkr.depth import state as depth_state
    from perf import recorder

    tape_silence.reset_for_tests()
    farm_notices.reset_for_tests()
    _lines(monkeypatch, {"SAIQ": ARRIVAL, "VEEA": ARRIVAL})
    monkeypatch.setattr(depth_state, "last_book_at", lambda sym: ARRIVAL + 100)
    monkeypatch.setattr(ticks, "get_ticker", lambda sym: _Ticker(datetime.fromtimestamp(EXCHANGE + 40, ET)))
    monkeypatch.setattr(ticks, "is_fresh", lambda sym, sec: True)
    rows: list[dict] = []
    monkeypatch.setattr(recorder, "persist", rows.append)
    first = tape_silence.reading("SAIQ", now=ARRIVAL + 101)
    tape_silence.reading("SAIQ", now=ARRIVAL + 116)          # a second socket's ping: same silence
    assert first["state"] == "dead" and first["pipeline"] == ["VEEA"]
    assert len(rows) == 1 and rows[0]["kind"] == "tape_silence" and rows[0]["schema_version"] == 1
    assert rows[0]["symbol"] == "SAIQ" and rows[0]["reading"]["state"] == "dead"
    assert sum("SAIQ's line reads dead" in m for m in caplog.messages) == 1
    tape_silence.reset_for_tests()
