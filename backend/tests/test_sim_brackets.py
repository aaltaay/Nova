"""A bracket on the loaded replay (#606 step 1): it fills on the replayed prints and unwinds with the playhead.

The Sim venue trades the loaded replay on a scratch account that forgets
whatever happened after a playhead the operator scrubs back to (ADR 020
decision 3). A bracket's exits wake at their entry's fill, so a scrub back
before that fill puts them back to waiting, and forward again replays it.
"""
from __future__ import annotations

from constants_practice import PRACTICE_OCO_CANCELLED_CODE
from sim import broker, feed
from sim import session_clock as clock
from tests.test_sim_practice import TAPE, historical, isolated  # noqa: F401 -- autouse fixture

# TAPE prints IMCC 10.0 at 10 s, 11.0 at 30 s, 10.4 at 45 s, 12.0 at 60 s (and an unreported 9.9 at 70 s).


def _statuses() -> dict[int, str]:
    return {int(r["order_id"]): r["status"] for r in broker.open_orders()}


def _closed() -> dict[int, dict]:
    return {int(r["order_id"]): r for r in broker.closed_orders()}


def _bracket_at_30s() -> int:
    """Entry 10.50 under the 11.00 last (it rests), target 11.50, stop 10.00; returns the entry's id."""
    historical(TAPE)
    clock.scrub_to_second(30)
    raw = broker.place_bracket("IMCC", "BUY", 5, 10.5, 11.5, 10.0)
    assert (raw["ok"], raw["broker_status"], raw["mode"]) == (True, "Submitted", "sim")
    feed.match_practice_fills()
    return int(raw["parent_order_id"])


def test_a_bracket_fills_on_the_replayed_prints() -> None:
    p = _bracket_at_30s()
    assert _statuses() == {p: "Submitted", p + 1: "PreSubmitted", p + 2: "PreSubmitted"}

    clock.scrub_to_second(60)
    filled = feed.match_practice_fills()

    # 10.4 at 45 s fills the entry at its limit; 12.0 at 60 s fills the target, which cancels the stop.
    assert [(r["order_id"], r["avg_fill_price"], r["fill_basis"]) for r in filled] == [
        (p, 10.5, "print_cross"), (p + 1, 11.5, "print_cross"),
    ]
    stop = _closed()[p + 2]
    assert (stop["status"], stop["reason_code"]) == ("Cancelled", PRACTICE_OCO_CANCELLED_CODE)
    assert broker.positions() == [] and broker.open_orders() == []


def test_the_stop_protects_a_bracket_filled_on_arrival() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    raw = broker.place_bracket("IMCC", "BUY", 5, 11.0, 12.5, 10.5)  # marketable at the 11.00 last
    assert (raw["broker_status"], raw["avg_fill_price"]) == ("Filled", 11.0)
    feed.match_practice_fills()

    clock.scrub_to_second(60)
    filled = feed.match_practice_fills()

    assert [(r["order_id"], r["avg_fill_price"], r["fill_basis"]) for r in filled] == [
        (raw["stop_order_id"], 10.4, "stop_trigger"),
    ]
    assert _closed()[raw["target_order_id"]]["reason_code"] == PRACTICE_OCO_CANCELLED_CODE
    assert broker.positions() == []


def test_scrubbing_back_before_the_entrys_fill_puts_the_exits_back_to_waiting() -> None:
    p = _bracket_at_30s()
    clock.scrub_to_second(60)
    assert len(feed.match_practice_fills()) == 2

    clock.scrub_to_second(40)  # after the placement, before the 45 s fill

    assert _statuses() == {p: "Submitted", p + 1: "PreSubmitted", p + 2: "PreSubmitted"}
    assert broker.positions() == [] and broker.closed_orders() == []
    clock.scrub_to_second(60)
    filled = feed.match_practice_fills()
    assert [(r["order_id"], r["avg_fill_price"]) for r in filled] == [(p, 10.5), (p + 1, 11.5)]


def test_scrubbing_back_between_the_fills_restores_the_cancelled_exit() -> None:
    p = _bracket_at_30s()
    clock.scrub_to_second(60)
    feed.match_practice_fills()

    clock.scrub_to_second(50)  # after the entry filled at 45 s, before the target and its cancel at 60 s

    assert _statuses() == {p + 1: "Submitted", p + 2: "Submitted"}
    assert broker.positions()[0]["qty"] == 5
    assert [r["order_id"] for r in broker.closed_orders()] == [p]
