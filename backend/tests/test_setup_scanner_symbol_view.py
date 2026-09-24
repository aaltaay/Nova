"""One symbol across every lane (ADR 035): the levels a forming setup would arm with, the lane's own
indicators, and the per-symbol route. None of it may change what arms."""
from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from setup_scanner import routes
from setup_scanner.bull_flag import BullFlagDetector
from setup_scanner.pullback import PullbackDetector
from setup_scanner.red_to_green import RedToGreenDetector, RedToGreenParams
from setup_scanner.series import Series, macd_hist
from setup_scanner.symbol_view import symbol_view
from tests.setup_scanner_fixtures import add, base_morning, et_ts, leg_up
from tests.test_setup_scanner_every_setup import flag_day, make
from tests.test_setup_scanner_engine import SYM


def pole_then_one_red():
    bars = base_morning()
    for close, vol in ((4.10, 80_000), (4.22, 88_000), (4.34, 96_000)):
        o = bars[-1].c
        add(bars, o, close + 0.01, o - 0.01, close, vol)
    add(bars, 4.34, 4.34, 4.28, 4.29, 30_000)
    return bars


def test_a_one_candle_flag_shows_its_provisional_levels_and_what_it_waits_for():
    det = BullFlagDetector(SYM)
    det.on_bars(pole_then_one_red())
    assert det.state == "leg" and det.armed is None
    f = det.forming
    assert f["trigger"] == 4.34 and f["entry"] == 4.35 and f["stop"] == 4.28 and f["risk"] == 0.07
    assert f["waiting"] == "1 more red or doji candle" and f["bars"] == 1
    assert f["target1"] >= f["entry"] + 2 * f["risk"] - 1e-9
    assert "forming" not in det.view()                   # the board / rows / journal never carry it
    assert det.symbol_view()["forming"] == f


def test_a_complete_flag_arms_and_clears_the_provisional_levels():
    det = BullFlagDetector(SYM)
    det.on_bars(flag_day())
    assert det.state == "armed" and det.forming is None
    assert det.armed["trigger"] == 4.30


def test_a_pullback_blocked_by_its_risk_keeps_the_levels_it_would_arm_with():
    bars = leg_up(base_morning(), [4.10, 4.30, 4.50, 4.70])
    add(bars, 4.70, 4.70, 4.36, 4.60, 40_000)            # one deep pullback candle: risk well over 0.20
    det = PullbackDetector(SYM)
    det.on_bars(bars)
    assert det.state == "pullback" and "over 0.20" in det.reason
    f = det.forming
    assert f["blocked"] == det.reason and f["trigger"] == 4.70 and f["stop"] == 4.36
    assert f["risk"] == round(f["entry"] - f["stop"], 4) and f["risk"] > 0.2


def test_the_forming_levels_go_when_the_setup_stops_forming():
    bars = leg_up(base_morning(), [4.10, 4.30, 4.50, 4.70])
    add(bars, 4.70, 4.70, 4.36, 4.60, 40_000)
    det = PullbackDetector(SYM)
    det.on_bars(bars)
    assert det.forming is not None
    leg_up(bars, [4.80, 4.95])                          # a fresh high: back to "wait for the pullback"
    det.on_bars(bars)
    assert det.state == "leg" and det.forming is None


def test_red_to_green_short_of_its_red_closes_is_provisional():
    bars = base_morning(start_hh=9, start_mm=10, n=20, price=5.00)   # 09:10 .. 09:29
    add(bars, 5.00, 5.05, 4.95, 4.96, 40_000)            # 09:30 opens 5.00, closes under it
    det = RedToGreenDetector(SYM, p=RedToGreenParams(min_red_bars=2))
    det.on_bars(bars)
    assert det.state == "leg" and det.forming is not None
    assert det.forming["trigger"] == 5.00 and det.forming["waiting"] == "1 more close under the open"
    assert det.forming["stop"] == 4.95


def test_the_series_hands_the_gate_its_own_numbers():
    bars = leg_up(base_morning(), [4.10, 4.30, 4.50])
    s = Series()
    s.update(bars)
    v = s.last_values()
    closes = [b.c for b in bars]
    assert v["bars"] == len(bars) and v["close"] == closes[-1]
    assert abs(v["macd_hist"] - macd_hist(closes)[-1]) < 1e-6
    assert abs(v["macd_line"] - v["macd_signal"] - v["macd_hist"]) < 1e-5
    assert v["hod"] == max(b.h for b in bars)
    assert Series().last_values() is None


def test_symbol_view_answers_every_lane_for_a_followed_symbol(tmp_path):
    eng, _, clock = make(tmp_path, pole_then_one_red())
    asyncio.run(eng.tick(clock["t"]))
    view = symbol_view(eng, SYM.lower(), clock["t"])
    assert view["followed"] is True and view["followed_note"] is None and view["symbol"] == SYM
    lanes = {s["setup_type"]: s for s in view["setups"]}
    assert list(lanes) == ["first_pullback", "bull_flag", "flat_top_breakout", "red_to_green"]
    flag = lanes["bull_flag"]
    assert flag["state"] == "leg" and flag["forming"]["waiting"] == "1 more red or doji candle"
    assert flag["series"]["macd_hist"] is not None and flag["template"]["id"] == "default"
    assert flag["rules"]["stop_cap"] == 0.20 and flag["rules"]["target_r"] == 2.0
    assert flag["window"]["start"] == "07:00" and flag["level"] == 1 and flag["chosen"] is False
    assert lanes["first_pullback"]["chosen"] is True
    assert lanes["red_to_green"]["state"] == "watching"   # before the open: the lane says so


def test_symbol_view_says_when_the_scanner_does_not_follow_the_symbol(tmp_path):
    eng, _, clock = make(tmp_path, flag_day())
    asyncio.run(eng.tick(clock["t"]))
    view = symbol_view(eng, "ZZZZ", clock["t"])
    assert view["followed"] is False and view["setups"] == []
    assert "HOD Momo" in view["followed_note"]


def test_a_replay_desk_does_not_pass_the_live_lanes_off_as_the_replays(tmp_path):
    eng, _, clock = make(tmp_path, flag_day())
    asyncio.run(eng.tick(clock["t"]))
    eng._replay_fn = lambda: True
    view = symbol_view(eng, SYM, clock["t"])
    assert view["followed"] is False and "Sim" in view["followed_note"]


def test_the_symbol_route(tmp_path, monkeypatch):
    eng, _, clock = make(tmp_path, flag_day())
    asyncio.run(eng.tick(clock["t"]))
    monkeypatch.setattr(routes, "get_engine", lambda: eng)
    app = FastAPI()
    app.include_router(routes.router)
    body = TestClient(app).get(f"/api/setups/symbol/{SYM}").json()
    assert body["schema_version"] == 1 and body["followed"] is True
    assert {s["setup_type"] for s in body["setups"]} == {"first_pullback", "bull_flag", "flat_top_breakout",
                                                          "red_to_green"}
    assert et_ts(9, 0) > 0
