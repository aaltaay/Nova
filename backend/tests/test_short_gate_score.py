"""A short setup's tape gate, scoring and flush, mirrored (ADR 049, #778 step 4): the long path is unchanged."""
from __future__ import annotations

import pytest

from setup_scanner.bars import Bar
from setup_scanner.scoring import ScoreTracker
from setup_scanner.tape_flow import FlushPolicy, flush_action
from setup_scanner.tape_gate import evaluate
from tests.setup_scanner_fixtures import et_ts

NOW = et_ts(10, 30)
TRIG = 5.47


def book(bids, asks):
    return {"bids": [{"price": p, "size": s} for p, s in bids], "asks": [{"price": p, "size": s} for p, s in asks]}


def prints(side, n=4, size=300, price=TRIG):
    return [{"ts": NOW - 3 + i * 0.5, "size": size, "side": side, "price": price} for i in range(n)]


QUIET = book([(5.47, 800), (5.46, 1200)], [(5.48, 900), (5.49, 1000)])


def gate(books, tape, **kw):
    return evaluate(trigger=TRIG, now=NOW, books=books, prints=tape, side="short", **kw)


# -- the tape gate --------------------------------------------------------------------------------
def test_a_short_goes_on_red_prints_at_the_bid():
    res = gate([(NOW - 5, QUIET), (NOW - 0.5, QUIET)], prints("bid"))
    assert res["verdict"] == "go", res["reasons"]
    assert res["reasons"][0] == "red on the tape (4 prints, 1.2k at the bid)"
    assert res["metrics"]["side"] == "short" and res["metrics"]["red_flow"] is True
    assert "green_flow" not in res["metrics"]


def test_the_long_gate_reads_the_same_tape_the_other_way():
    long_ = evaluate(trigger=TRIG, now=NOW, books=[(NOW - 5, QUIET), (NOW - 0.5, QUIET)], prints=prints("bid"))
    assert long_["verdict"] == "wait" and "side" not in long_["metrics"]
    assert long_["reasons"][0].startswith("burst of red on the tape")


def test_a_short_waits_on_green_and_on_no_red_yet():
    green = gate([(NOW - 5, QUIET), (NOW - 0.5, QUIET)], prints("ask"))
    assert green["verdict"] == "wait" and green["reasons"][0].startswith("burst of green on the tape")
    none = gate([(NOW - 5, QUIET), (NOW - 0.5, QUIET)], [])
    assert none["verdict"] == "wait" and none["reasons"] == ["no red on the tape yet"]


def test_a_buyer_at_the_level_holds_a_short_and_a_big_one_vetoes_it():
    wall = book([(5.47, 30_000), (5.46, 1200)], [(5.48, 900)])
    res = gate([(NOW - 5, wall), (NOW - 0.5, wall)], prints("bid"))
    assert res["verdict"] == "wait" and res["reasons"] == ["30k-share buyer at 5.47 is not thinning"]
    thinned = book([(5.47, 9_000), (5.46, 1200)], [(5.48, 900)])
    res = gate([(NOW - 5, wall), (NOW - 0.5, thinned)], prints("bid"))
    assert res["verdict"] == "go" and "buyer at 5.47 thinning out (30k to 9k)" in res["reasons"]
    big = book([(5.47, 120_000)], [(5.48, 900)])
    assert gate([(NOW - 5, big), (NOW - 0.5, big)], prints("bid"))["reasons"][0] == "120k-share buyer at 5.47"


def test_a_hidden_buyer_vetoes_a_short():
    res = gate([(NOW - 5, QUIET), (NOW - 0.5, QUIET)], prints("bid", n=6, size=400))   # 2.4k into an 800 bid
    assert res["verdict"] == "veto"
    assert res["reasons"][0] == "hidden buyer: 2.4k sold at the bid and the bid did not move"


def test_a_short_without_a_fresh_book_is_blind():
    res = gate([(NOW - 9, QUIET)], prints("bid"))
    assert res["verdict"] == "blind" and res["metrics"]["side"] == "short"


def test_a_short_entering_on_the_score_needs_a_score_at_or_under_minus_the_minimum():
    from setup_scanner.tape_gate import GateParams

    p = GateParams(entry_mode="score", entry_min_score=0.3)
    books = [(NOW - 5, QUIET), (NOW - 0.5, QUIET)]
    sold = gate(books, prints("bid"), p=p, flow={"score": -0.4, "label": "flush"})
    assert sold["verdict"] == "go" and sold["reasons"][0] == "flow -0.40 (flush)"
    bought = gate(books, prints("bid"), p=p, flow={"score": 0.4, "label": "burst"})
    assert bought["verdict"] == "wait" and bought["reasons"] == ["flow +0.40 is over -0.30"]


# -- scoring --------------------------------------------------------------------------------------
def tracker(**kw):
    t0 = et_ts(10, 22)
    base = dict(entry=5.46, stop=5.56, target1=5.26, risk=0.10, triggered_at=t0 + 10, entry_bar_t=t0, side="short")
    return ScoreTracker(**{**base, **kw}), t0


def bar(t, o, h, lo, c):
    return Bar(t, o, h, lo, c, 10_000)


def test_a_shorts_first_touch_is_its_target_under_or_its_stop_over():
    tr, t0 = tracker()
    assert tr.on_price(5.40, t0 + 20) is False and tr.mfe == pytest.approx(0.06)
    assert tr.on_price(5.26, t0 + 30) is True and tr.outcome == "target_first"
    tr, t0 = tracker()
    assert tr.on_price(5.50, t0 + 20) is False and tr.mae == pytest.approx(-0.04)
    assert tr.on_price(5.56, t0 + 30) is True and tr.outcome == "stop_first"


def test_a_short_covers_half_at_target_then_the_rest_on_a_close_over_the_9_ema():
    tr, t0 = tracker()
    assert tr.on_bar(bar(t0, 5.47, 5.48, 5.44, 5.45), 5.50) is False           # the entry bar
    assert tr.on_bar(bar(t0 + 60, 5.40, 5.41, 5.25, 5.30), 5.45) is False      # half at 5.26, stop to 5.46
    assert tr.half_done and tr.half_px == 5.26 and tr.bar_stop == 5.46
    assert tr.on_bar(bar(t0 + 120, 5.30, 5.36, 5.28, 5.35), 5.33) is True      # closed over the EMA
    assert tr.exit_reason == "ema" and tr.bar_r() == pytest.approx((0.5 * 0.20 + 0.5 * 0.11) / 0.10)


def test_a_short_is_stopped_over_its_stop_and_the_bailout_reads_closes_at_or_over_the_entry():
    tr, t0 = tracker()
    tr.on_bar(bar(t0, 5.47, 5.48, 5.44, 5.45), None)
    assert tr.on_bar(bar(t0 + 60, 5.50, 5.60, 5.49, 5.58), None) is True
    assert tr.exit_reason == "stop" and tr.exit_px == 5.56 and tr.bar_r() == pytest.approx(-1.0)
    tr, t0 = tracker(bailout_bars=2)
    tr.on_bar(bar(t0, 5.47, 5.48, 5.44, 5.45), None)
    assert tr.on_bar(bar(t0 + 60, 5.45, 5.47, 5.43, 5.44), None) is False
    assert tr.on_bar(bar(t0 + 120, 5.44, 5.48, 5.43, 5.46), None) is True and tr.exit_reason == "bailout"


def test_a_gap_over_the_buy_stop_covers_at_the_open():
    tr, t0 = tracker()
    tr.on_bar(bar(t0, 5.47, 5.48, 5.44, 5.45), None)
    assert tr.on_bar(bar(t0 + 60, 5.70, 5.75, 5.65, 5.72), None) is True
    assert tr.exit_px == 5.70 and tr.bar_r() == pytest.approx(-2.4)


# -- the flush exit -------------------------------------------------------------------------------
def test_a_burst_of_buying_is_a_shorts_flush():
    policy = FlushPolicy(mode="exit", hold_sec=0, trail_r=0.5, min_r=None)
    assert flush_action(policy, label="flush", price=5.40, ts=10, entry=5.46, risk=0.10, stop=5.56, since=0,
                        side="short") is None
    act = flush_action(policy, label="burst", price=5.40, ts=10, entry=5.46, risk=0.10, stop=5.56, since=0,
                       side="short")
    assert act == {"action": "exit", "r_now": 0.6}
    tighten = FlushPolicy(mode="tighten", hold_sec=0, trail_r=0.5, min_r=None)
    act = flush_action(tighten, label="burst", price=5.40, ts=10, entry=5.46, risk=0.10, stop=5.56, since=0,
                       side="short")
    assert act["action"] == "tighten" and act["stop"] == 5.45                     # down only
    assert flush_action(tighten, label="burst", price=5.55, ts=10, entry=5.46, risk=0.10, stop=5.56, since=0,
                        side="short") is None                                      # 5.60 would raise it


def test_a_shorts_flush_exit_covers_at_the_ask():
    tr, t0 = tracker(flush=FlushPolicy(mode="exit", hold_sec=0, trail_r=0.5, min_r=None))
    assert tr.on_flow(label="burst", price=5.40, bid=5.39, ask=5.41, ts=t0 + 30) == "exit"
    assert tr.exit_px == 5.41 and tr.exit_reason == "flush" and tr.bar_r() == pytest.approx(0.5)
