"""A row IBKR is still moving shows once (#1133).

IBKR can move rows by rewriting each one with its neighbour, and ib_async hands Nova the row operations of
each TCP read as it arrives; a read that ends partway leaves one venue's row on two rows. SPCX 2026-10-21:
the 162.00 bid, one NSDQ row of 15,210, read 30,420 for one book, then 15,210 again -- and the book watcher
judged a 15,210-share pull that never happened.
"""
from __future__ import annotations

from types import SimpleNamespace

from book_watch.detector import SymbolWatch
from ibkr.depth import handlers, state
from ibkr.depth.book import BID_SIDE, DELETE, UPDATE, DepthBook, Level, one_row_per_venue


def tick(op, position, price=0.0, size=0.0, mm="NSDQ"):
    return SimpleNamespace(operation=op, position=position, price=price, size=size, side=BID_SIDE, marketMaker=mm)


TOP = (162.01, 117.0, "NSDQ")
WALL = (162.00, 15210.0, "NSDQ")
UNDER = (161.99, 500.0, "ARCA")
BUILD = [tick(UPDATE, i, *row) for i, row in enumerate((TOP, WALL, UNDER))]
# The 162.01 bid leaves: IBKR rewrites each row with the one below it and deletes the last --
# and the TCP read ends after the first rewrite.
FIRST_READ = [tick(UPDATE, 0, *WALL)]
SECOND_READ = [tick(UPDATE, 1, *UNDER), tick(DELETE, 2)]


def rows_of(levels):
    return [(lv.price, lv.size, lv.mm) for lv in levels]


def test_a_venue_twice_mid_move_shows_once_while_the_kept_rows_stay_ibkrs():
    book = DepthBook(10)
    book.apply(BUILD)
    book.apply(FIRST_READ)
    assert rows_of(book.bids) == [WALL, WALL, UNDER]  # as IBKR addresses them: its next rewrite lands on row 1
    assert rows_of(book.shown()[0]) == [WALL, UNDER]
    book.apply(SECOND_READ)
    assert rows_of(book.bids) == rows_of(book.shown()[0]) == [WALL, UNDER]


def _judged_at_the_wall(books):
    w = SymbolWatch("SPCX", num_rows=10)
    asks = [{"price": 162.05, "size": 300.0, "mm": "NSDQ"}]
    events = []
    for i, bids in enumerate(books):
        events += w.on_book(1.0 + i / 10, bids, asks)
    events += w.flush()
    return [(e["event"], e["pulled"]) for e in events if e["event"] in ("drop", "pull") and e["price"] == 162.00]


def test_the_watcher_fed_the_published_book_judges_no_pull(monkeypatch):
    for hook in ("_record_book", "_broadcast_live", "_watch_book"):
        monkeypatch.setattr(handlers, hook, lambda sym, book: None)
    state.reset_book("SPCX")
    published, kept = [], []
    try:
        for read in (BUILD, FIRST_READ, SECOND_READ):
            handlers.on_update_book(SimpleNamespace(domTicks=read), "SPCX")
            published.append(state.current_book("SPCX")["bids"])
            kept.append([{"price": lv.price, "size": lv.size, "mm": lv.mm} for lv in state.book_for("SPCX").bids])
    finally:
        state.clear_symbol("SPCX")
    assert [sum(r["size"] for r in bids if r["price"] == 162.00) for bids in published] == [15210, 15210, 15210]
    assert _judged_at_the_wall(published) == []
    # What the desk was handed before: the copy, then a large pull with no print anywhere.
    assert _judged_at_the_wall(kept) == [("drop", 15210.0), ("pull", 15210.0)]


def test_of_a_venues_two_rows_the_one_ibkr_wrote_last_is_shown():
    """NVDA 2026-10-21: NSDQ read 160 and 260 at 220.07 at once -- the size changed as the row moved."""
    # Moving up (a row above left): the rewritten row is the upper one.
    up = DepthBook(10)
    up.apply([tick(UPDATE, 0, 220.08, 100, "IEX"), tick(UPDATE, 1, 220.07, 260), tick(UPDATE, 2, 220.06, 100, "ARCA")])
    up.apply([tick(UPDATE, 0, 220.07, 160)])
    assert rows_of(up.shown()[0]) == [(220.07, 160, "NSDQ"), (220.06, 100, "ARCA")]
    # Moving down (a row arrives above), rewritten from the bottom up: the rewritten row is the lower one.
    down = DepthBook(10)
    down.apply([tick(UPDATE, 0, 220.07, 260), tick(UPDATE, 1, 220.06, 100, "ARCA")])
    down.apply([tick(UPDATE, 2, 220.06, 100, "ARCA"), tick(UPDATE, 1, 220.07, 160)])
    assert rows_of(down.bids) == [(220.07, 260, "NSDQ"), (220.07, 160, "NSDQ"), (220.06, 100, "ARCA")]
    assert rows_of(down.shown()[0]) == [(220.07, 160, "NSDQ"), (220.06, 100, "ARCA")]
    down.apply([])  # an L1 tick on the shared ticker: no row operations, the same pick
    assert rows_of(down.shown()[0]) == [(220.07, 160, "NSDQ"), (220.06, 100, "ARCA")]
    down.apply([tick(UPDATE, 0, 220.08, 100, "IEX")])
    assert rows_of(down.shown()[0]) == [(220.08, 100, "IEX"), (220.07, 160, "NSDQ"), (220.06, 100, "ARCA")]
    # One read can hold a size update and the start of a move: the row written later in it still wins.
    same_read = DepthBook(10)
    same_read.apply([tick(UPDATE, 0, 220.07, 260), tick(UPDATE, 1, 220.06, 100, "ARCA")])
    same_read.apply([tick(UPDATE, 0, 220.07, 200), tick(UPDATE, 2, 220.06, 100, "ARCA"), tick(UPDATE, 1, 220.07, 160)])
    assert rows_of(same_read.shown()[0]) == [(220.07, 160, "NSDQ"), (220.06, 100, "ARCA")]


def test_two_venues_with_one_size_at_a_price_both_show_and_unnamed_rows_are_kept():
    """LITU 2026-10-21: DRCTEDGE, EDGEA and MEMX each bid 500 at 15.50 -- three orders."""
    rows = [Level(15.50, 500, "DRCTEDGE"), Level(15.50, 500, "EDGEA"), Level(15.50, 500, "MEMX")]
    assert one_row_per_venue(rows) == rows
    unnamed = [Level(1.0, 100, ""), Level(1.0, 100, "")]
    assert one_row_per_venue(unnamed) == unnamed
    # When a row was written is bookkeeping, never part of its value.
    assert Level(1.0, 100, "IEX", 3) == Level(1.0, 100, "IEX", 7)
