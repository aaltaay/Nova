"""Regression: final OHLCV must not leak into an unfinished replay interval."""
import json
from datetime import datetime

import pytest

import bars_store
import chart_bars
from archive import db as archive_db
from sim import capture_player as player, mode, replay, session_clock
from sim.chart_replay import completed_start_cutoff


def stamp(value):
    return datetime.fromisoformat(value).timestamp()


def candle(t, price=10):
    return dict(t=t, o=price, h=price + 2, l=price - 1, c=price + 1, v=100)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    mode.reset_for_tests()
    player.reset_for_tests()
    replay.reset_for_tests()
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    mode.set_sim_mode(True)
    yield
    mode.reset_for_tests()
    replay.reset_for_tests()


def fetch(tf="1Min", limit=10):
    return chart_bars.fetch_chart_bars("IMCC", tf, limit, discovery_provider="ibkr")


def test_real_history_cutoff_before_limit_and_backward_seek(monkeypatch):
    bars_store.write_payload(dict(symbol="IMCC", timeframe="1Min", bars=[
        candle("2026-09-18T13:30:00Z"), candle("2026-09-18T13:31:00Z"),
        candle("2026-09-18T13:32:00Z", 90), candle("2026-09-18T19:00:00Z", 900),
    ]))
    monkeypatch.setattr(session_clock, "now_et", lambda: datetime.fromisoformat("2026-09-18T13:32:17+00:00"))
    result = fetch(limit=1)
    assert [b["t"] for b in result["bars"]] == ["2026-09-18T13:31:00Z"]
    assert result["coverage"]["replay_mode"] == "completed_bars"
    monkeypatch.setattr(session_clock, "now_et", lambda: datetime.fromisoformat("2026-09-18T13:30:59+00:00"))
    assert fetch()["bars"] == []
    # The shared live store was not pruned or otherwise mutated by replay reads.
    assert len(bars_store.read("IMCC", "1Min", 10)["bars"]) == 4


def test_real_intraday_replay_does_not_paint_prior_session(monkeypatch):
    bars_store.write_payload(dict(symbol="IMCC", timeframe="5Min", bars=[
        candle("2026-09-18T13:30:00Z"),
        candle("2026-09-18T19:55:00Z", 90),
    ]))
    monkeypatch.setattr(session_clock, "now_et", lambda: datetime.fromisoformat(
        "2026-09-19T06:46:00-04:00",
    ))
    assert fetch("5Min")["bars"] == []
    assert len(bars_store.read("IMCC", "5Min", 10)["bars"]) == 2


def test_weekend_wall_clock_replays_last_trading_day(monkeypatch):
    """Saturday 04:41 ET with no capture selected reads Friday 04:00-04:40."""
    bars_store.write_payload(dict(symbol="SPY", timeframe="1Min", bars=[
        candle("2026-09-18T08:00:00Z", 1),
        candle("2026-09-18T08:40:00Z", 2),
        candle("2026-09-18T08:41:00Z", 3),
        candle("2026-09-18T23:55:00Z", 4),
    ]))
    session_clock.reset_for_tests()
    monkeypatch.setattr(session_clock, "_wall_et_now", lambda: datetime(
        2026, 9, 19, 4, 41, 16, tzinfo=session_clock.ET,
    ))
    result = chart_bars.fetch_chart_bars("SPY", "1Min", 10, discovery_provider="ibkr")
    assert [b["t"] for b in result["bars"]] == [
        "2026-09-18T08:00:00Z", "2026-09-18T08:40:00Z",
    ]
    assert result["coverage"]["replay"] is True


def test_real_intraday_replay_shows_only_closed_bars_on_selected_day(monkeypatch):
    bars_store.write_payload(dict(symbol="IMCC", timeframe="1Min", bars=[
        candle("2026-09-17T19:00:00Z", 1),
        candle("2026-09-18T09:59:00Z", 2),
        candle("2026-09-18T10:00:00Z", 3),
        candle("2026-09-18T10:01:00Z", 4),
    ]))
    monkeypatch.setattr(session_clock, "now_et", lambda: datetime.fromisoformat(
        "2026-09-18T06:01:30-04:00",
    ))
    assert [b["t"] for b in fetch("1Min")["bars"]] == [
        "2026-09-18T09:59:00Z", "2026-09-18T10:00:00Z",
    ]


@pytest.mark.parametrize("tf,cutoff", [
    ("10Sec", "2026-09-18T13:31:07+00:00"),
    ("5Min", "2026-09-18T13:26:17+00:00"),
    ("1Day", "2026-09-17T23:59:59+00:00"),
    ("1Week", "2026-09-13T23:59:59+00:00"),
    ("1Month", "2026-08-31T23:59:59+00:00"),
])
def test_completed_calendar_and_intraday_boundary(tf, cutoff):
    now = datetime.fromisoformat("2026-09-18T09:31:17-04:00")
    assert completed_start_cutoff(tf, now) == stamp(cutoff)


def prepare_capture(monkeypatch):
    start = stamp("2026-09-18T13:31:00+00:00")
    prints = [dict(ts=start + sec, price=px, size=size) for sec, px, size in
              [(0, 10, 5), (5, 12, 8), (17, 11, 2), (18, 99, 885)]]
    selection = player.CaptureData("2026-09-18|IMCC", "IMCC", prints, [], [],
                                   [p["ts"] for p in prints], [], [])
    monkeypatch.setattr(player, "_state", selection)
    return start


def test_partial_candle_only_contains_reached_prints_and_rewinds(monkeypatch):
    start = prepare_capture(monkeypatch)
    bars = player.chart_bars("1Min", 10, asof=start + 17)
    assert bars == [dict(t="2026-09-18T13:31:00Z", o=10, h=12, l=10, c=11, v=15, partial=True)]
    earlier = player.chart_bars("1Min", 10, asof=start + 4)
    assert earlier[0]["h"] == 10 and earlier[0]["v"] == 5
    assert player.chart_bars("1Min", 10, asof=start + 17) == bars
    completed = player.chart_bars("1Min", 10, asof=start + 60)
    assert completed[0]["h"] == 99 and completed[0]["v"] == 900
    assert "partial" not in completed[0]


def test_a_capture_without_prints_draws_no_candles(monkeypatch):
    start = prepare_capture(monkeypatch)
    monkeypatch.setattr(player.snapshot(), "prints", [])
    monkeypatch.setattr(player.snapshot(), "print_keys", [])
    assert player.chart_bars("1Min", 10, asof=start + 59) == []
    assert player.chart_bars("1Min", 10, asof=start + 60) == []


def test_stored_bar_files_are_never_drawn(tmp_path, monkeypatch):
    """#535: a recording made before candles took only price-setting prints stored wicks no trade made."""
    from capture.recorder import capture_root

    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(tmp_path))
    root = capture_root() / "2026-09-18" / "IMCC"
    root.mkdir(parents=True)
    start = stamp("2026-09-18T13:31:00+00:00")
    manifest = {"schema_version": 1, "symbol": "IMCC", "source": "ibkr", "status": "complete"}
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    rows = [dict(symbol="IMCC", ts=start + sec, price=px, size=100, conditions=cond)
            for sec, px, cond in [(1, 15.50, ""), (2, 13.19, "4 W"), (3, 15.43, "F"), (4, 15.60, "I")]]
    (root / "prints.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    wick = dict(symbol="IMCC", ts=start, open=15.50, high=15.60, low=13.19, close=15.60, volume=400)
    for name in ("bars_10s", "bars_1m", "bars_5m"):
        (root / f"{name}.jsonl").write_text(json.dumps(wick) + "\n", encoding="utf-8")
    try:
        assert player.load("2026-09-18", "IMCC")["ok"]
        for tf in ("1Min", "5Min", "15Min"):
            closed = player.chart_bars(tf, 10, asof=start + 3600)
            assert [(b["o"], b["h"], b["l"], b["c"], b["v"]) for b in closed] == [(15.50, 15.50, 15.43, 15.43, 200)]
    finally:
        player.reset_for_tests()


def test_print_only_capture_keeps_closed_bars_without_exposing_future_prints(monkeypatch):
    start = prepare_capture(monkeypatch)
    early = player.chart_bars("1Min", 10, asof=start + 5)
    assert early[0]["h"] == 12 and early[0]["v"] == 13
    closed = player.chart_bars("1Min", 10, asof=start + 60)
    assert len(closed) == 1 and closed[0]["v"] == 900
    assert "partial" not in closed[0]
    assert player.chart_bars("1Min", 10, asof=start + 5) == early


def test_missing_real_history_never_falls_back_to_current_broker(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Replay must not request unrestricted current broker history")
    monkeypatch.setattr(chart_bars, "_schedule_ibkr_fill", forbidden)
    monkeypatch.setattr(chart_bars, "_store_read", forbidden)
    assert fetch()["bars"] == []


def test_live_chart_path_unchanged(monkeypatch):
    mode.set_sim_mode(False)
    payload = dict(bars=[candle("2026-09-18T20:00:00Z")])
    monkeypatch.setattr(chart_bars, "_store_read", lambda *args: payload)
    monkeypatch.setattr(chart_bars._ibkr_client, "is_ready", lambda: False)
    assert fetch()["bars"] == payload["bars"]


# --- D-056 helpers ----------------------------------------------------------


def test_penny_bar_rounds_half_up_not_bankers():
    from sim.chart_replay import penny_bar

    # Python's round() is banker's: round(0.125, 2) == 0.12. IBKR is half-up.
    bar = penny_bar(dict(ts=0, open=10.125, high=10.125, low=10.125, close=10.135, volume=1))
    assert bar["open"] == 10.13 and bar["close"] == 10.14
    assert bar["high"] == 10.13  # ceil
    assert bar["low"] == 10.12   # floor


def test_penny_bar_leaves_exact_cents_alone():
    from sim.chart_replay import penny_bar

    bar = penny_bar(dict(ts=0, open=763.30, high=763.31, low=762.81, close=762.82, volume=5))
    assert (bar["open"], bar["high"], bar["low"], bar["close"]) == (763.30, 763.31, 762.81, 762.82)


def test_fill_flat_buckets_spans_gaps_and_sorts():
    from sim.chart_replay import fill_flat_buckets

    given = [dict(ts=180, open=2, high=2, low=2, close=2, volume=4),
             dict(ts=0, open=1, high=1, low=1, close=9, volume=3)]
    filled = fill_flat_buckets(given, 60)
    assert [row["ts"] for row in filled] == [0, 60, 120, 180]
    assert [row["volume"] for row in filled] == [3, 0.0, 0.0, 4]
    assert all(row["close"] == 9 for row in filled[1:3])  # carried prior close


def test_fill_flat_buckets_is_a_noop_without_a_gap():
    from sim.chart_replay import fill_flat_buckets

    given = [dict(ts=0, open=1, high=1, low=1, close=1, volume=1),
             dict(ts=60, open=1, high=1, low=1, close=1, volume=1)]
    assert fill_flat_buckets(given, 60) == given
    assert fill_flat_buckets([], 60) == []


def test_extend_flat_tail_stops_at_the_last_closed_interval():
    from sim.chart_replay import extend_flat_tail

    given = [dict(ts=0, open=1, high=1, low=1, close=7, volume=2)]
    assert [row["ts"] for row in extend_flat_tail(given, 60, through=180)] == [0, 60, 120]
    assert extend_flat_tail(given, 60, through=59) == given
    assert extend_flat_tail([], 60, through=600) == []
