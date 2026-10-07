"""The 5-minute flat top (ADR 031 amendment 2026-10-06; operator: "Make the 5-minute flat top a Paper buy with a
1-minute hold entry, as the material trades it").

A strategy of its own: a 1-minute lane like every other, whose detector reads the flat top on 5-minute candles
made of the minutes it is fed and, after a price over the flat top, the hold on the minutes -- the first minute
that holds the touch zone and closes green over the high is the entry, the stop at the pullback's low. It proposes
at Eyes, tells the bot at its trigger, and the bot takes it at On like any setup.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from setup_scanner.bars import Bar
from setup_scanner.detectors import make_detector
from setup_scanner.engine import SetupEngine
from setup_scanner.flat_top_5m import FlatTop5mDetector, five_minute_candles
from setup_scanner.lane_params import lane_params
from setup_scanner.store import SetupStore
from setup_templates import catalogue
from setup_templates.store import TemplateStore, default_template
from tests.setup_scanner_fixtures import et_ts
from tests.test_setup_scanner_engine import SYM, FakeTape, bar_msg

FT5 = "flat_top_5m"
LEVEL = 4.50


def params(**values):
    """The default template's pattern, with ``values`` over its own."""
    t = default_template(FT5)
    return lane_params(SimpleNamespace(id=t.id, rev=t.rev, fingerprint="x", name=t.name, setup=FT5,
                                       values={**t.values, **values})).pattern


def candle(t0: float, o: float, h: float, lo: float, c: float, v: float = 50_000) -> list[Bar]:
    """One 5-minute candle as its five minutes: flat, up to the high, down to the low, to the close, flat."""
    m = v / 5
    return [Bar(t0, o, o, o, o, m), Bar(t0 + 60, o, h, o, o, m), Bar(t0 + 120, o, o, lo, o, m),
            Bar(t0 + 180, o, max(o, c), min(o, c), c, m), Bar(t0 + 240, c, c, c, c, m)]


def flat_top_morning() -> list[Bar]:
    """Two quiet hours at 4.00 from 05:00, a 5-minute run to 4.50, then two 5-minute candles tapping it."""
    t = et_ts(5, 0)
    bars: list[Bar] = []
    for i in range(24):
        bars += candle(t, 4.00, 4.01, 3.99, 4.00 + (0.005 if i % 2 else 0.0), 20_000)
        t += 300
    for o, c in ((4.00, 4.12), (4.12, 4.26), (4.26, 4.40)):
        bars += candle(t, o, c + 0.01, o - 0.01, c, 90_000)
        t += 300
    bars += candle(t, 4.40, LEVEL, 4.39, 4.47, 90_000)      # the first touch: the high of day
    t += 300
    bars += candle(t, 4.47, 4.49, 4.45, 4.48, 40_000)       # a retest a cent under it
    t += 300
    bars += candle(t, 4.48, 4.50, 4.46, 4.48, 30_000)       # the third touch: armed when it is over
    return bars


def feed(det, bars: list[Bar]) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for k in range(len(bars)):
        out += det.on_bars(bars[:k + 1])
    return out


def armed() -> tuple[FlatTop5mDetector, list[Bar]]:
    bars = flat_top_morning()
    det = make_detector(FT5, SYM, params())
    feed(det, bars)
    assert det.state == "armed", det.reason
    return det, bars


def minute(bars: list[Bar], o: float, h: float, lo: float, c: float) -> Bar:
    b = Bar(bars[-1].t + 60, o, h, lo, c, 20_000)
    bars.append(b)
    return b


def broken(det, bars: list[Bar]) -> Bar:
    """A price over the flat top in the next minute, and that minute's close."""
    b = minute(bars, 4.48, 4.53, 4.48, 4.51)
    assert det.on_price(4.52, b.t + 20)[0][0] == "near"
    assert det.broke["bar_t"] == b.t                         # the break's own minute, not its 5-minute candle
    assert det.on_bars(bars) == []                           # the break's minute is not the hold
    return b


def test_the_pattern_reads_5_minute_candles_and_only_once_one_is_over():
    bars = flat_top_morning()
    done = five_minute_candles(bars)
    assert len(done) == len(bars) // 5 and done[-1].h == LEVEL and done[-1].t == bars[-5].t
    assert len(five_minute_candles(bars[:-1])) == len(done) - 1          # its last minute is not in yet
    det = make_detector(FT5, SYM, params())
    assert isinstance(det, FlatTop5mDetector) and det.p.bar_sec == 300 and det.p.hold_bar_sec == 60
    feed(det, bars[:-1])
    assert det.state == "leg" and "2 of 3 touches" in det.reason      # forming: two 5-minute touches
    assert det.on_bars(bars)[0][0] == "armed"
    a = det.armed
    assert (a["trigger"], a["entry"], a["stop"], a["kind"]) == (LEVEL, 4.51, 4.45, "flat_top_5m")   # the base low
    assert a["armed_bar_t"] == bars[-5].t and a["armed_at"] == bars[-5].t + 300
    assert len(a["detail"]["touches"]) == 3 and "a green 1-minute candle holding over it (up to 5)" in det.reason


def test_the_first_minute_that_holds_and_closes_green_is_the_entry_with_the_pullbacks_low_as_its_stop():
    det, bars = armed()
    broken(det, bars)
    minute(bars, 4.51, 4.51, 4.48, 4.49)                    # the pullback: red, still in the touch zone
    assert det.on_bars(bars) == [] and det.state == "near"
    assert det.reason == "broke 4.50: 1 of 5 minutes, none held over it and closed green yet"
    hold = minute(bars, 4.49, 4.53, 4.49, 4.52)             # holds the zone, closes green over the high
    [(name, view)] = det.on_bars(bars)
    s = view["setup"]
    assert name == "triggered" and s["kind"] == "flat_top_5m"
    assert (s["entry"], s["stop"], s["risk"]) == (4.53, 4.48, 0.05)          # the pullback went to 4.48
    assert s["triggered_at"] == hold.t + 60 and s["score_bar_t"] == hold.t and s["half_on_entry_bar"] is False
    assert s["detail"]["hold_bar_t"] == hold.t and s["detail"]["broke_bar_t"] == hold.t - 120
    assert "a green 1-minute candle closed at 4.52" in view["reason"]


def test_a_template_may_stop_at_the_hold_minutes_low_instead():
    bars = flat_top_morning()
    det = make_detector(FT5, SYM, params(ft_hold_stop="candle"))
    feed(det, bars)
    broken(det, bars)
    minute(bars, 4.51, 4.51, 4.48, 4.49)
    minute(bars, 4.49, 4.53, 4.49, 4.52)
    s = det.on_bars(bars)[0][1]["setup"]
    assert (s["stop"], s["risk"]) == (4.49, 0.04)


def test_a_minute_closing_under_the_zone_fails_it_and_five_without_a_hold_disarm_it():
    det, bars = armed()
    broken(det, bars)
    minute(bars, 4.50, 4.50, 4.45, 4.46)                    # under the zone (4.4775)
    assert det.on_bars(bars)[0][0] == "failed" and "closed back under the 4.50 high" in det.reason

    det, bars = armed()
    broken(det, bars)
    for _ in range(4):
        minute(bars, 4.50, 4.50, 4.48, 4.49)
        assert det.on_bars(bars) == []
    minute(bars, 4.50, 4.50, 4.48, 4.49)
    [(name, view)] = det.on_bars(bars)
    assert name == "disarmed" and view["reason"] == "no 1-minute candle held over 4.50 and closed green within 5"


def test_the_scoring_exit_reads_the_minutes_ema():
    det, bars = armed()
    assert det.ema_now == det.minutes.e[-1] and det.ema_now != det.series.e[-1]
    assert len(det.minutes.t) == len(bars) and len(det.series.t) == len(bars) // 5


def test_its_catalogue_is_the_flat_tops_on_5_minute_candles_with_the_hold_on_the_minutes():
    values = catalogue.defaults(FT5)
    assert values["ft_hold_bars"] == 5 and values["ft_hold_stop"] == "pullback" and values["entry_cutoff"] == "15:30"
    assert values["ft_min_touches"] == 3 and values["bot_window_start"] == "07:00" and values["bot_window_end"] == "10:00"
    specs = {s.key: s for s in catalogue.specs(FT5)}
    assert specs["ft_min_consol"].unit == "5-min candles" and specs["ft_hold_bars"].unit == "minutes"
    assert [v for v, _ in specs["ft_hold_stop"].choices] == ["pullback", "candle"]
    with pytest.raises(catalogue.TemplateError):
        catalogue.validate(FT5, {**values, "ft_hold_stop": "the moon"})
    assert default_template(FT5).rev == 1
    p = params()
    assert (p.bar_sec, p.hold_bar_sec, p.hold_stop, p.stop_cap_pct) == (300, 60, "pullback", None)


# -- the lane: it proposes, and tells the bot ----------------------------------------------------
def make_engine(tmp_path, seed: list[Bar], level: int = 1):
    audits: list[dict] = []
    clock = {"t": seed[-1].t + 30}
    eng = SetupEngine(store=SetupStore(tmp_path / "setups.db"), tape=FakeTape(), universe=lambda: [SYM],
                      seed=lambda sym, since: list(seed), replay_desk=lambda: False,
                      audit=lambda **kw: audits.append(kw), clock=lambda: clock["t"],
                      templates=lambda: TemplateStore(tmp_path / "t.json"), journal=lambda e: None,
                      levels=lambda: {"chosen": None, "levels": {FT5: level}}, setups=(FT5,))
    eng.pillars = lambda sym, now: {"price": 4.5, "change_pct": 12.0, "rvol": 6.0, "float": 9e6, "news": None,
                                    "headline": None, "catalyst": None}
    return eng, audits, clock


def test_its_lane_proposes_at_eyes_and_announces_its_trigger(tmp_path):
    bars = flat_top_morning()
    eng, audits, clock = make_engine(tmp_path, bars)
    heard: list[dict] = []
    eng.add_trigger_listener(heard.append)
    asyncio.run(eng.tick(clock["t"]))
    lane = eng.playing_lane(FT5)
    assert lane is not None and lane.p.bar_sec == 60 and lane.det[SYM].state == "armed"

    eng.on_l1_minute("last", SYM, {"price": 4.49, "ts": clock["t"], "bar_open": 4.48})
    asyncio.run(eng.tick(clock["t"]))
    [prop] = lane.open_proposals()
    assert prop["setup_type"] == FT5 and prop["trigger"] == LEVEL and prop["symbol"] == SYM
    assert prop["setup_id"].endswith("@flat_top_5m")

    brk = Bar(bars[-1].t + 60, 4.48, 4.53, 4.48, 4.51, 20_000)
    clock["t"] = brk.t + 20
    eng.on_l1_minute("last", SYM, {"price": 4.52, "ts": clock["t"], "bar_open": 4.48})
    asyncio.run(eng.tick(clock["t"]))
    for b in (brk, Bar(brk.t + 60, 4.51, 4.51, 4.48, 4.49, 20_000), Bar(brk.t + 120, 4.49, 4.53, 4.49, 4.52, 20_000)):
        eng.on_l1_minute("bar", SYM, bar_msg(b))
        clock["t"] = b.t + 61
        asyncio.run(eng.tick(clock["t"]))
    [event] = heard
    assert event["setup_type"] == FT5 and event["setup"]["kind"] == "flat_top_5m"
    assert event["setup"]["entry"] == 4.53 and event["setup"]["stop"] == 4.48
    [row] = eng.store.rows(setup_type=FT5)
    assert row["triggered_at"] == brk.t + 180 and row["kind"] == "flat_top_5m" and row["entry"] == 4.53
    # Its pattern is the 5-minute chart: its rows carry no 5-minute read, so trial T8 stays the 1-minute setups'.
    assert row["tf5_armed"] is None and row["tf5_trigger"] is None


def test_at_off_it_watches_and_scores_in_silence(tmp_path):
    bars = flat_top_morning()
    eng, _, clock = make_engine(tmp_path, bars, level=0)
    asyncio.run(eng.tick(clock["t"]))
    eng.on_l1_minute("last", SYM, {"price": 4.49, "ts": clock["t"], "bar_open": 4.48})
    asyncio.run(eng.tick(clock["t"]))
    lane = eng.playing_lane(FT5)
    assert lane.det[SYM].state == "near" and lane.open_proposals() == []


def test_the_bot_takes_its_trigger_at_on_and_holds_it_back_at_off():
    """The bot's admission is one rule for every setup: at On (Strategy) on Paper the 5-minute flat top's go
    trigger meets no blocker; at Off it is held back with the setup's level as the reason."""
    from bot.first_pullback.admit import blockers
    from bot.persist import load_session
    from tests.bot_helpers import ready_l2

    now = 1_790_000_000.0
    event = {"symbol": "IMCC", "setup_id": "IMCC-2026-09-24-1@flat_top_5m", "setup_type": FT5,
             "setup": {"kind": "flat_top_5m", "trigger": 10.0, "entry": 10.06, "stop": 10.01, "risk": 0.05,
                       "target1": 10.16, "triggered_at": now, "nth": 1},
             "tape": {"verdict": "go", "reasons": ["green"]}, "grade": "A",
             "pillars": {"passed": 5, "known": 5, "total": 5}, "filtered": None, "spread": 0.02}
    ready_l2(brain=None, symbols=("IMCC",), setups=("first_pullback",))
    held = dict(blockers(event, load_session(), now=now))
    assert "BOT_SETUP_NOT_STRATEGY" in held
    ready_l2(brain=None, symbols=("IMCC",), setups=(FT5,))
    assert dict(blockers(event, load_session(), now=now)) == {}
