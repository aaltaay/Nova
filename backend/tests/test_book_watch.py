"""The book watcher (ADR 033): filled vs pulled size, pull patterns, the worker, replay and sensor."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from book_watch import journal, live
from book_watch.book import aggregate, distance_ticks, in_view, side_view
from book_watch.detector import SymbolWatch
from book_watch.replay import replay


def lv(price, size, mm="NSDQ"):
    return {"price": price, "size": size, "mm": mm}


def watch(num_rows=10):
    return SymbolWatch("TEST", num_rows=num_rows)


ASKS = [lv(10.05, 300)]


# -- the book arithmetic ------------------------------------------------------

def test_venue_rows_at_one_price_are_summed():
    assert aggregate([lv(4.14, 150, "IEX"), lv(4.14, 170, "NSDQ"), lv(4.14, 100, "PEARL")]) == {4.14: 420.0}


def test_with_every_row_in_use_the_worst_price_is_the_cut_off():
    full = side_view([lv(10.0, 1), lv(9.99, 1), lv(9.98, 1)], "bid", 3)
    assert full.cutoff == 9.98 and full.best == 10.0
    assert in_view(9.99, "bid", full.cutoff) and not in_view(9.98, "bid", full.cutoff)
    spare = side_view([lv(10.0, 1)], "bid", 3)
    assert spare.cutoff is None and in_view(1.0, "bid", spare.cutoff)


def test_distance_is_ticks_from_the_side_best():
    assert distance_ticks("bid", 9.97, 10.0) == 3
    assert distance_ticks("ask", 10.02, 10.0) == 2
    assert distance_ticks("bid", 0.5, 0.5003) == 3  # sub-dollar tick


# -- filled vs pulled ---------------------------------------------------------

def test_a_level_that_trades_away_is_filled_not_pulled():
    w = watch()
    w.on_book(1.0, [lv(10.0, 500), lv(9.99, 300)], ASKS)
    w.on_print(1.1, 10.0, 500, lit=True)
    w.on_book(1.2, [lv(9.99, 300)], ASKS)
    w.tick(5.0)
    totals = w.totals(5.0)
    assert totals["filled_shares"] == 500 and totals["pulled_shares"] == 0


def test_a_level_that_vanishes_without_prints_is_pulled_and_large():
    w = watch()
    w.on_book(1.0, [lv(10.0, 300), lv(9.99, 5000), lv(9.98, 300)], ASKS)
    w.on_book(1.2, [lv(10.0, 300), lv(9.98, 300)], ASKS)
    events = w.tick(5.0)
    pulls = [e for e in events if e["event"] == "pull"]
    assert len(pulls) == 1
    pull = pulls[0]
    assert pull["side"] == "bid" and pull["price"] == 9.99 and pull["pulled"] == 5000 and pull["filled"] == 0
    assert pull["distance_ticks"] == 1 and pull["lifetime_sec"] is None  # there before the first book


def test_off_exchange_prints_never_fill_a_level():
    w = watch()
    w.on_book(1.0, [lv(10.0, 500), lv(9.99, 300)], ASKS)
    w.on_print(1.1, 10.0, 500, lit=False)  # FINRA
    w.on_book(1.2, [lv(9.99, 300)], ASKS)
    w.tick(5.0)
    assert w.totals(5.0)["pulled_shares"] == 500


def test_a_print_is_claimed_once():
    w = watch()
    w.on_book(1.0, [lv(10.0, 500), lv(9.99, 300)], ASKS)
    w.on_print(1.1, 10.0, 200, lit=True)
    w.on_book(1.2, [lv(9.99, 300)], ASKS)
    w.tick(5.0)
    totals = w.totals(5.0)
    assert totals["filled_shares"] == 200 and totals["pulled_shares"] == 300


def test_one_venue_leaving_a_shared_price_drops_only_its_size():
    w = watch()
    w.on_book(1.0, [lv(10.0, 300, "IEX"), lv(10.0, 200, "NSDQ"), lv(9.99, 100)], ASKS)
    w.on_book(1.2, [lv(10.0, 200, "NSDQ"), lv(9.99, 100)], ASKS)
    w.tick(5.0)
    assert w.totals(5.0)["pulled_shares"] == 300


def test_a_print_just_after_the_book_still_fills_the_drop():
    w = watch()
    w.on_book(1.0, [lv(10.0, 500), lv(9.99, 300)], ASKS)
    w.on_book(1.2, [lv(9.99, 300)], ASKS)
    w.on_print(1.4, 10.0, 500, lit=True)  # the tape line lagged the book
    w.tick(5.0)
    assert w.totals(5.0)["filled_shares"] == 500


# -- what is never judged -----------------------------------------------------

def test_a_price_that_scrolls_out_of_view_is_never_pulled():
    w = watch(num_rows=3)
    w.on_book(1.0, [lv(10.0, 300), lv(9.99, 5000), lv(9.98, 300)], ASKS)
    # A better bid pushes the rows down: 9.99 is now the cut-off, 9.98 gone from view.
    w.on_book(1.2, [lv(10.01, 300), lv(10.0, 300), lv(9.99, 100)], ASKS)
    w.tick(5.0)
    assert w.totals(5.0)["pulled_shares"] == 0


def test_a_collapsed_side_is_unknown_not_pulled():
    w = watch()
    w.on_book(1.0, [lv(10.0, 300), lv(9.99, 5000), lv(9.98, 300), lv(9.97, 300)], ASKS)
    w.on_book(1.2, [lv(10.0, 300)], ASKS)
    w.tick(5.0)
    assert w.totals(5.0)["pulled_shares"] == 0


def test_a_reset_starts_the_book_fresh():
    w = watch()
    w.on_book(1.0, [lv(10.0, 300), lv(9.99, 5000), lv(9.98, 300)], ASKS)
    w.reset()
    w.on_book(1.2, [lv(10.0, 300)], ASKS)  # IBKR resending from row 0
    w.tick(5.0)
    assert w.totals(5.0)["pulled_shares"] == 0


# -- flags --------------------------------------------------------------------

def test_size_pulled_as_the_price_came_toward_it_is_flagged():
    w = watch()
    w.on_book(1.0, [lv(10.0, 300), lv(9.99, 300), lv(9.97, 300)], ASKS)
    w.on_book(1.1, [lv(10.0, 300), lv(9.99, 300), lv(9.98, 5000), lv(9.97, 300)], ASKS)  # posted 2 ticks away
    w.on_book(1.5, [lv(9.99, 300), lv(9.98, 5000), lv(9.97, 300)], ASKS)  # the 10.00 bid went: 1 tick away
    w.on_book(2.0, [lv(9.99, 300), lv(9.97, 300)], ASKS)  # pulled, nothing printed there
    events = w.tick(5.0)
    flags = [e for e in events if e["event"] == "flag"]
    assert [f["kind"] for f in flags] == ["pulled_on_approach"]
    flag = flags[0]
    assert flag["price"] == 9.98 and flag["shares"] == 5000
    assert flag["evidence"]["distance_at_post_ticks"] == 2 and flag["evidence"]["distance_ticks"] == 1
    assert flag["evidence"]["lifetime_sec"] == pytest.approx(0.9)
    assert "pulled after the price came 1 tick(s) toward it" in flag["why"]
    assert list(w.flags) == flags


def test_three_large_pulls_on_one_side_are_a_repeat_flag_once_per_window():
    w = watch()
    t = 1.0
    for _ in range(4):
        w.on_book(t, [lv(10.0, 300), lv(9.99, 300), lv(9.98, 5000), lv(9.97, 300)], ASKS)
        w.on_book(t + 0.5, [lv(10.0, 300), lv(9.99, 300), lv(9.97, 300)], ASKS)
        t += 5.0
    w.tick(100.0)
    repeats = [f for f in w.flags if f["kind"] == "repeated_pulls"]
    assert len(repeats) == 1
    assert repeats[0]["evidence"]["count"] == 3 and repeats[0]["side"] == "bid"


def test_the_feed_reports_the_measured_rate():
    w = watch()
    for i in range(20):
        w.on_book(100.0 + i * 0.1, [lv(10.0, 300)], ASKS)
    feed = w.feed(102.0)
    assert feed["books"] == 20 and feed["books_per_sec"] == 2.0 and feed["median_gap_ms"] == pytest.approx(100.0)


def test_a_new_minute_closes_the_last_one():
    w = watch()
    w.on_book(60.0, [lv(10.0, 300)], ASKS)
    events = w.on_book(121.0, [lv(10.0, 300)], ASKS)
    minutes = [e for e in events if e["event"] == "minute"]
    assert minutes and minutes[0]["minute_ts"] == 60 and minutes[0]["books"] == 1


# -- the worker ---------------------------------------------------------------

@pytest.fixture
def worker_on(monkeypatch):
    monkeypatch.setenv("NOVA_BOOK_WATCH", "1")
    monkeypatch.setenv("NOVA_BOOK_WATCH_JOURNAL", "0")
    monkeypatch.setattr(live, "_ensure_thread", lambda: None)
    live.reset_for_tests()
    yield
    live.reset_for_tests()


def _drain():
    events = []
    while not live._q.empty():
        events += live.process(live._q.get_nowait())
    return events


def test_the_callbacks_only_enqueue_and_the_worker_judges(worker_on):
    live.enqueue_book("aapl", {"bids": [lv(10.0, 300), lv(9.99, 5000), lv(9.98, 300)], "asks": ASKS})
    live.enqueue_print({"symbol": "AAPL", "receive_ts": 1.0, "price": 10.0, "size": 5, "exchange": "FINRA"})
    assert live.snapshot("AAPL") is None  # nothing judged on the caller's thread
    _drain()
    live.enqueue_book("AAPL", {"bids": [lv(10.0, 300), lv(9.98, 300)], "asks": ASKS})
    _drain()
    live.tick(live._watches["AAPL"].last_book_ts + 5)
    snap = live.snapshot("AAPL", now=live._watches["AAPL"].last_book_ts + 5)
    assert snap["pulled_shares"] == 5000 and snap["pulls"][0]["price"] == 9.99


def test_an_l1_book_resets_the_watch(worker_on):
    live.enqueue_book("AAPL", {"bids": [lv(10.0, 300), lv(9.99, 5000), lv(9.98, 300)], "asks": ASKS})
    live.enqueue_book("AAPL", {"bids": [lv(10.0, 1)], "asks": [], "l1_fallback": True})
    live.enqueue_book("AAPL", {"bids": [lv(10.0, 300)], "asks": ASKS})
    _drain()
    live.tick(live._watches["AAPL"].last_book_ts + 5)
    assert live.snapshot("AAPL")["pulled_shares"] == 0


def test_off_means_nothing_is_queued(monkeypatch):
    monkeypatch.setenv("NOVA_BOOK_WATCH", "0")
    live.reset_for_tests()
    live.enqueue_book("AAPL", {"bids": [lv(10.0, 300)], "asks": ASKS})
    assert live._q.empty()


def test_journal_lines_carry_the_schema_version(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_BOOK_WATCH_DIR", str(tmp_path))
    monkeypatch.setenv("NOVA_BOOK_WATCH_JOURNAL", "1")
    journal.reset_for_tests()
    journal.record_many([{"event": "flag", "symbol": "AAPL", "kind": "repeated_pulls", "ts": 1.0}])
    assert journal.flush(5.0)
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    row = json.loads(files[0].read_text().splitlines()[0])
    assert row["schema_version"] == 1 and row["event"] == "flag" and "wall_ts" in row


# -- replay over a Session Record -------------------------------------------

def test_replay_runs_the_same_detector_over_a_recording(tmp_path):
    rec = tmp_path / "GCTK"
    rec.mkdir()
    books = [
        {"ts": 1.0, "bids": [{"price": 10.0, "size": 300}, {"price": 9.99, "size": 5000}, {"price": 9.98, "size": 300}],
         "asks": [{"price": 10.05, "size": 300}]},
        {"ts": 1.2, "bids": [{"price": 10.0, "size": 300}, {"price": 9.98, "size": 300}],
         "asks": [{"price": 10.05, "size": 300}]},
    ]
    prints = [{"ts": 1.1, "receive_ts": 1.1, "price": 10.05, "size": 100, "exchange": "NASDAQ"}]
    (rec / "l2.jsonl").write_text("\n".join(json.dumps(b) for b in books) + "\n")
    (rec / "prints.jsonl").write_text("\n".join(json.dumps(p) for p in prints) + "\n")
    result = replay(rec)
    assert result["symbol"] == "GCTK" and result["books"] == 2 and result["prints"] == 1
    assert result["pulled_shares"] == 5000 and [p["price"] for p in result["large_pulls"]] == [9.99]


# -- the sensor ---------------------------------------------------------------

def test_the_sensor_says_why_it_has_no_reading(worker_on):
    from main import app

    body = TestClient(app).get("/sensors/book-pulls", params={"symbol": "ZZZZ"}).json()
    assert body["sensor"] == "book-pulls" and body["data"]["watching"] is False
    assert "No Level 2 line for ZZZZ" in body["error"]
    assert body["data"]["caveats"] and "never a detection" in body["data"]["note"]


def test_the_sensor_reads_a_watched_line_and_the_event_feed(worker_on):
    from main import app

    live.enqueue_book("AAPL", {"bids": [lv(10.0, 300), lv(9.99, 300), lv(9.97, 300)], "asks": ASKS})
    live.enqueue_book("AAPL", {"bids": [lv(10.0, 300), lv(9.99, 300), lv(9.98, 5000), lv(9.97, 300)], "asks": ASKS})
    live.enqueue_book("AAPL", {"bids": [lv(9.99, 300), lv(9.98, 5000), lv(9.97, 300)], "asks": ASKS})
    live.enqueue_book("AAPL", {"bids": [lv(9.99, 300), lv(9.97, 300)], "asks": ASKS})
    _drain()
    live.tick(live._watches["AAPL"].last_book_ts + 5)
    client = TestClient(app)
    body = client.get("/sensors/book-pulls", params={"symbol": "AAPL"}).json()
    data = body["data"]
    assert body.get("error") is None and data["source"] == "ibkr_depth"
    assert data["feed"]["books"] == 4 and data["flags"][0]["kind"] == "pulled_on_approach"
    assert data["pulls_recent"][0]["price"] == 9.98
    feed = client.get("/sensors/book-pulls/events", params={"since": 0}).json()
    assert [f["kind"] for f in feed["flags"]] == ["pulled_on_approach"]
    assert feed["watcher"]["symbols"] == ["AAPL"]
    from sensors.adapters.bookish import _book_rates

    assert _book_rates("AAPL")["spoof_hints"][0]["price"] == 9.98  # the L2 sensor's hints are the watcher's pulls
