"""Hidden sellers and buyers (ADR 033 amendment, 2026-09-30): more traded at a price that held than
the book ever showed there -- the watcher's rule, its ladder frames, the sensor, the study and the
stock read's row."""
from __future__ import annotations

import json

import pytest

from book_watch import hidden_study, live
from book_watch.constants_book_watch import (
    BOOK_WATCH_HIDDEN_MIN_HOLD_SEC,
    BOOK_WATCH_HIDDEN_MIN_SHARES,
    BOOK_WATCH_HIDDEN_SHOWN_MULT,
)
from book_watch.detector import SymbolWatch
from book_watch.ladder import LadderPush
from book_watch.replay import replay


def lv(price, size, mm="NSDQ"):
    return {"price": price, "size": size, "mm": mm}


BIDS = [lv(10.00, 500), lv(9.99, 400), lv(9.98, 300)]


def asks(inside=300, at=10.05):
    return [lv(at, inside), lv(at + 0.01, 800), lv(at + 0.02, 900)]


def absorb(w, *, start=1.0, seconds=12, each=250, price=10.05, shown=300, side="ask", conditions=""):
    """A book every second (the offer at ``price`` keeps showing ``shown``) and a print there each second."""
    events = []
    for i in range(seconds):
        t = start + i
        if side == "ask":
            events += w.on_book(t, BIDS, asks(shown, price))
        else:
            events += w.on_book(t, [lv(price, shown), lv(price - 0.01, 400)], asks())
        events += w.on_print(t + 0.5, price, each, lit=True, conditions=conditions)
    return events


def hidden_events(events):
    return [e for e in events if e["event"] == "hidden"]


def test_the_defaults_are_the_measured_rule():
    assert (BOOK_WATCH_HIDDEN_MIN_HOLD_SEC, BOOK_WATCH_HIDDEN_MIN_SHARES, BOOK_WATCH_HIDDEN_SHOWN_MULT) == (10.0, 2000, 3.0)


def test_an_offer_that_keeps_taking_more_than_it_shows_is_a_hidden_seller():
    w = SymbolWatch("TEST", num_rows=10)
    events = hidden_events(absorb(w))
    first = events[0]
    assert first["kind"] == "hidden_seller" and first["side"] == "ask" and first["price"] == 10.05
    assert first["state"] == "holding" and first["shown_max"] == 300
    # Flagged at the first print 10 s after the first one: 11 prints of 250.
    assert first["flagged_ts"] == 11.5 and first["printed"] == 2750 and first["hidden"] == 2750 - 300
    assert first["started_ts"] == 1.5 and first["id"].endswith("-TEST-ask-10.05")


def test_a_sweep_is_no_one_holding_anything():
    w = SymbolWatch("TEST", num_rows=10)
    w.on_book(1.0, BIDS, asks(300))
    out = []
    for i in range(20):  # 5,000 at 10.05, then through it in the same second
        out += w.on_print(1.1 + i * 0.001, 10.05, 250, lit=True)
    out += w.on_print(1.2, 10.06, 100, lit=True)
    out += w.tick(30.0)
    assert hidden_events(out) == []


def test_an_offer_that_showed_its_size_is_not_hidden():
    w = SymbolWatch("TEST", num_rows=10)
    assert hidden_events(absorb(w, shown=5000)) == []  # 3,000 printed against 5,000 shown


def test_a_stretch_speaks_as_it_grows_and_once_when_it_ends():
    w = SymbolWatch("TEST", num_rows=10)
    events = absorb(w, seconds=15)
    events += w.on_book(16.0, BIDS, asks(300))
    events += w.on_print(16.5, 10.06, 100, lit=True)   # through the offer
    words = hidden_events(events)
    assert len({e["id"] for e in words}) == 1
    assert [e["state"] for e in words][:-1] == ["holding"] * (len(words) - 1)
    assert words[-1]["state"] == "broke" and words[-1]["ended_ts"] == 16.5
    assert words[-1]["printed"] == 15 * 250 and words[-1]["hidden"] == 15 * 250 - 300


def test_a_stretch_with_no_print_for_the_gap_fades():
    w = SymbolWatch("TEST", num_rows=10)
    absorb(w)
    last = hidden_events(w.tick(40.0))
    assert last and last[-1]["state"] == "faded" and last[-1]["ended_ts"] == 12.5 + 10.0


def test_a_hidden_buyer_is_the_bid_side_mirror():
    w = SymbolWatch("TEST", num_rows=10)
    words = hidden_events(absorb(w, side="bid", price=10.00))
    assert words and words[0]["kind"] == "hidden_buyer" and words[0]["side"] == "bid"


def test_cross_off_exchange_and_volume_only_prints_never_count():
    for kwargs in ({"conditions": "4 W"}, {"conditions": "O X"}):
        w = SymbolWatch("TEST", num_rows=10)
        assert hidden_events(absorb(w, **kwargs)) == [], kwargs
    w = SymbolWatch("TEST", num_rows=10)
    out = []
    for i in range(12):
        out += w.on_book(1.0 + i, BIDS, asks(300))
        out += w.on_print(1.5 + i, 10.05, 250, lit=False)  # FINRA
    assert hidden_events(out) == []


def test_a_cross_print_ends_both_sides():
    w = SymbolWatch("TEST", num_rows=10)
    absorb(w)
    words = hidden_events(w.on_print(13.0, 10.05, 50_000, lit=True, conditions="O X"))
    assert words and words[-1]["state"] == "auction"
    assert w.hidden.active == {"bid": None, "ask": None}


def test_no_fresh_book_means_nothing_is_judged():
    """A Session Record can keep the tape after its depth line is gone: a stale book calls everything hidden."""
    w = SymbolWatch("TEST", num_rows=10)
    w.on_book(1.0, BIDS, asks(300))
    out = []
    for i in range(20):
        out += w.on_print(10.0 + i, 10.05, 500, lit=True)
    assert hidden_events(out) == []


def test_a_midpoint_print_is_at_neither_side():
    w = SymbolWatch("TEST", num_rows=10)
    w.on_book(1.0, [lv(3.65, 500)], [lv(3.66, 500)])
    w.on_print(1.5, 3.655, 1000, lit=True)
    assert w.hidden.active == {"bid": None, "ask": None}


def test_a_reset_ends_a_stretch_without_a_verdict():
    w = SymbolWatch("TEST", num_rows=10)
    absorb(w, seconds=5)  # not held long enough yet
    assert w.hidden.active["ask"] is not None
    assert hidden_events(w.reset()) == []
    assert w.hidden.active["ask"] is None


def test_side_totals_carry_the_hidden_size_of_flagged_prices():
    w = SymbolWatch("TEST", num_rows=10)
    absorb(w)
    sides = w.totals(13.0)["sides"]
    assert sides["ask"]["hidden_shares"] == 3000 - 300 and sides["bid"]["hidden_shares"] == 0


# -- the ladder, the sensor ----------------------------------------------------

@pytest.fixture
def worker_on(monkeypatch):
    monkeypatch.setenv("NOVA_BOOK_WATCH", "1")
    monkeypatch.setenv("NOVA_BOOK_WATCH_JOURNAL", "0")
    monkeypatch.setattr(live, "_ensure_thread", lambda: None)
    live.reset_for_tests()
    yield
    live.reset_for_tests()


def _feed_absorption(symbol="AAPL", seconds=12):
    w = live._watches.setdefault(symbol, SymbolWatch(symbol, num_rows=10))
    return absorb(w, seconds=seconds)


def test_the_ladder_hears_a_hidden_seller_once_then_what_is_new(worker_on):
    _feed_absorption()
    push = LadderPush("AAPL")
    first = push.frame(now=13.0)
    assert first["reset"] is True and len(first["hidden"]) == 1
    word = first["hidden"][0]
    assert word["kind"] == "hidden_seller" and word["state"] == "holding" and "seq" in word
    assert push.frame(now=13.3) is None  # nothing new
    w = live._watches["AAPL"]
    w.on_print(13.5, 10.06, 100, lit=True)
    later = push.frame(now=14.0)
    assert [h["state"] for h in later["hidden"]] == ["broke"]
    assert later["sides"]["ask"]["hidden_shares"] > 0


def test_a_new_socket_gets_each_stretch_last_word_only(worker_on):
    _feed_absorption(seconds=15)
    live._watches["AAPL"].on_print(16.5, 10.06, 100, lit=True)
    view = live.ladder_view("AAPL", None, now=20.0)
    assert [h["state"] for h in view["hidden"]] == ["broke"]
    assert live.ladder_view("AAPL", None, now=200.0)["hidden"] == []  # ended long ago: out of the memory


def test_the_sensors_read_the_watcher(worker_on, monkeypatch):
    from book_watch.view import book_pull_events, book_pulls
    from sensors.adapters import bookish

    monkeypatch.setattr(live.time, "time", lambda: 13.0)  # the time module: the watcher's clock
    monkeypatch.setattr(bookish, "get_prints", lambda symbol, limit=20: ([], None))
    monkeypatch.setattr(bookish, "get_book", lambda symbol: (None, None))
    assert bookish.read_flow("AAPL")["data"]["iceberg_hint"] is None  # no depth line: unknown, not "none"
    _feed_absorption()
    data, error = book_pulls("AAPL")
    assert error is None and data["hidden_recent"][0]["kind"] == "hidden_seller" and data["hidden_note"]
    assert book_pull_events(0.0, "AAPL")["hidden"][0]["price"] == 10.05
    flow = bookish.read_flow("AAPL")["data"]
    assert flow["iceberg_hint"] is True and flow["hidden"]["stretches"][0]["side"] == "ask"


def test_a_watched_line_with_nothing_hidden_says_false(worker_on, monkeypatch):
    from sensors.adapters import bookish

    w = live._watches.setdefault("AAPL", SymbolWatch("AAPL", num_rows=10))
    w.on_book(12.0, BIDS, asks(300))
    monkeypatch.setattr(live.time, "time", lambda: 13.0)
    monkeypatch.setattr(bookish, "get_prints", lambda symbol, limit=20: ([], None))
    monkeypatch.setattr(bookish, "get_book", lambda symbol: (None, None))
    assert bookish.read_flow("AAPL")["data"]["iceberg_hint"] is False


# -- the replay and the study ----------------------------------------------------

def _recording(tmp_path, *, shown=300):
    rec = tmp_path / "2026-09-29" / "TEST"
    rec.mkdir(parents=True)
    books, prints = [], []
    for i in range(40):
        t = 1000.0 + i
        books.append({"ts": t, "bids": BIDS, "asks": asks(shown)})
        if i < 14:
            prints.append({"ts": t + 0.5, "receive_ts": t + 0.5, "price": 10.05, "size": 250, "exchange": "NASDAQ",
                           "conditions": ""})
    prints.append({"ts": 1000.2, "receive_ts": 1000.2, "price": 10.05, "size": 90_000, "exchange": "NASDAQ",
                   "conditions": "5 X"})  # a reopening cross before the buying: never counted
    prints.sort(key=lambda p: p["ts"])
    (rec / "l2.jsonl").write_text("\n".join(json.dumps(b) for b in books) + "\n")
    (rec / "prints.jsonl").write_text("\n".join(json.dumps(p) for p in prints) + "\n")
    return rec


def test_the_replay_keeps_each_stretch_last_word(tmp_path):
    result = replay(_recording(tmp_path))
    assert [(h["kind"], h["state"]) for h in result["hidden"]] == [("hidden_seller", "faded")]
    assert result["hidden"][0]["printed"] == 14 * 250  # the cross print never counted


def test_the_study_splits_flagged_from_busy_and_measures_what_came_next(tmp_path):
    flagged = hidden_study.read(_recording(tmp_path))
    shown = hidden_study.read(_recording(tmp_path / "wall", shown=5000))
    assert [e["group"] for e in hidden_study.events(flagged, 2000, 3.0, 10.0)] == ["flagged"]
    busy = hidden_study.events(shown, 2000, 3.0, 10.0)
    assert [e["group"] for e in busy] == ["busy"]
    ev = hidden_study.events(flagged, 2000, 3.0, 10.0)[0]
    assert ev["held_sec"] >= 10 and ev["horizons"]["10"]["broke"] is False  # the offer held
    assert ev["horizons"]["10"]["toward_bp"] == 0 and "300" not in ev["horizons"]  # past the recording: unmeasured
    answer = hidden_study.study([flagged, shown], min_shares=2000, shown_mult=3.0, min_hold=10.0)
    assert answer["groups"]["flagged_ask"]["n"] == 1 and answer["groups"]["busy_ask"]["n"] == 1
    assert answer["schema_version"] == 1 and answer["rule"]["min_hold_sec"] == 10.0


# -- the stock read's row ----------------------------------------------------------

def test_the_tape_tile_names_a_hidden_seller_holding():
    from stock_read.rows_trade import _hidden_row

    word = {"kind": "hidden_seller", "side": "ask", "price": 5.0, "state": "holding", "hidden": 12_400,
            "printed": 14_400, "shown_max": 2000, "ts": 100.0, "started_ts": 91.0, "last_print_ts": 100.0}
    r = _hidden_row({"watching": True, "hidden_recent": [word]}, 101.0, "no line")
    assert r["state"] == "warn" and r["value"] == "Seller at 5.00: 12.4K beyond 2K shown"
    assert "14.4K traded at 5.00 over 9 s" in r["detail"] and "37%" in r["detail"]
    assert _hidden_row(None, 101.0, "no line")["state"] == "unknown"
    assert _hidden_row({"watching": True, "hidden_recent": []}, 101.0, "x")["value"] == "None seen"
    buyer = _hidden_row({"watching": True, "hidden_recent": [{**word, "side": "bid", "kind": "hidden_buyer"}]},
                        101.0, "x")
    assert buyer["state"] == "info" and buyer["value"].startswith("Buyer at 5.00")
