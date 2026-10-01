"""The 5-minute setups (operator decision 2026-09-30: chart only, 07:00-15:30): a built-in lane per setup runs
the setup's own detector on 5-minute candles made of the scanner's minutes, scores in silence on its own
rows, and never proposes, tells the bot or reaches the Setups board."""
from __future__ import annotations

import asyncio

from constants_setups import SETUPS_5M_BAR_SEC, SETUPS_5M_ENTRY_CUTOFF_ET, SETUPS_5M_STOP_CAP_PCT
from setup_scanner.bars import Bar
from setup_scanner.detector import stop_cap
from setup_scanner.engine import SetupEngine
from setup_scanner.five_minute_lane import Candles, five_minute_params, is_five_minute
from setup_scanner.scoring import ScoreTracker
from setup_scanner.store import SetupStore
from setup_templates.store import TemplateStore
from tests.setup_scanner_fixtures import et_ts
from tests.test_setup_scanner_engine import EYES, FP_ONLY, SYM, FakeTape
from tests.test_setup_scanner_lanes import PILLARS, armed_bars


def stretched(bars: list[Bar], start: float) -> list[Bar]:
    """Each candle of ``bars`` as five one-minute bars from ``start``: the first carries its range, the rest
    sit at its close -- so the 5-minute candles they make are ``bars`` again, five times slower."""
    out = []
    for i, b in enumerate(bars):
        t0 = start + i * SETUPS_5M_BAR_SEC
        out.append(Bar(t0, b.o, b.h, b.lo, b.c, b.v / 5))
        out += [Bar(t0 + 60 * k, b.c, b.c, b.c, b.c, b.v / 5) for k in range(1, 5)]
    return out


def engine(tmp_path, bars: list[Bar]) -> tuple[SetupEngine, dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    clock = {"t": bars[-1].t + 60 + 5}
    eng = SetupEngine(store=SetupStore(tmp_path / "setups.db"), tape=FakeTape(), universe=lambda: [SYM],
                      seed=lambda sym, since: list(bars), replay_desk=lambda: False, audit=lambda **kw: None,
                      clock=lambda: clock["t"], templates=lambda: TemplateStore(tmp_path / "t.json"),
                      journal=lambda e: None, bot_state=lambda: {"level": 1, "active": True, "venue": "paper"},
                      levels=EYES, setups=FP_ONLY)
    eng.pillars = lambda sym, now: dict(PILLARS)
    return eng, clock


def test_the_built_in_rules_are_the_defaults_on_five_minute_candles_with_the_operators_window():
    p = five_minute_params("first_pullback")
    assert (p.template_id, p.template_rev, p.name) == ("5m", 1, "5-minute")
    assert p.bar_sec == SETUPS_5M_BAR_SEC == p.pattern.bar_sec and p.score_window_min == 60
    assert p.pattern.entry_cutoff == SETUPS_5M_ENTRY_CUTOFF_ET == "15:30" and p.pattern.session_start == "07:00"
    assert p.pattern.stop_cap_pct == SETUPS_5M_STOP_CAP_PCT and stop_cap(p.pattern, 17.0) == 1.02
    assert stop_cap(five_minute_params("bull_flag").pattern, 4.0) == 0.24
    assert five_minute_params("flat_top_breakout").pattern.bar_sec == 300


def test_candles_reach_the_detector_only_when_one_completes_and_prices_use_the_candles_open():
    c = Candles()
    minutes = [Bar(et_ts(9, 30) + 60 * i, 10 + i * 0.1, 10.5 + i * 0.1, 9.9, 10.05 + i * 0.1, 100) for i in range(7)]
    assert c.feed("X", minutes[:4], now=et_ts(9, 34)) == (None, None)        # 09:30 still forming
    done, newest = c.feed("X", minutes[:5], now=et_ts(9, 35))
    assert [b.t for b in done] == [et_ts(9, 30)] and newest is done[-1] and done[0].o == 10.0
    assert c.feed("X", minutes[:5], now=et_ts(9, 35)) == (None, None)        # nothing new, nothing fed
    c.feed("X", minutes[:7], now=et_ts(9, 37))
    assert c.bar_open("X", et_ts(9, 37) + 20, minute_open=99.0) == minutes[5].o   # 09:35's first minute
    assert c.bar_open("X", et_ts(9, 40) + 5, minute_open=12.3) == 12.3           # no minute of 09:40 closed yet


def test_a_five_minute_lane_arms_on_its_own_candles_scores_on_its_own_rows_and_never_plays(tmp_path):
    one = armed_bars()                              # arms a 1-minute first pullback
    eng1, clock1 = engine(tmp_path / "a", one)
    asyncio.run(eng1.tick(clock1["t"]))
    want = eng1.playing.det[SYM].armed
    assert want is not None

    five_bars = stretched(one, et_ts(7, 0))         # the same candles, five minutes each
    eng5, clock5 = engine(tmp_path / "b", five_bars)
    asyncio.run(eng5.tick(clock5["t"]))
    lane = next(lane for lane in eng5.lanes if is_five_minute(lane))
    assert lane.setup == "first_pullback" and not lane.playing and eng5.playing is not lane
    armed = lane.det[SYM].armed
    assert armed is not None and (armed["trigger"], armed["stop"]) == (want["trigger"], want["stop"])
    assert armed["armed_at"] == armed["armed_bar_t"] + SETUPS_5M_BAR_SEC        # the candle's close, not +60
    row = next(r for r in eng5.store.rows() if r["template_id"] == "5m")
    assert row["id"].endswith("~5m") and row["setup_type"] == "first_pullback"
    assert lane.tf5[SYM] is None                    # the 5-minute read is a 1-minute lane's
    board = eng5.board(clock5["t"])
    assert all(r.get("setup_id") is None or not str(r["setup_id"]).endswith("~5m") for r in board["rows"])
    assert board["setups"][0]["templates_watched"] == 1

    # Near and go: the playing lane proposes; the 5-minute lane never does.
    price = float(armed["trigger"]) - 0.01
    eng5.on_l1_minute("last", SYM, {"price": price, "ts": clock5["t"] + 2, "bar_open": price})
    asyncio.run(eng5.tick(clock5["t"] + 2))
    assert lane.proposals == {} and lane.alerts == []


def test_a_five_minute_trade_is_scored_on_five_minute_candles():
    tr = ScoreTracker(entry=10.0, stop=9.5, target1=11.0, risk=0.5, triggered_at=et_ts(10, 2),
                      entry_bar_t=et_ts(10, 0), window_min=60, bar_sec=300)
    assert not tr.on_bar(Bar(et_ts(10, 0), 10.0, 10.2, 9.9, 10.1, 1), 9.8)      # the entry candle
    assert tr.on_bar(Bar(et_ts(10, 5), 10.1, 10.1, 9.4, 9.6, 1), 9.8)          # the stop, one candle later
    assert tr.closed_at == et_ts(10, 10) and tr.exit_reason == "stop"
    assert tr.on_price(10.4, et_ts(10, 50)) is False and round(tr.mfe, 4) == 0.4           # MFE read within the hour


def test_the_five_minute_lanes_setups_are_folded_apart_from_the_setups_in_play():
    from eyes.episodes import EpisodeFold, closed_bar_t
    from tests.test_setup_episodes import ncpl_lines

    lines = ncpl_lines()
    five = [{**ln, "template": "5m", "playing": False} for ln in lines]
    in_play, five_fold = EpisodeFold(), EpisodeFold("5m", SETUPS_5M_BAR_SEC)
    for ln in lines + five:
        in_play.apply(ln)
        five_fold.apply(ln)
    assert len(in_play.episodes()) == len(five_fold.episodes()) > 0        # each reads only its own lines
    # A line written just after a 5-minute candle closed is about that candle; later, the forming one.
    assert closed_bar_t(et_ts(10, 5) + 0.3, SETUPS_5M_BAR_SEC) == et_ts(10, 0)
    assert closed_bar_t(et_ts(10, 7), SETUPS_5M_BAR_SEC) == et_ts(10, 5)
    assert closed_bar_t(et_ts(10, 7) + 0.3) == et_ts(10, 6)               # a minute lane's, unchanged


def test_the_route_reads_the_five_minute_lanes_with_tf_5m_and_the_symbol_view_carries_them(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from setup_scanner.symbol_view import symbol_view
    from stock_read import past_setups, routes

    seen = {}

    def fake(sym, day, now, *, today, five=False):
        seen["five"] = five
        return {"symbol": sym, "date": day, "generated_at": now, "timeframe": "5m" if five else "1m",
                "episodes": [], "counts": {}, "journal": {"ok": True, "error": None, "lines": 0},
                "bars": {"ok": True, "error": None, "count": 0}}

    monkeypatch.setattr(past_setups, "read", fake)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    assert client.get("/api/stock-read/IOVA/past-setups?tf=5m").json()["timeframe"] == "5m" and seen["five"] is True
    assert client.get("/api/stock-read/IOVA/past-setups").status_code == 200 and seen["five"] is False
    assert client.get("/api/stock-read/IOVA/past-setups?tf=15m").status_code == 400

    eng, clock = engine(tmp_path, stretched(armed_bars(), et_ts(7, 0)))
    asyncio.run(eng.tick(clock["t"]))
    view = symbol_view(eng, SYM, clock["t"])
    assert [s["timeframe"] for s in view["setups"]] == ["1m"]
    [five] = view["setups_5m"]
    assert five["timeframe"] == "5m" and five["template"]["id"] == "5m" and five["level"] == 0 and not five["chosen"]
    assert five["state"] == "armed" and five["rules"]["bar_sec"] == 300 and five["rules"]["stop_cap_pct"] == 0.06
    assert five["window"]["end"] == "15:30"
