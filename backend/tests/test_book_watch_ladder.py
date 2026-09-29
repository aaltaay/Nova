"""The book watcher on the Level 2 ladder (ADR 033 amendment, 2026-09-29): every large level that
leaves is a verdict (traded or pulled), each side has its totals, and the depth socket carries them."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from book_watch import ladder, live
from book_watch.constants_book_watch import (
    BOOK_WATCH_LADDER_MEMORY_SEC,
    BOOK_WATCH_NOT_LIVE_REASON,
    BOOK_WATCH_SIDES_PUSH_SEC,
)
from book_watch.detector import SymbolWatch


def lv(price, size, mm="NSDQ"):
    return {"price": price, "size": size, "mm": mm}


ASKS = [lv(10.05, 300)]


def drops_of(events):
    return [e for e in events if e["event"] == "drop"]


# -- the detector's verdicts ---------------------------------------------------

def test_a_large_level_that_trades_away_is_a_traded_drop():
    w = SymbolWatch("TEST", num_rows=10)
    w.on_book(1.0, [lv(10.0, 5000), lv(9.99, 300), lv(9.98, 300)], ASKS)
    w.on_print(1.1, 10.0, 5000, lit=True)
    w.on_book(1.2, [lv(9.99, 300), lv(9.98, 300)], ASKS)
    events = w.tick(5.0)
    (drop,) = drops_of(events)
    assert drop["outcome"] == "traded" and drop["filled"] == 5000 and drop["pulled"] == 0
    assert drop["dropped"] == 5000 and drop["large_pull"] is False and drop["on_approach"] is False
    assert not [e for e in events if e["event"] == "pull"]  # the pull feed and its flags are unchanged


def test_a_large_level_that_vanishes_unprinted_is_a_pulled_drop_beside_its_pull():
    w = SymbolWatch("TEST", num_rows=10)
    w.on_book(1.0, [lv(10.0, 300), lv(9.99, 5000), lv(9.98, 300)], ASKS)
    w.on_book(1.2, [lv(10.0, 300), lv(9.98, 300)], ASKS)
    events = w.tick(5.0)
    (drop,) = drops_of(events)
    assert drop["outcome"] == "pulled" and drop["pulled"] == 5000 and drop["large_pull"] is True
    assert drop["level_before"] == 5000 and drop["level_after"] == 0
    assert [e["event"] for e in events].count("pull") == 1


def test_a_split_drop_says_how_much_of_each():
    w = SymbolWatch("TEST", num_rows=10)
    w.on_book(1.0, [lv(10.0, 300), lv(9.99, 4000), lv(9.98, 300)], ASKS)
    w.on_print(1.1, 9.99, 1500, lit=True)
    w.on_book(1.2, [lv(10.0, 300), lv(9.98, 300)], ASKS)
    (drop,) = drops_of(w.tick(5.0))
    assert (drop["pulled"], drop["filled"], drop["outcome"]) == (2500, 1500, "pulled")


def test_a_small_drop_is_no_verdict():
    w = SymbolWatch("TEST", num_rows=10)
    w.on_book(1.0, [lv(10.0, 300), lv(9.99, 400), lv(9.98, 300)], ASKS)
    w.on_book(1.2, [lv(10.0, 300), lv(9.98, 300)], ASKS)
    assert drops_of(w.tick(5.0)) == []


def test_the_drop_carries_the_pulled_on_approach_rule():
    w = SymbolWatch("TEST", num_rows=10)
    w.on_book(1.0, [lv(10.0, 300), lv(9.99, 300), lv(9.97, 300)], ASKS)
    w.on_book(1.1, [lv(10.0, 300), lv(9.99, 300), lv(9.98, 5000), lv(9.97, 300)], ASKS)  # posted 2 ticks off
    w.on_book(1.5, [lv(9.99, 300), lv(9.98, 5000), lv(9.97, 300)], ASKS)  # the bid came down to it
    w.on_book(2.0, [lv(9.99, 300), lv(9.97, 300)], ASKS)
    events = w.tick(9.0)
    (drop,) = drops_of(events)
    assert drop["on_approach"] is True and drop["lifetime_sec"] == 0.9
    assert [e["kind"] for e in events if e["event"] == "flag"] == ["pulled_on_approach"]


def test_each_side_keeps_its_own_totals():
    w = SymbolWatch("TEST", num_rows=10)
    w.on_book(1.0, [lv(10.0, 300), lv(9.99, 5000), lv(9.98, 300)], [lv(10.05, 300), lv(10.06, 2000)])
    w.on_print(1.1, 10.06, 2000, lit=True)
    w.on_book(1.2, [lv(10.0, 300), lv(9.98, 300)], [lv(10.05, 300)])
    w.tick(5.0)
    sides = w.totals(5.0)["sides"]
    assert sides["bid"] == {"pulled_shares": 5000, "filled_shares": 0, "large_pulls": 1}
    assert sides["ask"] == {"pulled_shares": 0, "filled_shares": 2000, "large_pulls": 0}


# -- the ladder's view of a live line -----------------------------------------

@pytest.fixture
def worker_on(monkeypatch):
    monkeypatch.setenv("NOVA_BOOK_WATCH", "1")
    monkeypatch.setenv("NOVA_BOOK_WATCH_JOURNAL", "0")
    monkeypatch.setattr(live, "_ensure_thread", lambda: None)
    live.reset_for_tests()
    yield
    live.reset_for_tests()


def _drain():
    while not live._q.empty():
        live.process(live._q.get_nowait())


def _pull(symbol, price):
    """A 5,000-share bid at ``price`` posted, then gone without a print."""
    live.enqueue_book(symbol, {"bids": [lv(10.0, 300), lv(price, 5000), lv(9.90, 300)], "asks": ASKS})
    live.enqueue_book(symbol, {"bids": [lv(10.0, 300), lv(9.90, 300)], "asks": ASKS})
    _drain()
    watch = live._watches[symbol]
    live.tick(watch.last_book_ts + 1)


def test_the_view_sends_the_last_minute_then_only_what_is_new(worker_on):
    _pull("AAPL", 9.99)
    first = live.ladder_view("AAPL", None)
    assert [d["price"] for d in first["drops"]] == [9.99] and first["seq"] == 1 and first["watching"]
    assert live.ladder_view("AAPL", first["seq"])["drops"] == []
    _pull("AAPL", 9.98)
    assert [d["price"] for d in live.ladder_view("AAPL", first["seq"])["drops"]] == [9.98]
    later = live._watches["AAPL"].last_book_ts + BOOK_WATCH_LADDER_MEMORY_SEC + 5
    assert live.ladder_view("AAPL", None, now=later)["drops"] == []  # past the memory
    assert live.ladder_view("ZZZZ", None) is None


def test_one_socket_hears_each_verdict_once(worker_on):
    _pull("AAPL", 9.99)
    push = ladder.LadderPush("aapl")
    now = live._watches["AAPL"].last_book_ts + 1
    first = push.frame(now)
    assert first["reset"] is True and [d["price"] for d in first["drops"]] == [9.99]
    assert first["sides"]["bid"]["pulled_shares"] == 5000 and first["reason"] is None
    assert push.frame(now + 0.1) is None  # nothing new
    _pull("AAPL", 9.98)
    second = push.frame(now + 0.2)
    assert second["reset"] is False and [d["price"] for d in second["drops"]] == [9.98]


def test_the_sides_refresh_on_their_own_no_faster_than_their_clock(worker_on):
    _pull("AAPL", 9.99)
    push = ladder.LadderPush("AAPL")
    now = live._watches["AAPL"].last_book_ts + 1
    push.frame(now)
    # the minute slides past the pull: the totals change with no new verdict
    gone = now + 61
    assert push.frame(gone)["sides"]["bid"]["pulled_shares"] == 0
    push.sides = {"stale": True}
    assert push.frame(gone + BOOK_WATCH_SIDES_PUSH_SEC / 2) is None


def test_a_replay_ladder_is_told_why_once_and_starts_over_when_live(worker_on):
    _pull("AAPL", 9.99)
    push = ladder.LadderPush("AAPL")
    now = live._watches["AAPL"].last_book_ts + 1
    absent = push.frame(now, live_line=False)
    assert absent["watching"] is False and absent["reason"] == BOOK_WATCH_NOT_LIVE_REASON and absent["drops"] == []
    assert push.frame(now + 1, live_line=False) is None
    back = push.frame(now + 2)
    assert back["reset"] is True and [d["price"] for d in back["drops"]] == [9.99]


def test_a_watcher_that_is_off_says_so(worker_on, monkeypatch):
    monkeypatch.setenv("NOVA_BOOK_WATCH", "0")
    frame = ladder.LadderPush("AAPL").frame()
    assert frame["watching"] is False and "NOVA_BOOK_WATCH=0" in frame["reason"]


# -- the depth socket -----------------------------------------------------------

@pytest.fixture
def depth_socket(worker_on, monkeypatch):
    from ibkr import depth as _depth
    from l2 import continuous
    from sim import mode

    async def not_idle(_symbol):
        return False

    monkeypatch.setattr(_depth, "needs_subscribe", lambda _s: False)
    monkeypatch.setattr(_depth, "current_book", lambda _s: {"bids": [lv(10.0, 300)], "asks": ASKS,
                                                           "l1_fallback": False})
    monkeypatch.setattr(_depth, "release_when_idle", not_idle)
    monkeypatch.setattr(continuous, "start", lambda _s: None)
    replay = {"on": False}
    monkeypatch.setattr(mode, "is_replay_desk", lambda: replay["on"])
    return replay


def test_the_depth_socket_carries_the_verdicts_beside_the_books(depth_socket):
    from main import app

    _pull("AAPL", 9.99)
    with TestClient(app).websocket_connect("/ws/ibkr/depth/AAPL") as ws:
        assert ws.receive_json()["type"] == "subscribed"
        assert ws.receive_json()["type"] == "book"
        frame = ws.receive_json()
        assert frame["type"] == "book_watch" and frame["symbol"] == "AAPL"
        (drop,) = frame["data"]["drops"]
        assert drop["price"] == 9.99 and drop["outcome"] == "pulled" and frame["data"]["reset"] is True


def test_a_replay_desk_socket_gets_no_live_verdicts(depth_socket):
    from main import app

    depth_socket["on"] = True
    _pull("AAPL", 9.99)
    with TestClient(app).websocket_connect("/ws/ibkr/depth/AAPL") as ws:
        ws.receive_json()
        ws.receive_json()
        frame = ws.receive_json()
        assert frame["type"] == "book_watch" and frame["data"]["drops"] == []
        assert frame["data"]["reason"] == BOOK_WATCH_NOT_LIVE_REASON
