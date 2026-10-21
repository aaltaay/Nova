"""A copy of a row IBKR was moving, in a recorded book (#1133).

Session Records keep no venue, so a copy is told by its size and its life: the price and odd size of a row
above it that the book before held fewer of. On 2026-10-21, 431 of 437 such new pairs lasted one book; two
venues often show the same round lot, so round lots are left alone.
"""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from book_watch import big_replay, ladder_replay, live
from book_watch.book import RecordedCopies, drop_moving_copies
from book_watch.replay import replay


def row(price, size, mm=None):
    out = {"price": price, "size": size}
    if mm:
        out["mm"] = mm
    return out


WALL = row(162.00, 15210)


def test_an_odd_size_copy_the_book_before_did_not_hold_goes():
    before = [row(162.01, 117), WALL, row(161.99, 500)]
    assert drop_moving_copies([WALL, WALL, row(161.99, 500)], before) == [WALL, row(161.99, 500)]


def test_a_copy_further_down_its_price_goes_too():
    """AMOD 2026-10-21 1.78 bid: 100, 412, 300 read 412, 100, 412, 300 for one book."""
    before = [row(1.78, 100), row(1.78, 412), row(1.78, 300)]
    rows = [row(1.78, 412), row(1.78, 100), row(1.78, 412), row(1.78, 300)]
    assert drop_moving_copies(rows, before) == [row(1.78, 412), row(1.78, 100), row(1.78, 300)]


def test_round_lots_pairs_already_there_and_a_first_book_stay():
    pair = [row(15.50, 500), row(15.50, 500)]
    assert drop_moving_copies(pair, [row(15.50, 500)]) == pair  # two venues' round lots
    odd_pair = [WALL, WALL]
    assert drop_moving_copies(odd_pair, odd_pair) == odd_pair  # already two before
    assert drop_moving_copies(odd_pair, None) == odd_pair  # nothing to tell it by


def test_rows_that_name_their_venue_keep_each_venue_once():
    named = [row(162.00, 15210, "NSDQ"), row(162.00, 15210, "NSDQ"), row(162.00, 15210, "ARCA")]
    assert drop_moving_copies(named, None) == [row(162.00, 15210, "NSDQ"), row(162.00, 15210, "ARCA")]


def test_a_side_recorded_unchanged_keeps_its_copy_out_and_a_real_pair_comes_back():
    """CRDU 2026-10-21: 576 at 7.57 twice for two books -- the asks moved, the bids did not."""
    one, two = [row(7.57, 576)], [row(7.57, 576), row(7.57, 576)]
    copies = RecordedCopies()
    books = [(one, [row(7.60, 300)]), (two, [row(7.60, 300)]), (two, [row(7.61, 300)]), (one, [row(7.61, 300)])]
    assert [copies.read({"bids": b, "asks": a})["bids"] for b, a in books] == [one, one, one, one]
    # A second venue at the same odd size that is still there after its side changes shows from then.
    copies = RecordedCopies()
    pair_and_more = [*two, row(7.56, 100)]
    assert [copies.read({"bids": b, "asks": []})["bids"] for b in (one, two, pair_and_more)] == [one, one, pair_and_more]


def test_the_books_read_are_never_changed():
    first, second = {"ts": 1.0, "bids": [WALL]}, {"ts": 1.1, "bids": [WALL, WALL], "asks": []}
    kept = copy.deepcopy(second)
    copies = RecordedCopies()
    copies.read(first)
    assert copies.read(second)["bids"] == [WALL] and second == kept


# -- the replay tool and the Sim desk read the same books --------------------------

ASKS = [row(162.05, 300)]
COPY_BOOKS = [
    {"ts": 1.0, "bids": [row(162.01, 117), WALL, row(161.99, 500), row(161.98, 300)], "asks": ASKS},
    {"ts": 1.1, "bids": [WALL, WALL, row(161.99, 500), row(161.98, 300)], "asks": ASKS},  # mid-move
    {"ts": 1.2, "bids": [WALL, row(161.99, 500), row(161.98, 300)], "asks": ASKS},
]
PRINTS = [{"ts": 1.05, "receive_ts": 1.05, "price": 162.05, "size": 100, "exchange": "NASDAQ"}]


def _record(tmp_path, name, books, prints=PRINTS):
    rec = tmp_path / name
    rec.mkdir()
    (rec / "l2.jsonl").write_text("\n".join(json.dumps(b) for b in books) + "\n")
    (rec / "prints.jsonl").write_text("\n".join(json.dumps(p) for p in prints) + "\n")
    return rec


def test_the_replay_judges_no_pull_where_a_row_was_copied(tmp_path):
    result = replay(_record(tmp_path, "SPCX", COPY_BOOKS))
    assert result["large_pulls"] == [] and result["drops"] == []
    assert result["pulled_shares"] == 117  # only the 162.01 bid that left


def test_a_round_lot_pulled_from_a_pair_still_reads_pulled(tmp_path):
    """Two venues bid 5,000 at 9.99; one leaves with no print: a real pull, exactly half the level."""
    edge = [row(10.00, 300), row(9.98, 300)]
    books = [{"ts": 1.0, "bids": [edge[0], row(9.99, 5000), edge[1]], "asks": [row(10.05, 300)]},
             {"ts": 1.1, "bids": [edge[0], row(9.99, 5000), row(9.99, 5000), edge[1]], "asks": [row(10.05, 300)]},
             {"ts": 1.5, "bids": [edge[0], row(9.99, 5000), edge[1]], "asks": [row(10.05, 300)]}]
    prints = [{"ts": 1.3, "receive_ts": 1.3, "price": 10.05, "size": 100, "exchange": "NASDAQ"}]
    result = replay(_record(tmp_path, "PAIR", books, prints))
    assert [(p["price"], p["pulled"], p["level_before"], p["level_after"]) for p in result["large_pulls"]] == [
        (9.99, 5000.0, 10000.0, 5000.0)]


@pytest.fixture
def worker_on(monkeypatch):
    monkeypatch.setenv("NOVA_BOOK_WATCH", "1")
    monkeypatch.setenv("NOVA_BOOK_WATCH_JOURNAL", "0")
    monkeypatch.setattr(live, "_ensure_thread", lambda: None)
    live.reset_for_tests()
    ladder_replay.reset_for_tests()
    big_replay.reset_for_tests()
    yield
    live.reset_for_tests()
    ladder_replay.reset_for_tests()
    big_replay.reset_for_tests()


def _capture(books, prints):
    return SimpleNamespace(key="2026-10-21|SPCX", symbol="SPCX", l2=list(books), l2_keys=[b["ts"] for b in books],
                           prints=list(prints), print_keys=[p["ts"] for p in prints], spans=[])


def test_the_sim_ladder_judges_no_pull_where_a_row_was_copied(worker_on, monkeypatch):
    from sim import capture_player

    monkeypatch.setattr(capture_player, "snapshot", lambda: _capture(COPY_BOOKS, PRINTS))
    view = ladder_replay.ladder_view("SPCX", None, 3.0, num_rows=10)
    assert view["watching"] is True and view["drops"] == []


def test_the_sim_big_buyer_reading_never_counts_the_copy():
    """A 12,345-share bid wall held five seconds, copied for one book: its peak is the one order."""
    small = [row(4.46, 500), row(4.45, 600), row(4.44, 700), row(4.43, 400)]
    wall = row(4.47, 12345)
    asks = [row(4.48, 500), row(4.49, 400), row(4.50, 300), row(4.51, 800)]
    books = [{"ts": 1000.0 + i, "bids": [wall, wall, *small] if i == 3 else [wall, *small], "asks": asks}
             for i in range(6)]
    prints = [{"ts": 999.5, "price": 4.48, "size": 100, "exchange": "NASDAQ", "conditions": ""}]
    big_replay.reset_for_tests()
    try:
        reading = big_replay.reading(_capture(books, prints), 1005.5, num_rows=10)
    finally:
        big_replay.reset_for_tests()
    assert [(b["price"], b["size_peak"]) for b in reading["buyers"]] == [(4.47, 12345.0)]
