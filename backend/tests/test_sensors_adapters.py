"""Live adapters with mocked feeds -- no invented trip levels."""
from __future__ import annotations

from sensors.adapters import bars, bookish, desk, tapeish, volume
from sensors import rings


def setup_function() -> None:
    rings.reset_for_tests()


def test_l2_uses_existing_imbalance(monkeypatch):
    book = {
        "bids": [{"price": 10.00, "size": 900, "mm": "A"}],
        "asks": [{"price": 10.02, "size": 100, "mm": "B"}],
        "l1_fallback": False,
    }
    monkeypatch.setattr("sensors.adapters.bookish.get_book", lambda symbol: (book, "ibkr_depth"))
    rings.observe_book("AAPL", book)
    body = bookish.read_l2("AAPL")
    assert body["status"] == "live"
    assert body["data"]["imbalance"] == 0.8
    assert body["data"]["spread_ticks"] == 2.0
    assert len(body["data"]["bids"]) == 1


def test_tape_clusters_and_timing(monkeypatch):
    prints = [
        {"type": "print", "time": "2026-09-19T14:00:00+00:00", "price": 10.0, "size": 100, "side": "ask"},
        {"type": "print", "time": "2026-09-19T14:00:01+00:00", "price": 10.01, "size": 100, "side": "ask"},
        {"type": "print", "time": "2026-09-19T14:00:03+00:00", "price": 10.02, "size": 400, "side": "bid"},
    ]
    monkeypatch.setattr("sensors.adapters.tapeish.get_prints", lambda symbol, limit=20: (prints, "ibkr_tape"))
    body = tapeish.read_tape("AAPL")
    assert body["data"]["print_count"] == 3
    assert body["data"]["size_clustering"]["repeat_size"] == 100
    assert body["data"]["timing"]["median_gap_sec"] is not None


def test_vwap_macd_emas_from_bars(monkeypatch):
    bars_1m = [
        {"t": 1_700_000_000 + i * 60, "o": 10 + i * 0.01, "h": 10.1 + i * 0.01, "l": 9.9, "c": 10 + i * 0.01, "v": 200}
        for i in range(40)
    ]
    monkeypatch.setattr("sensors.adapters.bars.get_bars", lambda symbol, timeframe="1Min", limit=240: (bars_1m, "bars_store"))
    vwap = bars.read_vwap("AAPL")
    assert vwap["data"]["vwap"] is not None
    macd = bars.read_macd("AAPL")
    assert macd["data"]["ready"] is True
    emas = bars.read_emas("AAPL")
    assert emas["data"]["ema_9"]["ready"] is True
    assert emas["data"]["ema_200"]["ready"] is False
    # Each reading names its newest bar, so a week-old set is never read as live (QA W16).
    newest = float(bars_1m[-1]["t"])
    assert vwap["data"]["bars_as_of"] == newest
    assert macd["data"]["bars_as_of"] == newest
    assert emas["data"]["bars_as_of"] == newest


def test_vwap_is_the_sessions_from_four_am(monkeypatch):
    # ADR 035: the newest 240 stored bars straddled two sessions; the VWAP is the newest session's from 04:00 ET.
    from datetime import datetime
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    y = datetime(2026, 9, 23, 15, 0, tzinfo=et).timestamp()     # yesterday afternoon at 20.00
    t = datetime(2026, 9, 24, 4, 0, tzinfo=et).timestamp()      # today from 04:00 at 5.00
    old = [{"t": y + i * 60, "o": 20.0, "h": 20.0, "l": 20.0, "c": 20.0, "v": 10_000} for i in range(60)]
    new = [{"t": t + i * 60, "o": 5.0, "h": 5.0, "l": 5.0, "c": 5.0, "v": 1_000} for i in range(30)]
    monkeypatch.setattr("sensors.adapters.bars.get_bars", lambda symbol, timeframe="1Min", limit=240: (old + new, "bars_store"))
    body = bars.read_vwap("APUS")
    assert body["data"]["vwap"] == 5.0 and body["data"]["anchor"] == "04:00 ET"


def test_rvol_marks_missing_20d(monkeypatch):
    monkeypatch.setattr("sensors.adapters.volume.get_quote", lambda symbol: ({"volume": 1_000_000, "price": 4.2}, "ibkr_l1"))
    monkeypatch.setattr("sensors.adapters.volume.peek_avg_volume", lambda symbol: 2_000_000.0)
    monkeypatch.setattr("hod_momo_market.peek_rvol_5min", lambda symbol: 1.5, raising=False)
    body = volume.read_rvol("AAPL")
    assert body["data"]["tod_20d"] is None
    assert "20-day" in body["data"]["note"]
    assert body["data"]["rvol_vs_adv_pace"] is not None


def test_halt_not_halted(monkeypatch):
    monkeypatch.setattr("ibkr.halt_status.snapshot", lambda symbol, now=None: None)
    monkeypatch.setattr("ibkr.halt_status.halted_now", lambda symbols, now=None: {"AAPL": False})
    body = desk.read_halt("AAPL")
    assert body["status"] == "live"
    assert body["data"]["halted"] is False


def test_halt_unknown_is_not_read_as_not_halted(monkeypatch):
    # ADR 035: no open halt on record and no source that says it trades is unknown, never False.
    monkeypatch.setattr("ibkr.halt_status.snapshot", lambda symbol, now=None: None)
    monkeypatch.setattr("ibkr.halt_status.halted_now", lambda symbols, now=None: {"AAPL": None})
    body = desk.read_halt("AAPL")
    assert body["data"]["halted"] is None
    assert "Unknown" in body["data"]["note"]


def test_halt_from_existing_snapshot(monkeypatch):
    monkeypatch.setattr(
        "ibkr.halt_status.snapshot",
        lambda symbol, now=None: {
            "kind": "LULD",
            "halt_code": 2,
            "halt_start": 1_700_000_000,
            "reason": "LULD pause",
            "rule": "LULD",
            "source": "ibkr_ticker_halted",
            "start_late": False,
            "exchange": {},
        },
    )
    body = desk.read_halt("ABCD")
    assert body["data"]["halted"] is True
    assert body["data"]["kind"] == "LULD"
    assert body["data"]["elapsed_sec"] is not None


def test_spread_marks_widening(monkeypatch):
    tight = {
        "bids": [{"price": 10.00, "size": 100}],
        "asks": [{"price": 10.01, "size": 100}],
    }
    wide = {
        "bids": [{"price": 10.00, "size": 100}],
        "asks": [{"price": 10.05, "size": 100}],
    }
    rings.observe_book("AAPL", tight)
    monkeypatch.setattr("sensors.adapters.bookish.get_book", lambda symbol: (wide, "ibkr_depth"))
    rings.observe_book("AAPL", wide)
    body = bookish.read_spread("AAPL")
    assert body["data"]["direction"] == "widening"
    assert body["data"]["spread_ticks"] == 5.0


def test_flow_flags_same_side_sweep(monkeypatch):
    prints = [
        {"time": "2026-09-19T14:00:00+00:00", "price": 10.0, "size": 200, "side": "ask"},
        {"time": "2026-09-19T14:00:01+00:00", "price": 10.01, "size": 200, "side": "ask"},
        {"time": "2026-09-19T14:00:02+00:00", "price": 10.02, "size": 200, "side": "ask"},
    ]
    monkeypatch.setattr("sensors.adapters.bookish.get_prints", lambda symbol, limit=20: (prints, "ibkr_tape"))
    monkeypatch.setattr("sensors.adapters.bookish.get_book", lambda symbol: (None, None))
    body = bookish.read_flow("AAPL")
    assert body["data"]["sweep"] == {"side": "ask", "prints": 3}


def test_last_move_uses_median_range(monkeypatch):
    bars_1m = [
        {"t": 1_700_000_000 + i * 60, "o": 10, "h": 10.02, "l": 9.99, "c": 10, "v": 10}
        for i in range(19)
    ]
    bars_1m.append({"t": 1_700_001_140, "o": 10, "h": 10.50, "l": 9.50, "c": 10.2, "v": 50})
    monkeypatch.setattr("sensors.adapters.tapeish.get_bars", lambda symbol, timeframe="1Min", limit=240: (bars_1m, "bars_store"))
    body = tapeish.read_last_move("AAPL")
    assert body["data"]["bar"]["h"] == 10.50
    assert body["data"]["median_range"] is not None
    assert body["data"]["bars_as_of"] == 1_700_001_140.0


def test_liquidity_does_not_invent_typical_spread(monkeypatch):
    monkeypatch.setattr("sensors.adapters.bookish.peek_avg_volume", lambda symbol: 1_000_000.0)
    monkeypatch.setattr("sensors.adapters.bookish.get_book", lambda symbol: (None, None))
    monkeypatch.setattr("sensors.adapters.bookish.get_quote", lambda symbol: ({"price": 4.2}, "ibkr_l1"))
    body = bookish.read_liquidity("AAPL")
    assert body["data"]["adv"] == 1_000_000.0
    assert body["data"]["typical_spread_dollars"] is None
    assert "no historical" in body["data"]["typical_spread_note"].lower()


def test_day_volume_loud_when_missing(monkeypatch):
    monkeypatch.setattr("sensors.adapters.volume.get_quote", lambda symbol: (None, None))
    body = volume.read_day_volume("AAPL")
    assert body["error"]
    assert body["data"]["day_volume"] is None


def test_regime_trending_from_up_closes(monkeypatch):
    bars_1m = [
        {"t": 1_700_000_000 + i * 60, "o": 10 + i, "h": 10 + i, "l": 10 + i, "c": 10 + i, "v": 10}
        for i in range(20)
    ]
    monkeypatch.setattr("sensors.adapters.stubs.get_bars", lambda symbol, timeframe="1Min", limit=20: (bars_1m, "bars_store"))
    monkeypatch.setattr("sensors.adapters.stubs.get_prints", lambda symbol, limit=20: ([], None))
    monkeypatch.setattr("sensors.adapters.stubs.get_book", lambda symbol: (None, None))
    from sensors.adapters import stubs

    body = stubs.read_regime("AAPL")
    assert body["status"] == "computed_stub"
    assert body["data"]["regime"] == "trending"
