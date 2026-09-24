"""Nova's own Level 2 book, kept with IBKR's row rules (#540)."""
from __future__ import annotations

from types import SimpleNamespace

from constants import IBKR_ERROR_DEPTH_RESET
from ibkr.depth import handlers, state
from ibkr.depth.book import BID_SIDE, DELETE, INSERT, UPDATE, DepthBook, sort_levels


def tick(op: int, position: int, price: float, size: float = 100, side: int = BID_SIDE, mm: str = "ARCA"):
    return SimpleNamespace(operation=op, position=position, price=price, size=size, side=side, marketMaker=mm)


# IBKR builds a bid side, a better bid arrives at the top, one level leaves, another arrives.
SEQUENCE = [
    tick(INSERT, 0, 10.00), tick(INSERT, 1, 9.99), tick(INSERT, 2, 9.98),
    tick(INSERT, 0, 10.01),   # rows below move down
    tick(DELETE, 1, 10.00),   # 10.00 leaves; rows below move up
    tick(INSERT, 1, 10.005),  # a new second-best bid
]


def ib_async_side(ticks) -> list[float]:
    """What ib_async 2.1.0 shows for the same operations: a dict keyed by row."""
    dom: dict[int, float] = {}
    for t in ticks:
        if t.operation in (INSERT, UPDATE):
            dom[t.position] = t.price
        else:
            dom.pop(t.position, None)
    return list(dom.values())


def test_the_kept_book_follows_ibkrs_row_rules_where_ib_async_does_not():
    book = DepthBook(10)
    book.apply(SEQUENCE)
    assert [lv.price for lv in book.bids] == [10.01, 10.005, 9.99, 9.98]
    assert book.in_price_order()
    # The dict-keyed book lost 9.99 behind an overwrite and put 10.005 last.
    assert ib_async_side(SEQUENCE) == [10.01, 9.98, 10.005]


def test_an_insert_past_the_books_depth_drops_the_bottom_row():
    book = DepthBook(3)
    book.apply([tick(INSERT, i, 10.0 - i / 100) for i in range(3)])
    book.apply([tick(INSERT, 0, 10.01)])
    assert [lv.price for lv in book.bids] == [10.01, 10.0, 9.99]


def test_updates_and_deletes_out_of_range_never_invent_or_crash():
    book = DepthBook(10)
    book.apply([tick(DELETE, 4, 0.0), tick(UPDATE, 0, 5.0), tick(UPDATE, 0, 5.1)])
    assert [lv.price for lv in book.bids] == [5.1]
    assert book.asks == []


def test_the_handler_pushes_the_kept_book_and_a_depth_reset_starts_it_over(monkeypatch):
    monkeypatch.setattr(handlers, "_record_book", lambda sym, book: None)
    monkeypatch.setattr(handlers, "_broadcast_live", lambda sym, book: None)
    state.reset_book("GRML")
    try:
        handlers.on_update_book(SimpleNamespace(domTicks=SEQUENCE), "GRML")
        bids = state.current_book("GRML")["bids"]
        assert [row["price"] for row in bids] == [10.01, 10.005, 9.99, 9.98]
        # Events with no depth rows (an L1 tick on the shared ticker) leave the book alone.
        handlers.on_update_book(SimpleNamespace(domTicks=[]), "GRML")
        assert [row["price"] for row in state.current_book("GRML")["bids"]] == [10.01, 10.005, 9.99, 9.98]
        contract = SimpleNamespace(conId=4242)
        state._contracts["GRML"] = contract
        handlers.on_ib_error(7, IBKR_ERROR_DEPTH_RESET, "Market depth data has been RESET", contract)
        assert state.book_for("GRML").bids == []
    finally:
        state._contracts.pop("GRML", None)
        state.clear_symbol("GRML")


def test_a_recorded_out_of_order_book_reads_best_price_first():
    """GRML 2026-09-22: the ask shown first (17.00) was not the best ask (16.80)."""
    asks = [{"price": p, "size": 100} for p in (17.00, 16.80, 16.90, 17.00, 18.78)]
    assert [r["price"] for r in sort_levels(asks, bid=False)] == [16.80, 16.90, 17.00, 17.00, 18.78]
    bids = [{"price": p, "size": 100} for p in (10.45, 10.47, 10.45, 10.43)]
    assert [r["price"] for r in sort_levels(bids, bid=True)] == [10.47, 10.45, 10.45, 10.43]
