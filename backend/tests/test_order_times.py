"""Unit tests for IBKR order timestamp extraction."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from ibkr.order_times import _to_iso, extract_trade_times


def test_to_iso_naive_datetime_assumes_eastern():
    dt = datetime(2026, 7, 18, 9, 41, 23)
    iso = _to_iso(dt)
    assert iso is not None
    # 09:41 ET in July is UTC-4 → 13:41 UTC
    assert iso.startswith("2026-07-18T13:41:23")


def test_to_iso_ib_compact_string():
    iso = _to_iso("20260718  09:41:23")
    assert iso is not None
    assert "2026-07-18T13:41:23" in iso


def test_extract_trade_times_prefers_last_fill():
    et = ZoneInfo("America/New_York")
    trade = SimpleNamespace(
        log=[
            SimpleNamespace(time=datetime(2026, 7, 18, 9, 30, 0, tzinfo=et)),
            SimpleNamespace(time=datetime(2026, 7, 18, 9, 40, 0, tzinfo=et)),
        ],
        fills=[
            SimpleNamespace(
                execution=SimpleNamespace(
                    time=datetime(2026, 7, 18, 9, 35, 0, tzinfo=et),
                ),
            ),
            SimpleNamespace(
                execution=SimpleNamespace(
                    time=datetime(2026, 7, 18, 9, 41, 23, tzinfo=et),
                ),
            ),
        ],
    )
    submitted, updated = extract_trade_times(trade)
    assert submitted is not None and submitted.startswith("2026-07-18T13:30:00")
    assert updated is not None and updated.startswith("2026-07-18T13:41:23")
