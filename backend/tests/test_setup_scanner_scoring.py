"""Scoring a triggered setup, the store, and the summary (ADR 022)."""
from __future__ import annotations

import sqlite3

import pytest

from setup_scanner.bars import Bar
from setup_scanner.scoring import ScoreTracker
from setup_scanner.store import SetupStore, StoreVersionError
from setup_scanner.summary import net_r, summarize
from tests.setup_scanner_fixtures import et_ts

T0 = et_ts(9, 45)


def tracker(**kw):
    base = dict(entry=4.38, stop=4.30, target1=4.54, risk=0.08, triggered_at=T0 + 5, entry_bar_t=T0)
    base.update(kw)
    return ScoreTracker(**base)


def bar(i: int, o, h, lo, c) -> Bar:
    return Bar(T0 + 60 * i, o, h, lo, c, 10_000)


def test_first_touch_target_and_excursions():
    t = tracker()
    t.on_price(4.36, T0 + 20)
    t.on_price(4.50, T0 + 40)
    assert t.outcome == "open"
    assert t.on_price(4.55, T0 + 70) is True
    assert t.outcome == "target_first"
    t.on_price(4.20, T0 + 90)                  # after the outcome: still counts for MAE in the window
    assert t.outcome == "target_first"
    assert t.mfe == pytest.approx(0.17) and t.mae == pytest.approx(-0.18)


def test_first_touch_stop():
    t = tracker()
    t.on_price(4.29, T0 + 30)
    assert t.outcome == "stop_first"


def test_the_bots_exit_half_at_target_1_the_rest_at_target_2_and_the_stop_stays():
    """#845: the scoring exit is the bot's -- half at target 1, the rest at target 2; the stop does not move to
    the entry after the first half, and the 9 EMA exits nothing."""
    t = tracker(target2=4.70, target1_fraction=0.5)
    assert t.on_bar(bar(0, 4.33, 4.45, 4.33, 4.44)) is False                 # entry bar
    assert t.on_bar(bar(1, 4.44, 4.56, 4.42, 4.55)) is False                 # target 1: half at 4.54
    assert t.half_done and t.half_px == 4.54 and t.bar_stop == 4.30          # the stop stays where it was
    assert t.on_bar(bar(2, 4.55, 4.56, 4.40, 4.41), ema9=4.45) is False      # a close under the 9 EMA: still in
    assert t.on_bar(bar(3, 4.42, 4.72, 4.41, 4.69)) is True                  # target 2
    assert t.exit_reason == "target2" and t.exit_px == 4.70
    assert t.bar_r() == pytest.approx((0.5 * 0.16 + 0.5 * 0.32) / 0.08, abs=1e-3)


def test_after_target_1_the_rest_stops_at_the_original_stop():
    t = tracker(target2=4.70, target1_fraction=0.5)
    t.on_bar(bar(0, 4.33, 4.45, 4.33, 4.44))
    t.on_bar(bar(1, 4.44, 4.56, 4.42, 4.55))                                  # half at 4.54
    assert t.on_bar(bar(2, 4.50, 4.51, 4.36, 4.37)) is False                  # under the entry, over the stop
    assert t.on_bar(bar(3, 4.37, 4.38, 4.28, 4.29)) is True
    assert t.exit_reason == "stop_runner" and t.exit_px == 4.30
    assert t.bar_r() == pytest.approx((0.5 * 0.16 - 0.5 * 0.08) / 0.08, abs=1e-3)


def test_without_a_target_2_everything_sells_at_target_1():
    t = tracker()                                                            # target2 None: fraction 1.0
    assert t.target2 is None and t.target1_fraction == 1.0
    t.on_bar(bar(0, 4.33, 4.45, 4.33, 4.44))
    assert t.on_bar(bar(1, 4.44, 4.56, 4.42, 4.55)) is True
    assert t.exit_reason == "target" and t.exit_px == 4.54 and t.bar_r() == pytest.approx(2.0)


def test_a_bar_that_reaches_both_targets_sells_both():
    t = tracker(target2=4.70, target1_fraction=0.25)
    t.on_bar(bar(0, 4.33, 4.45, 4.33, 4.44))
    assert t.on_bar(bar(1, 4.44, 4.75, 4.42, 4.72)) is True
    assert (t.half_px, t.exit_px, t.exit_reason) == (4.54, 4.70, "target2")
    assert t.bar_r() == pytest.approx((0.25 * 0.16 + 0.75 * 0.32) / 0.08, abs=1e-3)


def test_net_r_counts_three_fills_once_part_sold_at_target_1():
    assert net_r({"bar_r": 1.0, "risk": 0.10, "bar_exit_reason": "target2"}) == pytest.approx(0.7)
    assert net_r({"bar_r": 1.0, "risk": 0.10, "bar_exit_reason": "target"}) == pytest.approx(0.8)
    assert net_r({"bar_r": 1.0, "risk": 0.10, "bar_exit_reason": "stop_runner"}, 0.02) == pytest.approx(0.4)


def test_bar_rules_entry_bar_stop_only_on_a_close_below():
    t = tracker()
    assert t.on_bar(bar(0, 4.33, 4.40, 4.25, 4.35), ema9=4.20) is False      # low under, close over
    t = tracker()
    assert t.on_bar(bar(0, 4.33, 4.40, 4.25, 4.28), ema9=4.20) is True
    assert t.exit_reason == "stop_entry_bar" and t.bar_r() == pytest.approx(-1.0)


def test_bar_rules_bailout_after_five_bars():
    t = tracker()
    t.on_bar(bar(0, 4.33, 4.40, 4.33, 4.39), ema9=4.20)
    closed = False
    for i in range(1, 6):
        closed = t.on_bar(bar(i, 4.38, 4.40, 4.35, 4.37), ema9=4.20)
    assert closed and t.exit_reason == "bailout"


def test_gap_through_the_stop_fills_at_the_open():
    t = tracker()
    t.on_bar(bar(0, 4.33, 4.40, 4.33, 4.39), ema9=4.20)
    t.on_bar(bar(1, 4.20, 4.22, 4.10, 4.15), ema9=4.20)
    assert t.exit_px == 4.20 and t.bar_r() == pytest.approx(-2.25)


def test_store_round_trip_and_json(tmp_path):
    s = SetupStore(tmp_path / "setups.db")
    s.upsert({"id": "ABC-2026-09-21-1", "session_date": "2026-09-21", "symbol": "ABC", "armed_at": T0,
              "trigger": 4.37, "risk": 0.08, "trigger_tape": {"verdict": "go", "reasons": ["green"]}})
    s.upsert({"id": "ABC-2026-09-21-1", "session_date": "2026-09-21", "symbol": "ABC", "bar_r": 1.2})
    rows = s.rows(date_from="2026-09-21")
    assert len(rows) == 1
    assert rows[0]["trigger"] == 4.37 and rows[0]["bar_r"] == 1.2
    assert rows[0]["trigger_tape"]["verdict"] == "go"
    s.close()


def test_store_refuses_an_unknown_version(tmp_path):
    p = tmp_path / "setups.db"
    conn = sqlite3.connect(p)
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    with pytest.raises(StoreVersionError):
        SetupStore(p)


def test_summary_splits_by_tape_verdict():
    rows = [
        {"armed_at": T0, "triggered_at": T0 + 60, "risk": 0.1, "bar_r": 1.5, "outcome": "target_first",
         "trigger_tape": {"verdict": "go"}, "grade": "A", "kind": "first_pullback", "mfe": 0.2, "mae": -0.02},
        {"armed_at": T0, "triggered_at": T0 + 60, "risk": 0.1, "bar_r": -1.0, "outcome": "stop_first",
         "trigger_tape": {"verdict": "wait"}, "grade": "A", "kind": "first_pullback", "mfe": 0.01, "mae": -0.1},
        {"armed_at": T0, "grade": "B", "kind": "first_pullback"},
    ]
    s = summarize(rows)
    assert s["all"]["armed"] == 3 and s["all"]["triggered"] == 2
    assert s["by"]["tape_at_trigger"]["go"]["avg_r"] == 1.5
    assert s["by"]["tape_at_trigger"]["wait"]["win_pct"] == 0.0
    assert s["by"]["session"]["regular"]["armed"] == 3
    assert net_r(rows[0]) == pytest.approx(1.5 - 0.2)
