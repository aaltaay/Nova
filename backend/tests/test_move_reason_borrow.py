"""The borrow feed (ADR 028): IBKR's short-stock file parsed, recorded as it changes, read per symbol."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from move_reason import borrow_feed, borrow_parse, borrow_store

ET = ZoneInfo("America/New_York")
HEADER = "#SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|FIGI|"


def usa_txt(rows, when="2026.09.23|09:31:02", eof=None):
    lines = [f"#BOF|{when}", HEADER]
    lines += [f"{sym}|{cur}|NAME|1|X|{reb}|{fee}|{avail}|F|" for sym, cur, reb, fee, avail in rows]
    lines.append(f"#EOF|{len(rows) if eof is None else eof}")
    return "\n".join(lines).encode()


def at(hh, mm, day=23):
    return datetime(2026, 9, day, hh, mm, tzinfo=ET).timestamp()


def test_the_file_parses_to_desk_symbols_in_usd_only():
    f = borrow_parse.parse(usa_txt([
        ("MSS", "USD", "-101.0401", "104.9201", "2000"),
        ("BRK B", "USD", "3.63", "0.25", ">10000000"),
        ("SHOP", "CAD", "1.0", "0.3", "5000"),
    ]))
    assert f.complete and f.file_ts == at(9, 31) + 2
    assert set(f.rows) == {"MSS", "BRK/B"}
    assert f.rows["MSS"].fee_rate == 104.9201 and f.rows["MSS"].available == 2000
    assert f.rows["BRK/B"].capped and f.rows["BRK/B"].available == 10_000_000


def test_a_cut_off_file_is_incomplete():
    assert not borrow_parse.parse(usa_txt([("MSS", "USD", "0", "5", "100")], eof=20280)).complete
    assert not borrow_parse.parse(b"#BOF|2026.09.23|09:31:02\n" + HEADER.encode() + b"\nMSS|USD|N|1|X|0|5|100|F|").complete


@pytest.fixture
def feed(tmp_path):
    files: list[bytes] = []
    clock = {"now": at(9, 0)}
    db = borrow_store.connect(tmp_path / "borrow.sqlite3")
    f = borrow_feed.BorrowFeed(fetch=lambda: files.pop(0), clock=lambda: clock["now"], db=db)
    f.warm_start()
    f.files, f.clock = files, clock  # type: ignore[attr-defined]
    return f


def poll(feed, when, rows):
    feed.clock["now"] = when
    feed.files.append(usa_txt(rows))
    return feed.poll_once()


def test_nothing_recorded_is_unknown_not_nothing_to_lend(feed):
    assert feed.view("MSS", at(9, 0)) is None


def test_only_changes_are_written_and_the_day_is_read_back(feed):
    assert poll(feed, at(3, 50), [("MSS", "USD", "0", "20", "500000"), ("TLSA", "USD", "2.6", "1.3", "1500000")])
    assert poll(feed, at(4, 5), [("MSS", "USD", "0", "20", "500000"), ("TLSA", "USD", "2.6", "1.3", "1500000")])
    assert poll(feed, at(9, 45), [("MSS", "USD", "-40", "45", "20000"), ("TLSA", "USD", "2.6", "1.3", "1500000")])
    assert poll(feed, at(11, 0), [("TLSA", "USD", "2.6", "1.3", "1500000")])            # MSS: nothing to lend
    rows = feed._db.execute("SELECT symbol, ts, listed FROM changes ORDER BY ts, symbol").fetchall()
    assert rows == [("MSS", at(3, 50), 1), ("TLSA", at(3, 50), 1), ("MSS", at(9, 45), 1), ("MSS", at(11, 0), 0)]
    v = feed.view("MSS", at(11, 5))
    assert v["listed"] is False
    assert v["open"] == {"listed": True, "fee_rate": 20.0, "available": 500000, "as_of": at(4, 5)}
    assert v["prior"]["as_of"] == at(3, 50)
    assert (v["max_fee_today"], v["min_available_today"]) == (45.0, 0)
    assert feed.view("NEVER", at(11, 5))["listed"] is False


def test_a_failed_or_partial_poll_records_nothing(feed):
    feed.files.append(usa_txt([("MSS", "USD", "0", "20", "500000")], eof=99))
    assert feed.poll_once() is False
    assert feed.status()["last_error"].startswith("incomplete file")
    feed.files.append(b"")
    assert feed.poll_once() is False
    assert feed._db.execute("SELECT count(*) FROM polls").fetchone()[0] == 0


def test_a_restart_keeps_the_day(tmp_path):
    db_path = tmp_path / "borrow.sqlite3"
    first = borrow_feed.BorrowFeed(fetch=lambda: usa_txt([("MSS", "USD", "0", "20", "500000")]),
                                   clock=lambda: at(8, 0), db=borrow_store.connect(db_path))
    first.warm_start()
    assert first.poll_once()
    again = borrow_feed.BorrowFeed(fetch=lambda: usa_txt([("MSS", "USD", "-80", "90", "3000")]),
                                   clock=lambda: at(10, 0), db=borrow_store.connect(db_path))
    again.warm_start()
    assert again.view("MSS", at(10, 0))["fee_rate"] == 20.0          # before its own first poll
    assert again.poll_once()
    v = again.view("MSS", at(10, 1))
    assert (v["fee_rate"], v["open"]["fee_rate"], v["since"]) == (90.0, 20.0, at(8, 0))


def test_pruning_keeps_each_symbols_last_value(tmp_path):
    db = borrow_store.connect(tmp_path / "borrow.sqlite3")
    borrow_store.put_poll(db, 100.0, None, 1, [("OLD", {"listed": True, "fee_rate": 1.0, "rebate_rate": 0.0,
                                                          "available": 5, "capped": False})])
    borrow_store.put_poll(db, 200.0, None, 1, [("OLD", {"listed": True, "fee_rate": 2.0, "rebate_rate": 0.0,
                                                          "available": 5, "capped": False})])
    borrow_store.put_poll(db, 900.0, None, 1, [])
    borrow_store.prune(db, before=500.0)
    assert db.execute("SELECT ts, fee_rate FROM changes").fetchall() == [(200.0, 2.0)]
    assert borrow_store.value_at(db, "OLD", 900.0)["fee_rate"] == 2.0


def test_an_unknown_store_version_refuses(tmp_path):
    path = tmp_path / "borrow.sqlite3"
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA user_version = 9")
    raw.execute("CREATE TABLE polls (ts REAL)")
    raw.commit()
    raw.close()
    with pytest.raises(RuntimeError, match="refusing to open"):
        borrow_store.connect(path)
