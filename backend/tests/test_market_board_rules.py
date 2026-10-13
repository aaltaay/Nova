"""The Market page's pure rules (ADR 053): the day read, the clock, ETF moves, the events window."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_board import clock, day_read, events, sectors

# 2026-10-13 is a Tuesday; 2026-10-12 (Columbus Day) the NYSE was open and the bond market closed.
TUE_0930 = clock.at(date(2026, 10, 13), 9 * 60 + 30)


def _fut(*moves):
    return {k: {"change_pct": m} for k, m in zip(("es", "nq", "rty", "ym"), moves, strict=True)}


def test_futures_check_counts_up_and_down():
    assert day_read.futures(_fut(0.6, 0.9, 1.3, 0.2))["state"] == "green"
    assert day_read.futures(_fut(-0.6, -0.9, -1.3, 0.2))["state"] == "red"
    assert day_read.futures(_fut(0.6, -0.9, 1.3, -0.2))["state"] == "amber"
    assert day_read.futures(_fut(0.6, None, 1.3, 0.2))["state"] == "unknown"


def test_breadth_check_waits_before_the_open_and_reads_the_ratio():
    assert day_read.breadth({"state": "waiting"}, TUE_0930)["starts_at"] == TUE_0930
    ok = day_read.breadth({"state": "ok", "advancing": 2012, "declining": 838}, TUE_0930)
    assert ok["state"] == "green" and ok["text"] == "2.4 : 1"
    assert day_read.breadth({"state": "ok", "advancing": 800, "declining": 2000}, TUE_0930)["state"] == "red"
    assert day_read.breadth({"state": "unavailable", "why": "354: not subscribed"}, TUE_0930)["why"] == "354: not subscribed"


def test_vix_small_caps_runners_gappers():
    assert day_read.vix({"change_pct": -6.2, "last": 15.84})["state"] == "green"
    assert day_read.vix({"change_pct": 4.0, "last": 19.0})["label"] == "Fear gauge rising (VIX)"
    assert day_read.small_caps(0.69)["state"] == "green" and day_read.small_caps(-0.4)["state"] == "red"
    assert day_read.runners(17, 11.0)["state"] == "green" and day_read.runners(17, None)["state"] == "unknown"
    assert day_read.gappers(7, 12, True, TUE_0930)["state"] == "amber"
    assert day_read.gappers(0, 0, False, TUE_0930)["state"] == "waiting"
    assert day_read.gappers(1, 2, True, TUE_0930)["state"] == "unknown"


def test_verdict_needs_three_known_and_a_net_of_three():
    g, r, a, w = ({"state": s} for s in ("green", "red", "amber", "waiting"))
    assert day_read.verdict([g, g, g, g, g, a])["verdict"] == "bullish"
    assert day_read.verdict([r, r, r, a, w, w])["verdict"] == "bearish"
    assert day_read.verdict([g, g, r, a, w, w])["verdict"] == "mixed"
    assert day_read.verdict([g, g, w, w, w, w])["verdict"] is None


def test_clock_trading_date_rolls_at_0400_and_skips_closed_days():
    assert clock.trading_date(clock.at(date(2026, 10, 13), 3 * 60 + 59)) == date(2026, 10, 12)
    assert clock.trading_date(clock.at(date(2026, 10, 13), 4 * 60)) == date(2026, 10, 13)
    assert clock.trading_date(clock.at(date(2026, 10, 11), 12 * 60)) == date(2026, 10, 9)   # Sunday -> Friday
    assert clock.sessions_back(date(2026, 10, 13), 5)[0] == date(2026, 10, 7)
    assert clock.phase(clock.at(date(2026, 11, 27), 13 * 60 + 30)) == "after_hours"         # early close
    assert clock.session(clock.at(date(2026, 11, 26), 12 * 60))["holiday"].startswith("US stocks closed")


def test_etf_change_for_each_period():
    closes = {"XLK": [["2026-10-05", 100.0], ["2026-10-06", 101.0], ["2026-10-07", 102.0], ["2026-10-08", 103.0],
                      ["2026-10-09", 104.0], ["2026-10-12", 105.0], ["2026-10-13", 106.0]]}
    quotes = {"XLK": {"price": 107.1, "prev_close": 105.0}}
    get = closes.get
    assert sectors.change("XLK", "1D", quotes, get, "2026-10-13") == pytest.approx(2.0)
    assert sectors.change("XLK", "7D", quotes, get, "2026-10-13") == pytest.approx(6.04)   # vs Oct 6's close
    assert sectors.change("XLK", "30D", quotes, get, "2026-10-13") is None                # too few sessions
    assert sectors.spark("XLK", "7D", get, "2026-10-13") == [101.0, 102.0, 103.0, 104.0, 105.0, 106.0]


def test_events_window_and_bond_market():
    items = events.upcoming(date(2026, 10, 13), bea=None, earnings=[
        {"symbol": "JPM", "date": "2026-10-14", "hour": "bmo"}, {"symbol": "ZZZZ", "date": "2026-10-14", "hour": "amc"}],
        biggest={"JPM"})
    titles = [(e["title"], e["source"]) for e in items]
    assert ("CPI", "bls") in titles and ("PPI", "bls") in titles and ("JPM earnings", "finnhub") in titles
    assert all(t != "ZZZZ earnings" for t, _ in titles)
    assert events.bond_market(date(2026, 10, 12)) == {"closed": True, "early_close_at": None, "why": "Columbus Day"}
    assert events.bond_market(date(2026, 11, 27))["early_close_at"] == clock.at(date(2026, 11, 27), 14 * 60)
