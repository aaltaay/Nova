"""Synthetic overnight window -- same shape as the AEMD 2026-08-28 soak."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vwap_probe import (
    interpolation_pair,
    paint_latest_day,
    segmented_session_vwap,
    session_vwap,
    RTH_END,
    RTH_START,
    EXT_START,
)


def _bar(iso: str, price: float, volume: float) -> dict:
    return {"t": iso, "o": price, "h": price + 0.1, "l": price - 0.1, "c": price, "v": volume}


def _aemd_shaped() -> list[dict]:
    return [
        _bar("2026-08-27T19:59:00Z", 2.18, 1_495),   # 15:59 ET
        _bar("2026-08-27T20:00:00Z", 2.26, 2_271),   # 16:00 ET
        _bar("2026-08-28T01:50:00Z", 3.20, 0),       # 21:50 ET
        _bar("2026-08-28T03:59:00Z", 3.23, 0),       # 23:59 ET
        _bar("2026-08-28T08:00:00Z", 3.23, 10_000),  # 04:00 ET
        _bar("2026-08-28T11:00:00Z", 3.82, 377_534), # 07:00 ET
        _bar("2026-08-28T13:29:00Z", 2.90, 85_297),  # 09:29 ET
        _bar("2026-08-28T13:30:00Z", 2.95, 260_670), # 09:30 ET
        _bar("2026-08-28T13:31:00Z", 2.97, 50_000),  # 09:31 ET
    ]


def test_rth_ignores_premarket_and_resets_at_open():
    points = session_vwap(_aemd_shaped(), RTH_START, RTH_END)
    today = [p for p in points if p["day"] == "2026-08-28"]
    assert today[0]["t"].startswith("2026-08-28 09:30")
    assert today[0]["value"] == today[0]["close"] or abs(today[0]["value"] - 2.95) < 0.2


def test_overnight_pair_would_interpolate():
    points = session_vwap(_aemd_shaped(), RTH_START, RTH_END)
    pair = interpolation_pair(points)
    assert pair is not None
    assert pair["would_interpolate"] is True
    assert pair["gap_min"] > 500


def test_latest_day_paint_starts_at_premarket():
    points = session_vwap(_aemd_shaped(), EXT_START, RTH_END)
    painted = paint_latest_day(points, "2026-08-28")
    assert painted[0]["t"].startswith("2026-08-28 04:00")
    assert all(p["day"] == "2026-08-28" for p in painted)


def test_extended_includes_premarket_volume():
    bars = _aemd_shaped()
    rth = session_vwap(bars, RTH_START, RTH_END)
    ext = session_vwap(bars, EXT_START, RTH_END)
    today_rth = [p for p in rth if p["day"] == "2026-08-28"]
    today_ext = [p for p in ext if p["day"] == "2026-08-28"]
    assert today_ext[0]["t"].startswith("2026-08-28 04:00")
    assert today_ext[-1]["value"] != today_rth[-1]["value"]


def test_afterhours_resets_instead_of_blending():
    bars = [
        _bar("2026-08-27T13:30:00Z", 10.0, 1_000),   # 09:30 ET
        _bar("2026-08-27T19:59:00Z", 10.0, 1_000),   # 15:59 ET
        _bar("2026-08-27T20:00:00Z", 500.0, 5_000_000),  # 16:00 ET
        _bar("2026-08-27T23:59:00Z", 500.0, 5_000_000),  # 19:59 ET
    ]
    painted = paint_latest_day(segmented_session_vwap(bars), "2026-08-27")
    assert painted[1]["value"] == 10.0
    assert abs(painted[-1]["value"] - 500.0) < 1.0
    assert painted[-1]["value"] != painted[1]["value"]
