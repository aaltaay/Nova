"""What the Level 2 marks may claim (operator audit 2026-11-13: "we do really want accurate results here").

- **Only exchanges the book shows.** Each exchange sells its book separately and the tape carries them all.
  That morning the ladders showed no NYSE Arca row, and Arca was about half the lit volume: 20 of 33 hidden
  calls were prints on exchanges the book could not show, and prints there were filling drops elsewhere.
- **A big seller that shrank is smaller, not gone.** AIRS 0.85: 5,000 of 24,001 left and the card read
  "pulled" with 19,001 still offered.
- **A blink is not a refill** (the size gone for one book and back, ``test_book_watch_back.py``).
"""
from __future__ import annotations

from book_watch.constants_book_watch import BOOK_WATCH_BIG_SMALLER_SHARE
from book_watch.detector import SymbolWatch


def lv(price, size, mm="NSDQ"):
    return {"price": price, "size": size, "mm": mm}


def bare(rows):
    """The rows as a Session Record keeps them: no venue."""
    return [{"price": r["price"], "size": r["size"]} for r in rows]


# -- which exchanges a line shows ---------------------------------------------

def test_a_line_knows_the_exchanges_its_rows_have_named():
    w = SymbolWatch("TEST", num_rows=10)
    assert w.venues == set() and w.seen("ARCA")           # nothing named yet: it cannot be told
    w.on_book(1.0, [lv(10.00, 500), lv(9.99, 400, "DRCTEDGE")], [lv(10.05, 300, "GSCO")])
    assert w.venues == {"NSDQ", "DRCTEDGE", "GSCO"}
    assert w.seen("NASDAQ") and w.seen("DRCTEDGE")        # the tape says NASDAQ, the book says NSDQ
    assert not w.seen("ARCA") and not w.seen("NYSE")
    assert w.seen(None) and w.seen("")                    # a print that names no exchange: not told
    w.on_book(2.0, [lv(10.00, 500, "ARCA")], [lv(10.05, 300)])
    assert w.seen("ARCA")                                 # a row named it: shown from here on
    assert w.feed(2.0)["venues"] == ["ARCA", "DRCTEDGE", "GSCO", "NSDQ"]


def test_rows_that_name_no_venue_count_every_lit_print_as_before():
    w = SymbolWatch("TEST", num_rows=10)
    w.on_book(1.0, bare([lv(10.00, 500)]), bare([lv(10.05, 300)]))
    assert w.venues == set() and w.seen("ARCA")


# -- filled vs pulled ------------------------------------------------------------

BIDS = [lv(10.00, 300), lv(9.99, 5000), lv(9.98, 300)]
BIDS_AFTER = [lv(10.00, 300), lv(9.98, 300)]
ASKS = [lv(10.05, 300)]


def _drop(exchange):
    w = SymbolWatch("TEST", num_rows=10)
    w.on_book(1.0, BIDS, ASKS)
    w.on_print(1.1, 9.99, 5000, lit=True, exchange=exchange)
    events = w.on_book(1.2, BIDS_AFTER, ASKS) + w.flush()
    return next(e for e in events if e["event"] == "drop")


def test_a_print_on_an_exchange_the_book_shows_fills_the_level():
    drop = _drop("NASDAQ")
    assert (drop["outcome"], drop["filled"], drop["pulled"]) == ("traded", 5000.0, 0.0)


def test_a_print_on_an_exchange_the_book_does_not_show_fills_nothing_here():
    drop = _drop("ARCA")
    assert (drop["outcome"], drop["filled"], drop["pulled"]) == ("pulled", 0.0, 5000.0)


# -- hidden ------------------------------------------------------------------------

def _absorb(w, exchange, *, seconds=12):
    events = []
    for i in range(seconds):
        t = 1.0 + i
        events += w.on_book(t, [lv(10.00, 500), lv(9.99, 400)], [lv(10.05, 300), lv(10.06, 800)])
        events += w.on_print(t + 0.5, 10.05, 250, lit=True, exchange=exchange)
    return [e for e in events if e["event"] == "hidden"]


def test_prints_on_an_exchange_the_book_shows_can_be_a_hidden_seller():
    first = _absorb(SymbolWatch("TEST", num_rows=10), "NASDAQ")[0]
    assert first["kind"] == "hidden_seller" and first["printed"] == 2750 and first["unseen"] == 0


def test_prints_on_an_exchange_the_book_does_not_show_are_never_a_hidden_seller():
    w = SymbolWatch("TEST", num_rows=10)
    assert _absorb(w, "ARCA") == []
    st = w.hidden.active["ask"]
    assert st is not None and st.printed == 0 and st.unseen == 3000   # it held the price; nothing weighed


def test_a_hidden_seller_says_what_else_traded_where_the_book_cannot_look():
    w = SymbolWatch("TEST", num_rows=10)
    _absorb(w, "NASDAQ")
    events = w.on_print(13.6, 10.05, 4000, lit=True, exchange="ARCA")
    events += w.on_print(14.7, 10.05, 250, lit=True, exchange="NASDAQ")
    last = [e for e in events if e["event"] == "hidden"][-1]
    assert last["printed"] == 3250 and last["unseen"] == 4000 and last["hidden"] == 3250 - 300


def test_size_gone_for_one_book_and_back_is_not_a_refill():
    w = SymbolWatch("TEST", num_rows=10)
    bids = [lv(10.00, 500)]
    w.on_book(1.0, bids, [lv(10.05, 300), lv(10.06, 800)])
    w.on_print(1.1, 10.05, 100, lit=True, exchange="NASDAQ")
    w.on_book(1.2, bids, [lv(10.04, 100), lv(10.06, 800)])       # a new price arrives; 10.05 is on no row
    w.on_book(1.27, bids, [lv(10.04, 100), lv(10.05, 300), lv(10.06, 800)])
    st = w.hidden.active["ask"]
    assert st is not None and st.price == 10.05 and st.refills == 0
    w.on_book(3.0, bids, [lv(10.04, 100), lv(10.05, 100), lv(10.06, 800)])
    w.on_book(5.0, bids, [lv(10.04, 100), lv(10.05, 300), lv(10.06, 800)])   # two seconds later: a refill
    assert st.refills == 1


# -- a big seller that shrank --------------------------------------------------------

B = [lv(4.46, 500), lv(4.45, 600), lv(4.44, 700), lv(4.43, 400)]


def asks(wall):
    return [lv(4.48, 500), lv(4.49, 400), lv(4.51, 800), lv(4.52, 600), lv(4.50, wall)]


def _called(w, wall=18_000):
    w.on_print(0.5, 4.47, 100, lit=True)
    for t in (1.0, 2.0, 3.0, 4.0):
        w.on_book(t, B, asks(wall))


def _ended(w, wall_after, *, print_at=None):
    if print_at is not None:
        w.on_print(4.9, 4.50, print_at, lit=True, exchange="NASDAQ")
    events = w.on_book(5.0, B, asks(wall_after)) + w.on_book(9.0, B, asks(wall_after))
    return [e for e in events if e["event"] == "big"]


def test_the_share_that_reads_smaller_is_the_operators_choice():
    assert BOOK_WATCH_BIG_SMALLER_SHARE == 0.5


def test_a_big_seller_with_most_of_it_still_there_is_smaller_not_pulled():
    w = SymbolWatch("TEST", num_rows=10)
    _called(w)
    (end,) = _ended(w, 9_500)        # under the 10,000 floor, over half of the 18,000
    assert end["state"] == "smaller" and end["how"] == "no_prints"
    assert end["left"] == {"before": 18_000, "after": 9_500, "filled": 0.0}


def test_a_smaller_big_seller_says_when_what_left_traded():
    w = SymbolWatch("TEST", num_rows=10)
    _called(w)
    (end,) = _ended(w, 9_500, print_at=8_500)
    assert end["state"] == "smaller" and end["how"] == "traded" and end["left"]["filled"] == 8_500


def test_a_big_seller_that_lost_most_of_its_size_still_reads_pulled():
    w = SymbolWatch("TEST", num_rows=10)
    _called(w)
    (end,) = _ended(w, 4_000)
    assert end["state"] == "pulled" and end["left"]["after"] == 4_000


def test_a_smaller_big_seller_is_never_counted_as_a_pull_when_one_comes_back():
    w = SymbolWatch("TEST", num_rows=10)
    _called(w)
    _ended(w, 9_500)
    called = []
    for t in (10.0, 11.0, 12.0, 13.0, 14.0):
        called += [e for e in w.on_book(t, B, asks(18_000)) if e["event"] == "big"]
    assert called and called[0]["state"] == "holding" and called[0]["back"] is None


def test_a_print_on_an_exchange_the_book_does_not_show_takes_no_big_seller():
    w = SymbolWatch("TEST", num_rows=10)
    _called(w)
    w.on_print(4.9, 4.50, 18_000, lit=True, exchange="ARCA")
    events = w.on_book(5.0, B, asks(0)[:-1]) + w.on_book(9.0, B, asks(0)[:-1])
    (end,) = [e for e in events if e["event"] == "big"]
    assert end["state"] == "pulled" and end["left"]["filled"] == 0.0
