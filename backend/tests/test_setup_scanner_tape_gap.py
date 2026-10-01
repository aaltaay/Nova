"""The tape hold (#673): a live tape read never reads across an IBKR feed gap's catch-up burst."""
from __future__ import annotations

from setup_scanner import tape_gap, tape_flow
from setup_scanner.tape_gate import evaluate

NOW = 1_790_861_560.0      # 2026-10-01 09:32:40 ET
TRIG = 8.00
GAP = {"start": NOW - 34.0, "end": NOW - 18.0}   # 09:32:06 -> 09:32:22, the 16 s silence


def book(ts_ago: float = 0.5):
    return (NOW - ts_ago, {"bids": [{"price": 7.99, "size": 4_000}], "asks": [{"price": 8.00, "size": 2_000}]})


def burst():
    """What arrived in one second after the gap: green prints, the shape the gate calls go."""
    return [{"ts": NOW - 2 + i * 0.05, "size": 100, "side": "ask", "price": 8.00, "exchange": "NSDQ"}
            for i in range(20)]


def test_touching_spans_the_silence_and_the_settle_after_it():
    assert tape_gap.touching([GAP], NOW - 10, NOW, settle=5.0) is None          # settled at NOW - 13
    assert tape_gap.touching([GAP], NOW - 15, NOW, settle=5.0) == GAP
    assert tape_gap.touching([GAP], NOW - 60, NOW - 40, settle=5.0) is None     # before it
    live = {"start": NOW - 9, "end": None}
    assert tape_gap.touching([GAP, live], NOW - 5, NOW) == live                 # the newest wins


def test_the_gate_reads_blind_with_the_gap_as_its_reason():
    prs, books = burst(), [book(9), book(0.5)]
    assert evaluate(trigger=TRIG, now=NOW, books=books, prints=prs)["verdict"] == "go"
    held = evaluate(trigger=TRIG, now=NOW - 12, books=books, prints=prs, gaps=[GAP])
    assert held["verdict"] == "blind"
    assert held["reasons"] == ["IBKR data stopped for 16 s at 09:32:06 ET; what IBKR held arrived in one burst at "
                               "09:32:22, so Nova does not read the tape across it"]
    assert held["metrics"]["feed_gap"] == {"start": GAP["start"], "end": GAP["end"], "silent_sec": 16.0}
    assert held["metrics"]["read_at"] == NOW - 12


def test_an_open_gap_says_the_data_stopped_not_open_level_2():
    held = evaluate(trigger=TRIG, now=NOW, books=[], prints=[], gaps=[{"start": NOW - 9, "end": None}])
    assert held["verdict"] == "blind"
    assert held["reasons"][0].startswith("IBKR data has stopped on every line for 9 s")


def test_no_gaps_reads_as_before():
    prs, books = burst(), [book(9), book(0.5)]
    assert (evaluate(trigger=TRIG, now=NOW, books=books, prints=prs, gaps=[])
            == evaluate(trigger=TRIG, now=NOW, books=books, prints=prs))


def test_the_flow_holds_a_burst_and_restarts_its_baseline_after_the_gap():
    p = tape_flow.DEFAULT_FLOW
    reading = tape_flow.evaluate(now=NOW - 14, books=[book(14.2)], prints=burst(), p=p)
    held = tape_gap.hold_flow(reading, [GAP], NOW - 14, p.window_sec)
    assert held["label"] == "blind" and held["score"] is None
    assert set(held["readings"].values()) == {None}
    assert held["gap"]["silent_sec"] == 16.0 and "one burst" in held["gap"]["text"]
    assert tape_gap.hold_flow(reading, [], NOW - 14, p.window_sec) is reading
    assert tape_gap.history_from([GAP], NOW - 300, NOW) == GAP["end"] + 5.0
    assert tape_gap.history_from([GAP], None, NOW - 20) is None                 # not settled yet: nothing to move
    assert tape_gap.history_from([], NOW - 300, NOW) == NOW - 300
