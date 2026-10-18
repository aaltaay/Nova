"""The book watcher on the Level 2 ladder (ADR 033 amendment, 2026-09-29): every large level that
leaves is a verdict (traded or pulled), each side has its totals, and the depth socket carries them."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from book_watch import ladder, live
from book_watch.constants_book_watch import (
    BOOK_WATCH_LADDER_MEMORY_SEC,
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
    assert sides["bid"] == {"pulled_shares": 5000, "filled_shares": 0, "large_pulls": 1, "hidden_shares": 0}
    assert sides["ask"] == {"pulled_shares": 0, "filled_shares": 2000, "large_pulls": 0, "hidden_shares": 0}


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
    assert absent["watching"] is False and absent["source"] == "replay" and absent["drops"] == []
    assert "No Session Record of AAPL is loaded" in absent["reason"]
    assert push.frame(now + 1, live_line=False) is None
    back = push.frame(now + 2)
    assert back["reset"] is True and back["source"] == "live" and [d["price"] for d in back["drops"]] == [9.99]


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
        assert frame["data"]["watching"] is False and "AAPL" in frame["data"]["reason"]


# -- Sim replay ladder adapter (#617) -------------------------------------------

def _capture_ns(symbol="SSTI", key="2026-09-29|SSTI", books=(), prints=(), spans=()):
    from types import SimpleNamespace

    b_list = list(books)
    p_list = list(prints)
    return SimpleNamespace(
        key=key,
        symbol=symbol,
        l2=b_list,
        l2_keys=[float(b["ts"]) for b in b_list],
        prints=p_list,
        print_keys=[float(p["ts"]) for p in p_list],
        spans=list(spans),
    )


def test_replay_ladder_shows_matched_unmatched_and_mixed_drops_without_lookahead(worker_on, monkeypatch):
    from sim import capture_player

    bids = [lv(8.15, 300), lv(8.14, 300), lv(8.13, 300), lv(8.05, 5800)]
    asks_t0 = [lv(8.19, 3000), lv(8.20, 2500), lv(8.26, 300), lv(8.27, 300), lv(8.28, 300)]
    # 8.25 offer is posted at t=1000.2 (6 ticks above 8.19), then best ask steps up to 8.20 and 8.25 is pulled.
    asks_t1 = [lv(8.19, 3000), lv(8.20, 2500), lv(8.25, 2000), lv(8.26, 300), lv(8.27, 300), lv(8.28, 300)]
    asks_t2 = [lv(8.20, 500), lv(8.25, 2000), lv(8.26, 300), lv(8.27, 300), lv(8.28, 300)]  # 8.19 (3000) traded, 8.20 (2000) mixed
    asks_t3 = [lv(8.20, 500), lv(8.26, 300), lv(8.27, 300), lv(8.28, 300)]                    # 8.25 (2000) pulled on approach; 8.05 bid pulled
    bids_t3 = [lv(8.15, 300), lv(8.14, 300), lv(8.13, 300)]
    books = [
        {"ts": 1000.0, "bids": bids, "asks": asks_t0},
        {"ts": 1000.2, "bids": bids, "asks": asks_t1},
        {"ts": 1001.0, "bids": bids, "asks": asks_t2},
        {"ts": 1002.0, "bids": bids_t3, "asks": asks_t3},
    ]
    prints = [
        {"ts": 1000.9, "price": 8.19, "size": 3000, "exchange": "NASDAQ", "conditions": ""},
        {"ts": 1001.0, "price": 8.20, "size": 800, "exchange": "NASDAQ", "conditions": ""},
    ]
    data = _capture_ns(books=books, prints=prints)
    monkeypatch.setattr(capture_player, "snapshot", lambda: data)
    push = ladder.LadderPush("SSTI")

    # At 1001.3, the drops at 1001.0 have not reached their 0.75 s settle deadline (1001.75): no flush lookahead.
    early = push.frame(1001.3, live_line=False)
    assert early["watching"] is True and early["source"] == "replay" and early["drops"] == []

    # At 1001.8, the 1001.0 drops settle (8.19 traded 3000; 8.20 mixed: 800 filled, 1200 pulled), but 1002.0 has not happened.
    mid = push.frame(1001.8, live_line=False)
    assert mid["reset"] is False and mid["now"] == 1001.8
    by_px = {d["price"]: d for d in mid["drops"]}
    assert set(by_px) == {8.19, 8.20}
    assert by_px[8.19]["outcome"] == "traded" and by_px[8.19]["filled"] == 3000 and by_px[8.19]["pulled"] == 0
    assert by_px[8.20]["outcome"] == "pulled" and by_px[8.20]["filled"] == 800 and by_px[8.20]["pulled"] == 1200

    # At 1003.0, the 1002.0 drops settle (8.25 pulled on approach; 8.05 bid pulled 5800).
    late = push.frame(1003.0, live_line=False)
    by_px_late = {d["price"]: d for d in late["drops"]}
    assert set(by_px_late) == {8.25, 8.05}
    assert by_px_late[8.25]["on_approach"] is True and by_px_late[8.25]["pulled"] == 2000
    assert by_px_late[8.05]["side"] == "bid" and by_px_late[8.05]["pulled"] == 5800
    assert late["sides"]["ask"]["filled_shares"] == 3800 and late["sides"]["ask"]["pulled_shares"] == 3200
    assert late["sides"]["bid"]["pulled_shares"] == 5800


def test_replay_claims_prints_once_and_honors_sweeps_refills_and_view_loss(worker_on, monkeypatch):
    from sim import capture_player

    bids = [lv(9.90, 300), lv(9.89, 300), lv(9.88, 300)]
    # 1) One 2000-share print at 10.00 cannot fill two 2000-share drops at 10.00.
    # 2) Sweep at 10.02 proves the 10.01 ask (1500) traded even when the book shows it gone 1.3 s later;
    #    a refill at 10.01 (2000) after the sweep that then vanishes without prints still reads pulled.
    # 3) A deep ask at 10.10 that scrolls past the 5-row cutoff is unknown, never pulled.
    tail = [lv(10.02, 300), lv(10.03, 300), lv(10.05, 300)]
    books = [
        {"ts": 100.0, "bids": bids, "asks": [lv(10.00, 4000), lv(10.01, 1500), *tail[:2]]},
        {"ts": 100.2, "bids": bids, "asks": [lv(10.00, 2000), lv(10.01, 1500), *tail[:2]]},
        {"ts": 100.3, "bids": bids, "asks": [lv(10.01, 1500), *tail, lv(10.10, 5000)][:4]},
        {"ts": 101.6, "bids": bids, "asks": [*tail, lv(10.10, 5000)]},
        {"ts": 102.0, "bids": bids, "asks": [lv(10.01, 2000), *tail, lv(10.06, 300)]},  # 5 rows: 10.10 scrolled past cutoff 10.06
        {"ts": 102.5, "bids": bids, "asks": [*tail, lv(10.06, 300)]},                   # refilled 10.01 pulled
    ]
    prints = [
        {"ts": 100.1, "price": 10.00, "size": 2000, "exchange": "NASDAQ", "conditions": ""},
        {"ts": 100.4, "price": 10.01, "size": 1500, "exchange": "NASDAQ", "conditions": ""},
        {"ts": 100.4, "price": 10.02, "size": 100, "exchange": "NASDAQ", "conditions": ""},  # sweep through 10.01
    ]
    data = _capture_ns(books=books, prints=prints)
    monkeypatch.setattr(capture_player, "snapshot", lambda: data)
    from book_watch import ladder_replay

    view = ladder_replay.ladder_view("SSTI", None, 104.0, num_rows=5)
    drops = [(d["ts"], d["price"], d["outcome"], d["filled"], d["pulled"]) for d in view["drops"]]
    assert drops == [
        (100.2, 10.00, "traded", 2000.0, 0.0),   # claimed the single 2000 print
        (100.3, 10.00, "pulled", 0.0, 2000.0),   # print already claimed once
        (101.6, 10.01, "traded", 1500.0, 0.0),   # late-book drop recovered by the sweep at 100.4
        (102.5, 10.01, "pulled", 0.0, 2000.0),   # refill after the sweep reads pulled
    ]  # 10.10 scrolling past the 5-row cutoff at 102.0 was never judged pulled


def test_replay_rewind_gap_missing_streams_and_l1_fallback_are_honest(worker_on, monkeypatch):
    from sim import capture_player

    bids = [lv(9.90, 300), lv(9.89, 300), lv(9.88, 300)]
    books = [
        {"ts": 50.0, "bids": bids, "asks": [lv(10.00, 5000), lv(10.01, 300), lv(10.02, 300)]},
        {"ts": 50.2, "bids": bids, "asks": [lv(10.01, 300), lv(10.02, 300)]},
        # Second segment after a gap [55.0, 200.0]:
        {"ts": 200.0, "bids": bids, "asks": [lv(10.05, 300), lv(10.06, 300)]},
        {"ts": 201.0, "bids": bids, "asks": [lv(10.05, 300)], "l1_fallback": True},
    ]
    prints = [
        {"ts": 49.9, "price": 10.00, "size": 100, "exchange": "NASDAQ", "conditions": ""},
        {"ts": 200.0, "price": 10.05, "size": 100, "exchange": "NASDAQ", "conditions": ""},
    ]
    data = _capture_ns(books=books, prints=prints, spans=[(49.0, 55.0), (200.0, 210.0)])
    monkeypatch.setattr(capture_player, "snapshot", lambda: data)
    push = ladder.LadderPush("SSTI")

    # Pre-first-book moment:
    before = push.frame(49.5, live_line=False)
    assert before["watching"] is False and "no Level 2 book" in before["reason"] and before["sides"] is None

    # At 51.0, the pull at 50.2 is visible:
    at_51 = push.frame(51.0, live_line=False)
    assert at_51["watching"] is True and at_51["reset"] is True and [d["price"] for d in at_51["drops"]] == [10.0]

    # Rewind to 50.1 (before the 50.2 pull): rebuilds deterministically and clears future drops.
    rewound = push.frame(50.1, live_line=False)
    assert rewound["watching"] is True and rewound["reset"] is True and rewound["drops"] == []
    assert rewound["sides"]["ask"]["pulled_shares"] == 0

    # Forward again to 51.0, then into the gap at 100.0:
    assert [d["price"] for d in push.frame(51.0, live_line=False)["drops"]] == [10.0]
    in_gap = push.frame(100.0, live_line=False)
    assert in_gap["watching"] is False and "between recorded stretches" in in_gap["reason"] and in_gap["drops"] == []

    # After the gap at 200.5: no marks or totals from segment 1 carry across the gap.
    seg2 = push.frame(200.5, live_line=False)
    assert seg2["watching"] is True and seg2["reset"] is True and seg2["drops"] == []
    assert seg2["sides"]["ask"]["pulled_shares"] == 0

    # At 201.2, the book is l1_fallback: reports unavailable rather than watching with zero totals.
    l1_only = push.frame(201.2, live_line=False)
    assert l1_only["watching"] is False and "Level 1" in l1_only["reason"] and l1_only["sides"] is None

    # Missing tape or missing depth:
    monkeypatch.setattr(capture_player, "snapshot", lambda: _capture_ns(books=books[:2], prints=[]))
    no_tape = push.frame(51.0, live_line=False)
    assert no_tape["watching"] is False and "Time & Sales" in no_tape["reason"] and no_tape["sides"] is None


def test_historical_snapshot_includes_book_watch_for_recorded_depth_and_reasons_when_absent(worker_on, tmp_path, monkeypatch):
    import l2.batch as l2_batch
    import l2.db as l2_db
    from l2.store import record_snapshot
    from l2.tape import persist_prints
    from sim import history_depth, history_playback as playback, history_store as store, session_clock as clock

    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setattr(l2_db, "cache_dir", lambda: tmp_path)
    l2_batch.clear_queues_for_tests()
    clock.reset_for_tests()
    playback.clear()
    history_depth.clear()
    try:
        spec = store.window("IMCC", "2026-09-18", "04:00", "09:30")
        t0 = spec["start_ts"] + 60
        job = store.create(spec, "trades")
        store.commit_page(job["id"], spec["start_ts"], [dict(ts=t0, price=10.0, size=100)], spec["end_ts"], True)
        playback.select(spec)
        clock.set_paused(True)

        # Unrecorded moment: book_watch is present with watching=False and a clear reason.
        clock.scrub_to_second(10)
        unrecorded = playback.snapshot("IMCC")
        assert unrecorded["book_watch"]["watching"] is False
        assert "not recorded" in unrecorded["book_watch"]["reason"].lower()

        # Recorded L2 + tape at t0..t0+2:
        l2_db.init_db()
        bids = [lv(9.90, 300), lv(9.89, 300), lv(9.88, 300)]
        record_snapshot("rec-1", "IMCC", "depth", t0, t0,
                        {"bids": bids, "asks": [lv(10.00, 5000), lv(10.01, 300), lv(10.02, 300)], "l1_fallback": False},
                        session_id="s1")
        record_snapshot("rec-1", "IMCC", "depth", t0, t0 + 0.5,
                        {"bids": bids, "asks": [lv(10.01, 300), lv(10.02, 300)], "l1_fallback": False},
                        session_id="s1")
        persist_prints([{"symbol": "IMCC", "ts": t0 + 0.4, "receive_ts": t0 + 0.4, "price": 10.00, "size": 2000,
                         "exchange": "NASDAQ", "source": "ibkr", "session_id": "s1", "conditions": ""}])
        history_depth.clear()

        clock.scrub_to_second(62)
        snap = playback.snapshot("IMCC")
        bw = snap["book_watch"]
        assert bw["watching"] is True and bw["source"] == "replay" and bw["now"] == t0 + 2
        assert len(bw["drops"]) == 1
        assert bw["drops"][0]["price"] == 10.00 and bw["drops"][0]["filled"] == 2000 and bw["drops"][0]["pulled"] == 3000
        assert bw["sides"]["ask"]["filled_shares"] == 2000 and bw["sides"]["ask"]["pulled_shares"] == 3000
    finally:
        l2_batch.clear_queues_for_tests()
        clock.reset_for_tests()
        playback.clear()
        history_depth.clear()
