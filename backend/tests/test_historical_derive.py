"""1Min -> coarser timeframe derivation."""
from __future__ import annotations

from ibkr.historical_derive import derive_from_1min


def test_five_min_aggregates_ohlcv():
    bars = [
        {"t": "2026-08-18T14:00:00Z", "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 10},
        {"t": "2026-08-18T14:01:00Z", "o": 1.5, "h": 3.0, "l": 1.0, "c": 2.0, "v": 20},
        {"t": "2026-08-18T14:06:00Z", "o": 2.0, "h": 2.2, "l": 1.8, "c": 2.1, "v": 5},
    ]
    out = derive_from_1min(bars, "5Min")
    assert len(out) == 2
    first = out[0]
    assert first["o"] == 1.0
    assert first["h"] == 3.0
    assert first["l"] == 0.5
    assert first["c"] == 2.0
    assert first["v"] == 30
    assert out[1]["o"] == 2.0
    assert out[1]["v"] == 5


def test_unknown_target_is_empty():
    assert derive_from_1min(
        [{"t": "2026-08-18T14:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}],
        "1Day",
    ) == []
