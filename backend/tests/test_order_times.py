"""Unit tests for IBKR order timestamp extraction + Nova place stamps."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from ibkr.order_times import (
    _to_iso,
    clear_nova_placed_for_tests,
    extract_trade_times,
    remember_nova_placed,
    resolve_submitted_at,
    wall_utc_now_iso,
)


def setup_function() -> None:
    clear_nova_placed_for_tests()


def test_to_iso_naive_datetime_assumes_eastern():
    dt = datetime(2026, 7, 18, 9, 41, 23)
    iso = _to_iso(dt)
    assert iso is not None
    # 09:41 ET in July is UTC-4 → 13:41 UTC
    assert iso.startswith("2026-07-18T13:41:23")
    assert iso.endswith("Z")


def test_to_iso_preserves_microseconds():
    et = ZoneInfo("America/New_York")
    dt = datetime(2026, 7, 18, 9, 41, 23, 456789, tzinfo=et)
    iso = _to_iso(dt)
    assert iso is not None
    assert "456789" in iso or "456" in iso


def test_to_iso_ib_compact_string():
    iso = _to_iso("20260718  09:41:23")
    assert iso is not None
    assert "2026-07-18T13:41:23" in iso


def test_to_iso_ib_compact_with_fraction():
    iso = _to_iso("20260718 09:41:23.123456")
    assert iso is not None
    assert iso.startswith("2026-07-18T13:41:23")
    assert "123" in iso


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
    submitted, updated, filled_at = extract_trade_times(trade)
    assert submitted is not None and submitted.startswith("2026-07-18T13:30:00")
    assert updated is not None and updated.startswith("2026-07-18T13:41:23")
    assert filled_at is not None and filled_at.startswith("2026-07-18T13:41:23")


def test_extract_trade_times_filled_at_none_when_no_fills():
    et = ZoneInfo("America/New_York")
    trade = SimpleNamespace(
        log=[
            SimpleNamespace(time=datetime(2026, 7, 18, 9, 30, 0, tzinfo=et)),
            SimpleNamespace(time=datetime(2026, 7, 18, 9, 32, 0, tzinfo=et)),
        ],
        fills=[],
    )
    submitted, updated, filled_at = extract_trade_times(trade)
    assert submitted is not None and submitted.startswith("2026-07-18T13:30:00")
    # updated_at still falls back to last log time (cancel) when there are no fills.
    assert updated is not None and updated.startswith("2026-07-18T13:32:00")
    assert filled_at is None


def test_wall_utc_now_iso_is_zulu():
    iso = wall_utc_now_iso()
    assert iso.endswith("Z")
    assert "T" in iso


def test_resolve_submitted_prefers_broker_over_nova():
    remember_nova_placed(42, "2026-07-18T12:00:00.000000Z")
    assert (
        resolve_submitted_at("2026-07-18T13:00:00.000000Z", 42)
        == "2026-07-18T13:00:00.000000Z"
    )


def test_resolve_submitted_falls_back_to_nova_stamp():
    stamp = remember_nova_placed(99)
    assert resolve_submitted_at(None, 99) == stamp
    # First stamp wins — later calls must not overwrite.
    assert remember_nova_placed(99, "2026-07-18T23:59:59.000000Z") == stamp
