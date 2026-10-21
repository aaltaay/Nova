"""What Ahead sends the forecaster (ADR 065): completed candles at the desk clock, the prior close from its owner
(never worked back from a percentage), and the contract's request body."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from ahead import inputs

ET = ZoneInfo("America/New_York")


def at(h: int, m: int, day: int = 21) -> float:
    return datetime(2026, 10, day, h, m, tzinfo=ET).timestamp()


def bar(t: float, c: float = 4.0, v: float = 100) -> dict:
    return {"t": t, "o": c, "h": c + 0.01, "l": c - 0.01, "c": c, "v": v}


def test_live_bars_drop_the_forming_minute_and_earlier_sessions(monkeypatch):
    import sensors.feeds as feeds

    stored = [bar(at(19, 58, day=20)), *(bar(at(9, m)) for m in range(0, 5))]
    monkeypatch.setattr(feeds, "get_bars", lambda sym, tf, limit: (stored, "bars_store"))
    out = inputs.session_bars("XYZ", at(9, 4) + 30, replay=False)     # 09:04 is still forming
    assert [b["t"] for b in out] == [at(9, m) for m in range(0, 4)]
    assert all(isinstance(b["v"], float) for b in out)


def test_replay_bars_come_from_the_replay_chart_at_the_playhead(monkeypatch):
    from stock_read import replay_read

    seen = {}

    def fake(sym, tf, limit, now):
        seen.update(sym=sym, tf=tf, limit=limit, now=now)
        return [{"t": at(9, 0), "o": 1, "h": 1, "l": 1, "c": 1, "v": 5, "partial": False}]

    monkeypatch.setattr(replay_read, "bars", fake)
    out = inputs.session_bars("XYZ", at(9, 3), replay=True)
    assert seen == {"sym": "XYZ", "tf": "1Min", "limit": 1000, "now": at(9, 3)}
    assert out == [{"t": at(9, 0), "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 5.0}]


def test_an_unreadable_candle_is_left_out_not_invented(monkeypatch, caplog):
    import sensors.feeds as feeds

    rows = [bar(at(9, 0)), {"t": at(9, 1), "o": None, "h": 1, "l": 1, "c": 1, "v": 1}, bar(at(9, 2))]
    monkeypatch.setattr(feeds, "get_bars", lambda sym, tf, limit: (rows, "bars_store"))
    out = inputs.session_bars("XYZ", at(9, 10), replay=False)
    assert [b["t"] for b in out] == [at(9, 0), at(9, 2)]
    assert "unreadable" in caplog.text


def test_the_desk_counts_as_a_replay_when_the_live_edge_is_unreadable(monkeypatch):
    import sim.mode
    from stock_read import replay_read

    def boom():
        raise RuntimeError("no clock")

    monkeypatch.setattr(sim.mode, "is_replay_desk", boom)
    monkeypatch.setattr(replay_read, "playhead", lambda: 1234.0)
    assert inputs.desk_now() == (1234.0, True)


def test_live_prior_close_is_the_board_rows_then_the_l1_lines(monkeypatch):
    import strategy.symbol_pillars as pillars

    monkeypatch.setattr(pillars, "raw_boards", lambda: {"gappers": [{"symbol": "XYZ", "prev_close": 3.1}]})
    monkeypatch.setattr(pillars, "live_quote", lambda sym: {"prev_close": 9.9})
    assert inputs.prior_close("XYZ", replay=False) == 3.1
    monkeypatch.setattr(pillars, "raw_boards", lambda: {})
    assert inputs.prior_close("XYZ", replay=False) == 9.9
    monkeypatch.setattr(pillars, "live_quote", lambda sym: {"prev_close": 0})
    assert inputs.prior_close("XYZ", replay=False) is None


def test_replay_prior_close_is_the_loaded_replays_own(monkeypatch):
    from sim import capture_player, history_playback

    monkeypatch.setattr(history_playback, "selected", lambda: SimpleNamespace(spec={"symbol": "XYZ"}, prev_close=2.5))
    assert inputs.prior_close("XYZ", replay=True) == 2.5
    monkeypatch.setattr(history_playback, "selected", lambda: None)
    monkeypatch.setattr(capture_player, "snapshot", lambda: SimpleNamespace(symbol="xyz", prev_close=1.75))
    assert inputs.prior_close("XYZ", replay=True) == 1.75
    assert inputs.prior_close("ABC", replay=True) is None              # another stock's replay says nothing


def test_an_unreadable_prior_close_is_unknown(monkeypatch, caplog):
    import strategy.symbol_pillars as pillars

    def boom():
        raise RuntimeError("store gone")

    monkeypatch.setattr(pillars, "raw_boards", boom)
    assert inputs.prior_close("XYZ", replay=False) is None
    assert "prior close of XYZ" in caplog.text


def test_contiguous_tail_counts_consecutive_minutes():
    assert inputs.contiguous_tail([]) == 0
    assert inputs.contiguous_tail([bar(at(9, 0))]) == 1
    assert inputs.contiguous_tail([bar(at(9, m)) for m in (0, 1, 3, 4, 5)]) == 3


def test_assert_causal_refuses_a_candle_ending_after_the_clock():
    bars = [bar(at(9, 0)), bar(at(9, 1))]
    inputs.assert_causal(bars, at(9, 2))
    with pytest.raises(ValueError):
        inputs.assert_causal(bars, at(9, 2) - 1)


def test_request_body_is_the_contracts():
    bars = [bar(at(9, 0), c=1.05, v=120000)]
    body = inputs.request_body("XYZ", bars, at(9, 1), None, "sim")
    assert body == {
        "symbol": "XYZ", "as_of": "2026-10-21T09:01:00-04:00", "horizon_min": 15, "prior_close": None,
        "venue": "sim",
        "bars": [{"t": "2026-10-21T09:00:00-04:00", "o": 1.05, "h": 1.06, "l": 1.04, "c": 1.05, "v": 120000}],
    }


def test_reset_pool_makes_new_read_threads():
    first = inputs._executor()
    inputs.reset_pool()
    second = inputs._executor()
    assert first is not second and second._thread_name_prefix == "ahead-read"
    inputs.reset_pool()
