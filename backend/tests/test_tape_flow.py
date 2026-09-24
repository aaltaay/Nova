"""The tape flow score (ADR 034): one number for who is winning the tape, the entry
modes that read it, the flush exit it drives, and the two ways it is summed."""
from __future__ import annotations

import random

import pytest

from setup_scanner.scoring import ScoreTracker
from setup_scanner.bars import Bar
from setup_scanner.tape_flow import (
    DEFAULT_FLOW,
    FlowIndex,
    FlowParams,
    FlushPolicy,
    depth,
    evaluate,
    flush_action,
)
from setup_scanner.tape_gate import GateParams, evaluate as gate

NOW = 1_790_000_000.0
THIN_BIDS = {"bids": [{"price": 4.85, "size": 200}, {"price": 4.84, "size": 100}],
             "asks": [{"price": 4.86, "size": 4000}, {"price": 4.87, "size": 3000}]}
THICK_BIDS = {"bids": [{"price": 4.86, "size": 5000}], "asks": [{"price": 4.87, "size": 300}]}


def pr(ts, price, size, side, exchange="NSDQ", conditions=""):
    return {"ts": ts, "price": price, "size": size, "side": side, "exchange": exchange, "conditions": conditions}


def baseline(start=NOW - 120, end=NOW - 10, every=5.0):
    """A calm two minutes: a 100-share print every five seconds, sides alternating."""
    out, t, i = [], start, 0
    while t < end:
        out.append(pr(t, 4.90, 100, "ask" if i % 2 else "bid"))
        t, i = t + every, i + 1
    return out


def flush_window():
    """The GLND picture: fast prints at the bid, price stepping down, nothing at the ask."""
    return [pr(NOW - 9 + i * 0.5, round(4.90 - 0.005 * i, 3), 300, "bid") for i in range(18)]


def burst_window():
    return [pr(NOW - 9 + i * 0.5, round(4.86 + 0.005 * i, 3), 300, "ask") for i in range(18)]


# -- the score ---------------------------------------------------------------------------
def test_a_flush_reads_flush_and_a_burst_reads_burst():
    f = evaluate(now=NOW, books=[(NOW - 0.2, THIN_BIDS)], prints=baseline() + flush_window())
    assert f["label"] == "flush" and f["score"] <= -0.9
    assert f["readings"]["imbalance"] == -1.0 and f["readings"]["pace"] == -1.0
    assert f["readings"]["drift"] < 0 and f["readings"]["book"] < 0
    assert f["metrics"]["bid_shares"] == 5400 and f["metrics"]["best_bid"] == 4.85
    b = evaluate(now=NOW, books=[(NOW - 0.2, THICK_BIDS)], prints=baseline() + burst_window())
    assert b["label"] == "burst" and b["score"] >= 0.9


def test_too_little_tape_is_quiet_and_no_tape_no_book_is_blind():
    few = [pr(NOW - 2, 4.9, 100, "bid"), pr(NOW - 1, 4.89, 100, "bid")]
    q = evaluate(now=NOW, books=[(NOW - 0.2, THIN_BIDS)], prints=few)
    assert q["label"] == "quiet" and q["score"] is not None      # scored, but too little to call
    assert evaluate(now=NOW, books=[], prints=[])["label"] == "blind"
    # A book but no prints is a quiet line, never blind.
    assert evaluate(now=NOW, books=[(NOW - 0.2, THIN_BIDS)], prints=[])["label"] == "quiet"


def test_a_reading_nova_cannot_take_drops_out_of_the_mean_never_zero():
    f = evaluate(now=NOW, books=[], prints=baseline() + flush_window())     # no book
    assert f["readings"]["book"] is None and f["label"] == "flush"
    stale = evaluate(now=NOW, books=[(NOW - 30, THICK_BIDS)], prints=baseline() + flush_window())
    assert stale["readings"]["book"] is None and stale["score"] == f["score"]
    # With only the book weighted, no book is no score at all: quiet, not neutral.
    only_book = FlowParams(w_imbalance=0, w_pace=0, w_drift=0, w_book=1)
    assert evaluate(now=NOW, books=[], prints=baseline() + flush_window(), p=only_book)["score"] is None


def test_pace_is_speed_against_the_tapes_own_baseline_and_unknown_without_one():
    busy_baseline = [pr(NOW - 120 + i * 0.5, 4.90, 300, "ask" if i % 2 else "bid") for i in range(220)]
    f = evaluate(now=NOW, books=[], prints=busy_baseline + flush_window())
    # 540 shares a second in the window against 600 before it: no faster than usual, no pace.
    assert f["readings"]["pace"] == 0.0 and f["metrics"]["pace_ratio"] == pytest.approx(0.9)
    # The feed started listening 5 s ago: no baseline to judge speed by -- unknown, not quiet.
    late = evaluate(now=NOW, books=[], prints=baseline() + flush_window(), history_from=NOW - 5)
    assert late["readings"]["pace"] is None and late["metrics"]["baseline_sec"] == 0


def test_trade_reports_and_between_prints_count_for_no_side():
    rows = baseline() + [pr(NOW - 5 + i * 0.1, 4.9, 5000, "bid", exchange="FINRA") for i in range(10)]
    rows += [pr(NOW - 4 + i * 0.1, 4.9, 1000, "between") for i in range(10)]
    f = evaluate(now=NOW, books=[], prints=rows)
    assert f["metrics"]["bid_shares"] == 0 and f["metrics"]["between_shares"] == 10_000
    assert f["label"] == "quiet"


def test_an_odd_lot_never_sets_the_drift():
    rows = baseline() + [pr(NOW - 8, 4.90, 300, "bid"), pr(NOW - 1, 1.00, 5, "bid", conditions="I"),
                         pr(NOW - 0.5, 4.89, 300, "bid")]
    f = evaluate(now=NOW, books=[], prints=rows)
    assert f["metrics"]["drift_pct"] == pytest.approx(-0.204, abs=1e-3)


def test_depth_sums_venue_rows_at_one_price_and_reads_a_missing_side_as_unknown():
    book = {"bids": [{"price": 4.86, "size": 100}, {"price": 4.86, "size": 200}, {"price": 4.85, "size": 50}],
            "asks": []}
    assert depth(book, 1) == (300.0, None, 4.86, None)
    assert depth(book, 5)[0] == 350.0


def test_the_index_sums_exactly_what_the_list_sums():
    rng = random.Random(7)
    prints, t = [], NOW - 400
    while t < NOW + 200:
        t += rng.expovariate(4.0)
        prints.append(pr(t, round(4.5 + rng.random(), 2), rng.choice([1, 50, 100, 300, 2000]),
                         rng.choice(["ask", "bid", "between", "unknown", None]),
                         exchange=rng.choice(["NSDQ", "ARCA", "FINRA", "IEX"]),
                         conditions=rng.choice(["", "", "I", "T"])))
    books = [(NOW - 400 + i * 0.5, {"bids": [{"price": 4.8, "size": rng.randint(1, 900)}],
                                    "asks": [{"price": 4.81, "size": rng.randint(1, 900)}]}) for i in range(1200)]
    idx = FlowIndex(prints, books)
    for p in (DEFAULT_FLOW, FlowParams(window_sec=5, baseline_sec=30, book_levels=1)):
        for now in (NOW - 350, NOW - 100.25, NOW, NOW + 123.4):
            for since in (None, NOW - 150, now - 3):
                a = evaluate(now=now, books=books, prints=prints, p=p, history_from=since)
                b = idx.evaluate(now, p, history_from=since)
                assert a == b, (p, now, since)


# -- the entry modes ------------------------------------------------------------------------
BOOK = {"bids": [{"price": 4.36, "size": 4000}], "asks": [{"price": 4.37, "size": 3000}]}


def _red(now):
    return [pr(now - 3 + i * 0.5, 4.37, 300, "bid") for i in range(4)] + [pr(now - 1, 4.37, 100, "ask")]


def test_the_gate_mode_is_the_pre_registered_rule_and_the_flow_rides_along():
    flow = {"score": 0.8, "label": "burst"}
    res = gate(trigger=4.37, now=NOW, books=[(NOW - 0.5, BOOK)], prints=_red(NOW), flow=flow)
    assert res["verdict"] == "wait" and res["reasons"][0].startswith("burst of red")
    assert res["flow"] == flow and res["metrics"]["entry_mode"] == "gate"


def test_score_mode_trades_the_print_counts_for_the_score():
    p = GateParams(entry_mode="score", entry_min_score=0.3)
    ok = gate(trigger=4.37, now=NOW, books=[(NOW - 0.5, BOOK)], prints=_red(NOW), p=p,
              flow={"score": 0.45, "label": "neutral"})
    assert ok["verdict"] == "go" and ok["reasons"][0] == "flow +0.45 (neutral)"
    low = gate(trigger=4.37, now=NOW, books=[(NOW - 0.5, BOOK)], prints=_red(NOW), p=p,
               flow={"score": 0.1, "label": "neutral"})
    assert low["verdict"] == "wait" and low["reasons"] == ["flow +0.10 is under +0.30"]
    quiet = gate(trigger=4.37, now=NOW, books=[(NOW - 0.5, BOOK)], prints=[], p=p,
                 flow={"score": 0.9, "label": "quiet"})
    assert quiet["verdict"] == "wait" and "quiet" in quiet["reasons"][0]


def test_both_mode_needs_the_green_prints_and_the_score():
    p = GateParams(entry_mode="both", entry_min_score=0.3)
    green = [pr(NOW - 3 + i * 0.5, 4.37, 300, "ask") for i in range(4)]
    res = gate(trigger=4.37, now=NOW, books=[(NOW - 0.5, BOOK)], prints=green, p=p,
               flow={"score": 0.6, "label": "burst"})
    assert res["verdict"] == "go" and res["reasons"][0].startswith("green on the tape") and "flow +0.60" in res["reasons"][1]
    res = gate(trigger=4.37, now=NOW, books=[(NOW - 0.5, BOOK)], prints=green, p=p,
               flow={"score": 0.1, "label": "neutral"})
    assert res["verdict"] == "wait"


def test_a_veto_holds_in_every_mode():
    wide = {"bids": [{"price": 4.20, "size": 4000}], "asks": [{"price": 4.37, "size": 3000}]}
    for mode in ("gate", "score", "both"):
        res = gate(trigger=4.37, now=NOW, books=[(NOW - 0.5, wide)], prints=[], p=GateParams(entry_mode=mode),
                   flow={"score": 1.0, "label": "burst"})
        assert res["verdict"] == "veto", mode


# -- the flush rule --------------------------------------------------------------------------
def test_flush_action_is_off_by_default_and_waits_out_the_entry_noise():
    kw = {"label": "flush", "price": 4.40, "entry": 4.38, "risk": 0.08, "stop": 4.30, "since": NOW}
    assert flush_action(FlushPolicy(), ts=NOW + 60, **kw) is None
    exit_ = FlushPolicy(mode="exit", hold_sec=10)
    assert flush_action(exit_, ts=NOW + 5, **kw) is None
    assert flush_action(exit_, ts=NOW + 11, **kw) == {"action": "exit", "r_now": 0.25}
    assert flush_action(exit_, ts=NOW + 11, **{**kw, "label": "neutral"}) is None
    assert flush_action(FlushPolicy(mode="exit", hold_sec=0, min_r=0.5), ts=NOW + 11, **kw) is None


def test_tighten_moves_the_stop_up_and_never_down():
    t = FlushPolicy(mode="tighten", hold_sec=0, trail_r=0.5)
    kw = {"label": "flush", "entry": 4.38, "risk": 0.08, "since": NOW, "ts": NOW + 30}
    assert flush_action(t, price=4.45, stop=4.30, **kw) == {"action": "tighten", "stop": 4.41, "r_now": 0.875}
    assert flush_action(t, price=4.33, stop=4.30, **kw) is None       # 4.29 would be lower than the stop


def _bar(t, o, h, lo, c):
    return Bar(t=t, o=o, h=h, lo=lo, c=c, v=1000)


def test_the_scoring_exit_follows_the_flush_and_names_it():
    tr = ScoreTracker(entry=4.38, stop=4.30, target1=4.54, risk=0.08, triggered_at=NOW, entry_bar_t=NOW - 20,
                      flush=FlushPolicy(mode="exit", hold_sec=10))
    assert tr.on_flow(label="flush", price=4.41, bid=4.40, ts=NOW + 5) is None       # inside the hold
    assert tr.on_flow(label="flush", price=4.41, bid=4.40, ts=NOW + 15) == "exit"
    assert tr.exit_px == 4.40 and tr.exit_reason == "flush" and tr.bar_r() == pytest.approx(0.25)
    assert tr.on_bar(_bar(NOW + 40, 4.4, 4.6, 4.2, 4.5), 4.3) is False              # already out


def test_a_tightened_stop_that_is_hit_is_named_for_the_flush_and_the_half_never_lowers_it():
    tr = ScoreTracker(entry=4.38, stop=4.30, target1=4.54, risk=0.08, triggered_at=NOW, entry_bar_t=NOW - 20,
                      flush=FlushPolicy(mode="tighten", hold_sec=0, trail_r=0.5))
    tr.on_bar(_bar(NOW - 20, 4.37, 4.40, 4.36, 4.39), 4.3)                           # the entry bar
    assert tr.on_flow(label="flush", price=4.52, bid=4.51, ts=NOW + 45) == "tighten"
    assert tr.bar_stop == pytest.approx(4.48)
    tr.on_bar(_bar(NOW + 40, 4.50, 4.56, 4.49, 4.55), 4.4)                            # target 1: half off
    assert tr.half_done and tr.bar_stop == pytest.approx(4.48)                         # not back down to 4.38
    assert tr.on_bar(_bar(NOW + 100, 4.52, 4.53, 4.46, 4.47), 4.4) is True
    assert tr.exit_reason == "flush_stop_runner" and tr.exit_px == pytest.approx(4.48)


def test_off_changes_nothing_in_the_scoring():
    tr = ScoreTracker(entry=4.38, stop=4.30, target1=4.54, risk=0.08, triggered_at=NOW, entry_bar_t=NOW - 20)
    assert tr.on_flow(label="flush", price=4.35, bid=4.34, ts=NOW + 60) is None
    assert tr.bar_stop == 4.30 and tr.exit_px is None
