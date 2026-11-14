"""Size that is back before its drop is judged never left (operator audit 2026-11-13).

IBKR can move its rows down by rewriting each with the one above it; a read that ends partway leaves the
row being carried on no row until the next read. SOC 2026-11-13: a new 0.7448 bid arrived, the 0.7353 bid
of 4,500 was on no row for one book (71 ms), and the watcher judged a 4,500-share pull; the 0.75 ask of
56,100 read "big seller pulled" four times while it rested. Against Nasdaq's own order record, two in three
such drops had nothing leave.
"""
from __future__ import annotations

from book_watch.detector import SymbolWatch


def lv(price, size, mm="NSDQ"):
    return {"price": price, "size": size, "mm": mm}


ASKS = [lv(0.7479, 300)]
BEFORE = [lv(0.7419, 100), lv(0.7415, 100), lv(0.7353, 4500), lv(0.7325, 100), lv(0.7313, 400)]
BLINK = [lv(0.7448, 400), lv(0.7419, 100), lv(0.7415, 100), lv(0.7325, 100), lv(0.7313, 400)]
AFTER = [lv(0.7448, 400), lv(0.7419, 100), lv(0.7415, 100), lv(0.7353, 4500), lv(0.7325, 100), lv(0.7313, 400)]


def judged(events):
    return [(e["event"], e["price"], e["pulled"]) for e in events if e["event"] in ("drop", "pull")]


def test_a_level_gone_for_one_book_and_back_is_no_pull_and_no_mark():
    w = SymbolWatch("SOC", num_rows=10)
    events = w.on_book(1.000, BEFORE, ASKS) + w.on_book(1.165, BLINK, ASKS) + w.on_book(1.236, AFTER, ASKS)
    events += w.flush()
    assert judged(events) == [] and w.returned == 1
    assert w.totals(2.0)["pulled_shares"] == 0 and list(w.drops) == []


def test_a_level_that_stays_gone_is_still_pulled():
    w = SymbolWatch("SOC", num_rows=10)
    events = w.on_book(1.000, BEFORE, ASKS) + w.on_book(1.165, BLINK, ASKS) + w.on_book(1.236, BLINK, ASKS)
    events += w.flush()
    assert judged(events) == [("drop", 0.7353, 4500.0), ("pull", 0.7353, 4500.0)] and w.returned == 0


def test_size_back_only_after_the_verdict_stays_pulled():
    w = SymbolWatch("SOC", num_rows=10)
    events = w.on_book(1.000, BEFORE, ASKS) + w.on_book(1.165, BLINK, ASKS) + w.on_book(2.000, AFTER, ASKS)
    assert ("pull", 0.7353, 4500.0) in judged(events + w.flush())


def test_part_of_the_size_back_is_still_a_drop_of_all_that_left():
    w = SymbolWatch("SOC", num_rows=10)
    part = [lv(0.7353, 3000) if r["price"] == 0.7353 else r for r in AFTER]
    events = w.on_book(1.000, BEFORE, ASKS) + w.on_book(1.165, BLINK, ASKS) + w.on_book(1.236, part, ASKS)
    assert ("pull", 0.7353, 4500.0) in judged(events + w.flush())


def test_the_order_that_was_there_keeps_when_it_was_first_seen():
    w = SymbolWatch("SOC", num_rows=10)
    w.on_book(0.5, [r for r in BEFORE if r["price"] != 0.7353], ASKS)
    w.on_book(1.000, BEFORE, ASKS)           # the 4,500 arrives at t=1
    w.on_book(1.165, BLINK, ASKS)
    w.on_book(1.236, AFTER, ASKS)            # back: the same order, not a new one
    events = w.on_book(9.0, BLINK, ASKS) + w.flush()   # now it really leaves
    pull = next(e for e in events if e["event"] == "pull")
    assert pull["price"] == 0.7353 and pull["lifetime_sec"] == 8.0


# -- a big seller ---------------------------------------------------------------

BIDS = [lv(0.7448, 500), lv(0.7419, 600), lv(0.7415, 700), lv(0.7353, 400)]
WALL = [lv(0.7479, 500), lv(0.7484, 400), lv(0.75, 56100), lv(0.7509, 800), lv(0.7516, 600)]
NO_WALL = [r for r in WALL if r["price"] != 0.75]


def _called(w):
    events = w.on_print(0.5, 0.7470, 100, lit=True)
    for t in (1.0, 2.0, 3.0, 4.0):
        events += w.on_book(t, BIDS, WALL)
    return events


def big_states(events):
    return [e["state"] for e in events if e["event"] == "big"]


def test_a_big_seller_gone_for_one_book_and_back_is_still_holding():
    w = SymbolWatch("SOC", num_rows=10)
    assert big_states(_called(w)) == ["holding"]
    events = w.on_book(5.000, BIDS, NO_WALL) + w.on_book(5.340, BIDS, WALL) + w.on_book(9.0, BIDS, WALL)
    assert big_states(events) == []
    seller = w.big.reading(9.0)["sellers"][0]
    assert seller["state"] == "holding" and seller["size_now"] == 56100 and seller["held_sec"] == 8.0


def test_a_big_seller_back_before_a_late_print_arrives_still_reads_taken():
    w = SymbolWatch("SOC", num_rows=10)
    _called(w)
    events = w.on_book(5.000, BIDS, NO_WALL) + w.on_book(5.100, BIDS, WALL)
    events += w.on_print(5.2, 0.75, 56100, lit=True)       # inside the drop's window, after the size was back
    events += w.on_book(9.0, BIDS, WALL)
    assert big_states(events)[0] == "eaten"


def test_a_big_seller_that_stays_gone_is_still_pulled():
    w = SymbolWatch("SOC", num_rows=10)
    _called(w)
    events = w.on_book(5.000, BIDS, NO_WALL) + w.on_book(5.340, BIDS, NO_WALL) + w.on_book(9.0, BIDS, NO_WALL)
    assert big_states(events) == ["pulled"]


def test_a_level_taken_by_prints_and_posted_again_still_reads_traded_and_never_pulled():
    w = SymbolWatch("SOC", num_rows=10)
    w.on_book(1.000, BEFORE, ASKS)
    w.on_print(1.100, 0.7353, 3000, lit=True)          # 3,000 of the 4,500 printed there
    events = w.on_book(1.165, BLINK, ASKS) + w.on_book(1.236, AFTER, ASKS) + w.flush()
    drops = [e for e in events if e["event"] == "drop"]
    assert [(d["outcome"], d["dropped"], d["filled"], d["pulled"]) for d in drops] == [("traded", 3000.0, 3000.0, 0.0)]
    assert [e for e in events if e["event"] == "pull"] == []


def test_a_big_seller_taken_by_prints_and_posted_again_still_reads_taken():
    w = SymbolWatch("SOC", num_rows=10)
    _called(w)
    w.on_print(4.9, 0.75, 56100, lit=True)
    events = w.on_book(5.000, BIDS, NO_WALL) + w.on_book(5.340, BIDS, WALL) + w.on_book(9.0, BIDS, WALL)
    assert big_states(events)[0] == "eaten"
