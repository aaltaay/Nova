"""Pure sensor indicator math -- no I/O."""
from __future__ import annotations

from sensors.math_indicators import ema_series, last_ema, macd_from_closes, session_vwap, slope_last
from sensors.session_phase import classify_phase


def _bars(closes: list[float]) -> list[dict]:
    return [
        {"t": 1_700_000_000 + i * 60, "o": c, "h": c + 0.1, "l": c - 0.1, "c": c, "v": 100}
        for i, c in enumerate(closes)
    ]


def test_ema_ready_after_period():
    series = ema_series([1, 2, 3, 4, 5], 3)
    assert series[0] is None
    assert series[1] is None
    assert series[2] is not None
    row = last_ema(_bars([1, 2, 3, 4, 5, 6, 7, 8, 9]), 9)
    assert row["ready"] is True
    assert row["value"] is not None


def test_macd_needs_slow_plus_signal():
    closes = [float(i) for i in range(1, 40)]
    out = macd_from_closes(closes, 12, 26, 9)
    assert out["ready"] is True
    assert out["macd"] is not None
    assert out["signal"] is not None
    assert out["histogram"] == round(out["macd"] - out["signal"], 6)


def test_vwap_volume_weighted():
    bars = [
        {"t": 1, "o": 10, "h": 10, "l": 10, "c": 10, "v": 100},
        {"t": 2, "o": 20, "h": 20, "l": 20, "c": 20, "v": 300},
    ]
    stats = session_vwap(bars)
    assert stats["vwap"] == 17.5
    assert stats["distance"] == 2.5


def test_slope_positive_on_up_series():
    assert slope_last([1.0, 2.0, 3.0, 4.0, 5.0], 5) > 0


def test_session_phase_clock_buckets():
    assert classify_phase(4 * 60) == "pre-market"
    assert classify_phase(9 * 60 + 30) == "open auction"
    assert classify_phase(10 * 60) == "morning momentum"
    assert classify_phase(12 * 60) == "midday chop"
    assert classify_phase(15 * 60) == "power hour"
    assert classify_phase(16 * 60) == "after-hours"
    assert classify_phase(21 * 60) == "closed"
