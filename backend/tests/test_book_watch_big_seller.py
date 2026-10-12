"""Big sellers on the ask and big buyers on the bid (#846): the rule, a called price's life (holding,
taken, pulled, lost), the live and replay readings, the route and the sensor."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from book_watch import big_read, big_replay, live
from book_watch.big_seller import BigParams, BigWallTracker
from book_watch.book import side_view
from book_watch.constants_book_watch import (
    BOOK_WATCH_BIG_MEDIAN_MULT,
    BOOK_WATCH_BIG_MIN_DOLLARS,
    BOOK_WATCH_BIG_MIN_HOLD_SEC,
    BOOK_WATCH_BIG_MIN_SHARES,
)
from book_watch.detector import SymbolWatch
from book_watch.replay import replay


def lv(price, size, mm="NSDQ"):
    return {"price": price, "size": size, "mm": mm}


BIDS = [lv(4.46, 500), lv(4.45, 600), lv(4.44, 700), lv(4.43, 400)]


def asks(wall=20_000, at=4.50):
    rows = [lv(4.48, 500), lv(4.49, 400), lv(4.51, 800), lv(4.52, 600)]
    return rows + [lv(at, wall)] if wall else rows


def bigs(events):
    return [e for e in events if e["event"] == "big"]


def held(w, *, until=4.5, book=None, bids=BIDS, last=4.47):
    """A print at ``last`` (the price), then a book every second from t=1 until ``until``."""
    events = w.on_print(0.5, last, 100, lit=True)
    t = 1.0
    while t <= until:
        events += w.on_book(t, bids, book if book is not None else asks())
        t += 1.0
    return events


def watch(num_rows=10):
    return SymbolWatch("TEST", num_rows=num_rows)


# -- the rule -------------------------------------------------------------------

def test_the_defaults_are_the_documented_rule():
    assert (BOOK_WATCH_BIG_MIN_SHARES, BOOK_WATCH_BIG_MIN_DOLLARS, BOOK_WATCH_BIG_MEDIAN_MULT,
            BOOK_WATCH_BIG_MIN_HOLD_SEC) == (10_000, 20_000.0, 5.0, 3.0)
    p = BigParams()
    assert p.floor(4.5) == 10_000 and p.floor(1.0) == 20_000          # the dollars set it under $2
    assert p.window(3.0) == pytest.approx(0.05) and p.window(10.0) == pytest.approx(0.10)
    assert p.window(1.0) == pytest.approx(0.03)                        # never more than 3%


def test_a_size_far_over_the_book_just_over_the_price_is_called_after_it_holds():
    w = watch()
    assert bigs(held(w, until=3.5)) == []          # big from t=1, but not yet 3 s
    called = bigs(w.on_book(4.0, BIDS, asks()))
    assert len(called) == 1
    big = called[0]
    assert big["kind"] == "big_seller" and big["side"] == "ask" and big["state"] == "holding"
    assert big["price"] == 4.50 and big["size_first"] == 20_000 and big["first_seen_ts"] == 1.0
    assert big["distance"] == pytest.approx(0.03) and big["median_level"] == 550 and big["seen_from_start"] is True
    reading = w.big.reading(10.0)
    assert reading["sellers"][0]["held_sec"] == 9.0 and reading["buyers"] == []
    assert reading["reference_source"] == "last" and reading["last"] == 4.47


def test_size_under_the_multiple_of_the_book_around_it_is_not_big():
    w = watch()
    thick = [lv(4.48, 3000), lv(4.49, 3000), lv(4.51, 3000), lv(4.52, 3000), lv(4.50, 14_000)]
    assert bigs(held(w, until=6.0, book=thick)) == []  # 14,000 is under 5 x 3,000


def test_size_under_the_share_floor_is_not_big_however_thin_the_book():
    w = watch()
    assert bigs(held(w, until=6.0, book=asks(9_000))) == []


def test_the_dollar_floor_sets_it_on_a_cheap_stock():
    def cheap(size):
        return [lv(0.98, 100), lv(0.99, 100), lv(1.01, 100), lv(1.02, 100), lv(1.00, size)]

    low_bids = [lv(0.96, 100), lv(0.95, 100), lv(0.94, 100), lv(0.93, 100)]
    w = watch()
    assert bigs(held(w, until=6.0, book=cheap(15_000), bids=low_bids, last=0.99)) == []   # $15,000
    w = watch()
    assert len(bigs(held(w, until=6.0, book=cheap(25_000), bids=low_bids, last=0.99))) == 1


def test_a_size_past_the_window_is_not_called():
    w = watch()
    far = [lv(4.48, 500), lv(4.49, 400), lv(4.51, 800), lv(4.52, 600), lv(4.60, 20_000)]
    assert bigs(held(w, until=6.0, book=far)) == []    # 13 cents over, the window is 5


def test_a_size_that_shrinks_during_the_hold_starts_over():
    w = watch()
    events = w.on_print(0.5, 4.47, 100, lit=True)
    events += w.on_book(1.0, BIDS, asks())
    events += w.on_book(2.0, BIDS, asks(2_000))      # no longer big: the hold restarts
    for t in (3.0, 4.0, 5.0):
        events += w.on_book(t, BIDS, asks())
    assert bigs(events) == []
    assert len(bigs(w.on_book(6.0, BIDS, asks()))) == 1


def test_too_few_levels_around_it_is_no_call():
    w = watch()
    thin = [lv(4.48, 500), lv(4.49, 400), lv(4.50, 20_000)]
    assert bigs(held(w, until=6.0, book=thin)) == []
    assert w.big.reading(6.0)["sides"]["ask"] == {"levels": 3, "enough": False}


# -- a called price's life ------------------------------------------------------------

def test_a_print_through_it_is_taken_at_once():
    w = watch()
    held(w, until=4.0)
    out = bigs(w.on_print(5.0, 4.51, 200, lit=True))
    assert len(out) == 1 and out[0]["state"] == "eaten" and out[0]["how"] == "through"
    assert out[0]["distance"] == pytest.approx(0.03)   # where it sat before the print went through
    assert w.big.reading(6.0)["sellers"][0]["state"] == "eaten"
    assert w.big.reading(40.0)["sellers"] == []        # ended ones show 30 s


def test_an_off_exchange_or_odd_lot_print_through_it_proves_nothing():
    w = watch()
    held(w, until=4.0)
    assert bigs(w.on_print(5.0, 4.51, 200, lit=False)) == []
    assert bigs(w.on_print(5.1, 4.51, 50, lit=True, conditions="I")) == []
    assert w.big.reading(6.0)["sellers"][0]["state"] == "holding"


def test_a_size_that_trades_away_at_its_price_is_taken():
    w = watch()
    held(w, until=4.0)
    w.on_print(4.5, 4.50, 5_000, lit=True)
    w.on_book(5.0, BIDS, asks(15_000))               # partly taken: still big
    w.on_print(5.6, 4.50, 14_000, lit=True)
    assert bigs(w.on_book(6.0, BIDS, asks(0))) == []  # gone: judged once the settle time passes
    assert w.big.reading(6.1)["sellers"][0]["state"] == "left"
    out = bigs(w.tick(7.0))
    assert out[0]["state"] == "eaten" and out[0]["how"] == "traded"
    assert out[0]["left"] == {"before": 15_000, "after": 0, "filled": 14_000}
    assert out[0]["traded"] == 19_000 and out[0]["size_first"] == 20_000


def test_a_size_that_leaves_without_trading_is_pulled():
    w = watch()
    held(w, until=4.0)
    w.on_print(5.5, 4.50, 300, lit=True)
    w.on_book(6.0, BIDS, asks(0))
    out = bigs(w.tick(7.0))
    assert out[0]["state"] == "pulled" and out[0]["how"] == "no_prints" and out[0]["left"]["filled"] == 300


def test_a_price_that_scrolls_out_of_view_is_lost_never_pulled():
    w = watch(num_rows=5)
    rows = asks()
    held(w, until=4.0, book=rows)
    deeper = [lv(4.47, 500), lv(4.475, 500), lv(4.48, 500), lv(4.49, 400), lv(4.50, 20_000)]  # 4.50 is the cut-off now
    out = bigs(w.on_book(5.0, BIDS, deeper))
    assert out[0]["state"] == "lost" and out[0]["how"] == "cut_off"


def test_a_book_reset_loses_what_it_followed():
    w = watch()
    held(w, until=4.0)
    out = bigs(w.reset())
    assert out[0]["state"] == "lost" and out[0]["how"] == "reset"


# -- the bid mirror -----------------------------------------------------------------

def test_a_big_buyer_on_the_bid_mirrors_it():
    bids = [lv(4.46, 500), lv(4.45, 20_000), lv(4.44, 700), lv(4.43, 400), lv(4.42, 600)]
    w = watch()
    out = bigs(held(w, until=4.0, bids=bids, book=asks(0)))
    assert len(out) == 1 and out[0]["kind"] == "big_buyer" and out[0]["side"] == "bid"
    assert out[0]["distance"] == pytest.approx(0.02)   # two cents under the price
    taken = bigs(w.on_print(5.0, 4.44, 100, lit=True))
    assert taken[0]["state"] == "eaten" and taken[0]["how"] == "through"


# -- live, replay, the route and the sensor --------------------------------------------

@pytest.fixture
def worker_on(monkeypatch):
    monkeypatch.setenv("NOVA_BOOK_WATCH", "1")
    monkeypatch.setenv("NOVA_BOOK_WATCH_JOURNAL", "0")
    monkeypatch.setattr(live, "_ensure_thread", lambda: None)
    monkeypatch.setattr(big_read, "_replay_desk", lambda: False)
    live.reset_for_tests()
    big_replay.reset_for_tests()
    yield
    live.reset_for_tests()
    big_replay.reset_for_tests()


def _feed_live(symbol, start):
    live.process(("print", symbol, start - 0.5, 4.47, 100, True, ""))
    for i in range(5):
        live.process(("book", symbol, start + i, BIDS, asks()))


def test_no_depth_line_says_so_never_none(worker_on):
    body = big_read.live_reading("ZZZZ")
    assert body["watching"] is False and body["sellers"] == [] and body["buyers"] == []
    assert "No Level 2 line for ZZZZ" in body["reason"]


def test_a_stale_line_says_so_and_lists_nothing(worker_on):
    _feed_live("AAPL", 100.0)
    body = big_read.live_reading("AAPL", now=116.0)
    assert body["watching"] is False and body["sellers"] == []
    assert "no book for 12 s" in body["reason"]


def test_the_watcher_off_says_so(worker_on, monkeypatch):
    monkeypatch.setenv("NOVA_BOOK_WATCH", "0")
    assert big_read.live_reading("AAPL")["reason"].startswith("The book watcher is off")


def test_the_route_reads_the_live_line(worker_on):
    from main import app

    _feed_live("AAPL", time.time() - 5)
    body = TestClient(app).get("/api/book-watch/aapl/big-sellers").json()
    assert body["schema_version"] == 1 and body["source"] == "live" and body["watching"] is True
    assert body["reason"] is None and body["sellers"][0]["price"] == 4.50 and body["sellers"][0]["state"] == "holding"
    assert body["rule"]["median_mult"] == 5.0 and "never acted on" in body["note"]


def test_the_sensor_answers_the_same_reading(worker_on):
    from main import app

    client = TestClient(app)
    missing = client.get("/sensors/big-sellers", params={"symbol": "ZZZZ"}).json()
    assert missing["sensor"] == "big-sellers" and "No Level 2 line for ZZZZ" in missing["error"]
    _feed_live("AAPL", time.time() - 5)
    found = client.get("/sensors/big-sellers", params={"symbol": "AAPL"}).json()
    assert found.get("error") is None and found["data"]["sellers"][0]["kind"] == "big_seller"


def test_the_live_worker_journals_the_call(worker_on):
    events = []
    events += live.process(("print", "AAPL", 0.5, 4.47, 100, True, ""))
    for i in range(5):
        events += live.process(("book", "AAPL", 1.0 + i, BIDS, asks()))
    assert [e["state"] for e in bigs(events)] == ["holding"]


def _capture(books, prints, key="2026-10-12|TEST"):
    return SimpleNamespace(key=key, symbol="TEST", l2=books, l2_keys=[b["ts"] for b in books], prints=prints,
                           print_keys=[p["ts"] for p in prints], spans=[])


def _recorded():
    books = [{"ts": 1000.0 + i, "bids": BIDS, "asks": asks()} for i in range(10)]
    prints = [{"ts": 999.5, "price": 4.47, "size": 100, "exchange": "NASDAQ", "conditions": ""},
              {"ts": 1008.5, "price": 4.51, "size": 200, "exchange": "NASDAQ", "conditions": ""}]
    return _capture(books, prints)


def test_the_replay_reads_the_recording_up_to_the_playhead_only(worker_on):
    data = _recorded()
    early = big_replay.reading(data, 1002.0, num_rows=10)
    assert early["watching"] is True and early["sellers"] == []            # 2 s: not yet held
    mid = big_replay.reading(data, 1005.0, num_rows=10)
    assert mid["sellers"][0]["state"] == "holding" and mid["sellers"][0]["held_sec"] == 5.0
    late = big_replay.reading(data, 1009.0, num_rows=10)
    assert late["sellers"][0]["state"] == "eaten"                          # the 4.51 print went through
    back = big_replay.reading(data, 1005.0, num_rows=10)                    # a rewind rebuilds: no later word
    assert back["sellers"][0]["state"] == "holding"


def test_the_replay_with_no_recent_book_says_so(worker_on):
    data = _recorded()
    stale = big_replay.reading(data, 1030.0, num_rows=10)
    assert stale["watching"] is False and stale["last_book_age_sec"] == 21.0


def test_the_replay_desk_reads_the_loaded_session_record(worker_on, monkeypatch):
    from sim import capture_player

    monkeypatch.setattr(big_read, "_replay_desk", lambda: True)
    monkeypatch.setattr(capture_player, "asof_unix", lambda: 1005.0)
    monkeypatch.setattr(capture_player, "snapshot", lambda: None)
    assert "none is loaded" in big_read.reading("TEST")["reason"]
    monkeypatch.setattr(capture_player, "snapshot", lambda: _recorded())
    body = big_read.reading("TEST")
    assert body["source"] == "replay" and body["watching"] is True and body["sellers"][0]["price"] == 4.50
    monkeypatch.setattr(capture_player, "snapshot", lambda: _capture([], [{"ts": 1.0, "price": 4.0, "size": 1}]))
    assert "kept no Level 2 book" in big_read.reading("TEST")["reason"]


def test_a_session_record_replay_reports_the_last_word_on_each(tmp_path):
    import json

    rec = tmp_path / "TEST"
    rec.mkdir()
    books = [{"ts": 1.0 + i, "bids": BIDS, "asks": asks()} for i in range(5)]
    prints = [{"ts": 0.5, "price": 4.47, "size": 100, "exchange": "NASDAQ"},
              {"ts": 6.0, "price": 4.51, "size": 100, "exchange": "NASDAQ"}]
    (rec / "l2.jsonl").write_text("\n".join(json.dumps(b) for b in books) + "\n")
    (rec / "prints.jsonl").write_text("\n".join(json.dumps(p) for p in prints) + "\n")
    result = replay(rec)
    assert [(b["price"], b["state"]) for b in result["big"]] == [(4.50, "eaten")]


def test_the_tracker_alone_takes_side_views():
    t = BigWallTracker("TEST")
    t.on_print(0.5, 4.47, 100, lit=True, conditions="")
    prev = None
    for ts in (1.0, 2.0, 3.0, 4.0):
        views = {"bid": side_view(BIDS, "bid", 10), "ask": side_view(asks(), "ask", 10)}
        out = t.on_book(ts, views, prev)
        prev = views
    assert out and out[0]["state"] == "holding"
