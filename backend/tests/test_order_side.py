"""The Orders table's Side column (ADR 048 decision 6): what an order does to the position.

Practice rows stamp it when they are placed (``test_practice_short_rules.py``). A Live row Nova sent
reads its execution row -- ``short_entry``, a bracket's legs, the position the door saw as it sent
-- and a working order placed outside Nova reads the position now. Nothing is guessed: what Nova
cannot know reads null.
"""
from __future__ import annotations

from execution.order_side import fill_from_positions, from_position, from_record
from execution.sent_by import ledger_sent_by


def test_a_plain_order_reads_the_position_it_meets() -> None:
    assert from_position("BUY", 0.0) == ("long", "opens")
    assert from_position("BUY", 300.0) == ("long", "opens")
    assert from_position("BUY", -300.0) == ("short", "closes")
    assert from_position("SELL", 300.0) == ("long", "closes")
    assert from_position("SELL", 0.0) == (None, None)        # a SELL from flat is no plain order
    assert from_position("BUY", None) == (None, None)         # the position is not known


def test_a_row_nova_sent_reads_its_own_record() -> None:
    assert from_record({"short_entry": True}, "SELL", "bracket") == ("short", "opens")
    assert from_record({"short_entry": True}, "BUY", "bracket") == ("short", "closes")   # the short's exits
    assert from_record({}, "BUY", "bracket") == ("long", "opens")
    assert from_record({}, "SELL", "bracket") == ("long", "closes")                      # the long's exits
    assert from_record({"position_at_send": -416}, "BUY", "place") == ("short", "closes")
    assert from_record({"position_at_send": 200}, "SELL", "place") == ("long", "closes")
    assert from_record({"position_at_send": None}, "BUY", "place") == (None, None)


def test_the_sender_join_carries_the_side() -> None:
    led = {"source": "flatten", "operation": "place",
           "payload": {"origin": "day_cover", "position_at_send": -416, "side": "BUY"}}
    assert ledger_sent_by(led) == {"order_source": "flatten", "order_origin": "day_cover", "short_entry": False,
                                   "position_side": "short", "effect": "closes"}


def test_an_outside_order_reads_the_position_now_and_unknown_when_unreadable() -> None:
    rows = [
        {"order_id": 1, "symbol": "RDYN", "side": "BUY"},
        {"order_id": 2, "symbol": "RDYN", "side": "BUY", "position_side": "long", "effect": "opens"},
        {"order_id": 3, "symbol": "GAPX", "side": "SELL"},
    ]
    held = [{"symbol": "RDYN", "qty": -416}, {"symbol": "GAPX", "qty": 100}]
    out = {r["order_id"]: (r["position_side"], r["effect"]) for r in fill_from_positions(rows, held)}
    assert out == {1: ("short", "closes"), 2: ("long", "opens"), 3: ("long", "closes")}
    unknown = {r["order_id"]: r["position_side"] for r in fill_from_positions(rows, None)}
    assert unknown == {1: None, 2: "long", 3: None}
