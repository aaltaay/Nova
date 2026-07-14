"""Unit tests for Time & Sales bid/ask/between classification."""
from __future__ import annotations

from ibkr.tape_side import (
    TAPE_SIDE_ASK,
    TAPE_SIDE_BETWEEN,
    TAPE_SIDE_BID,
    TAPE_SIDE_UNKNOWN,
    best_bid_ask,
    classify_print_side,
)


def test_best_bid_ask_from_depth_book():
    bid, ask = best_bid_ask(
        {
            "bids": [{"price": 0.8428, "size": 100}],
            "asks": [{"price": 0.8488, "size": 200}],
        }
    )
    assert bid == 0.8428
    assert ask == 0.8488


def test_best_bid_ask_empty_or_none():
    assert best_bid_ask(None) == (None, None)
    assert best_bid_ask({"bids": [], "asks": []}) == (None, None)


def test_classify_ask_at_or_above():
    assert classify_print_side(0.8488, 0.8428, 0.8488) == TAPE_SIDE_ASK
    assert classify_print_side(0.85, 0.8428, 0.8488) == TAPE_SIDE_ASK


def test_classify_bid_at_or_below():
    assert classify_print_side(0.8428, 0.8428, 0.8488) == TAPE_SIDE_BID
    assert classify_print_side(0.84, 0.8428, 0.8488) == TAPE_SIDE_BID


def test_classify_between_spread():
    # MVO example from live UI: print 0.843 with 0.8428 x 0.8488
    assert classify_print_side(0.843, 0.8428, 0.8488) == TAPE_SIDE_BETWEEN


def test_classify_unknown_missing_or_crossed():
    assert classify_print_side(0.85, None, 0.8488) == TAPE_SIDE_UNKNOWN
    assert classify_print_side(0.85, 0.8428, None) == TAPE_SIDE_UNKNOWN
    assert classify_print_side(0.85, 0.85, 0.84) == TAPE_SIDE_UNKNOWN
    assert classify_print_side(0.85, 0.0, 0.8488) == TAPE_SIDE_UNKNOWN
