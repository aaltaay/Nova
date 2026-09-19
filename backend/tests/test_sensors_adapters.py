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
    body = desk.read_halt("AAPL")
    assert body["status"] == "live"
    assert body["data"]["halted"] is False


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
