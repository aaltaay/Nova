"""Unit tests for IBKR order timestamp extraction + Nova place stamps."""

from __future__ import annotations

from datetime import datetime, timezone
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


def test_to_iso_naive_datetime_is_utc():
    dt = datetime(2026, 7, 18, 9, 41, 23)
    iso = _to_iso(dt)
    assert iso is not None
    # IBKR Execution.time digits are UTC -- do not attach Eastern.
    assert iso.startswith("2026-07-18T09:41:23")
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
    assert "2026-07-18T09:41:23" in iso


def test_to_iso_ib_compact_with_fraction():
    iso = _to_iso("20260718 09:41:23.123456")
    assert iso is not None
    assert iso.startswith("2026-07-18T09:41:23")
    assert "123" in iso


def test_to_iso_ib_dash_compact_is_utc():
    iso = _to_iso("20260918-14:06:10")
    assert iso == "2026-09-18T14:06:10Z"


def test_extract_ny_labeled_execution_keeps_utc_wall_digits():
    """ib_async may attach America/New_York to UTC execution.time digits."""
    et = ZoneInfo("America/New_York")
    trade = SimpleNamespace(
        log=[
            SimpleNamespace(
                time=datetime(2026, 9, 18, 15, 2, 48, 551000, tzinfo=timezone.utc),
            ),
        ],
        fills=[
            SimpleNamespace(
                execution=SimpleNamespace(
                    time=datetime(2026, 9, 18, 15, 2, 48, tzinfo=et),
                ),
            ),
        ],
    )
    submitted, _updated, filled_at = extract_trade_times(trade)
    assert submitted is not None and submitted.startswith("2026-09-18T15:02:48")
    assert filled_at == "2026-09-18T15:02:48Z"
    assert not filled_at.startswith("2026-09-18T19:02:48")


def test_extract_ib_async_host_tz_converted_fill_rewritten():
    """naive.astimezone(UTC) on an Eastern host yields 19:02:48Z from 15:02:48."""
    et = ZoneInfo("America/New_York")
    converted = datetime(2026, 9, 18, 15, 2, 48, tzinfo=et).astimezone(timezone.utc)
    assert converted.hour == 19
    trade = SimpleNamespace(
        log=[
            SimpleNamespace(
                time=datetime(2026, 9, 18, 15, 2, 48, 551000, tzinfo=timezone.utc),
            ),
        ],
        fills=[
            SimpleNamespace(execution=SimpleNamespace(time=converted)),
        ],
    )
    submitted, _updated, filled_at = extract_trade_times(trade)
    assert submitted is not None and submitted.startswith("2026-09-18T15:02:48")
    assert filled_at is not None and filled_at.startswith("2026-09-18T15:02:48")
    assert not filled_at.startswith("2026-09-18T19:02:48")


def test_extract_naive_fill_stays_utc_against_utc_log():
    """IMCC-shaped: naive 14:06:10 fill must not become 18:06:10Z."""
    trade = SimpleNamespace(
        log=[SimpleNamespace(time=datetime(2026, 9, 18, 14, 6, 6, 962023, tzinfo=timezone.utc))],
        fills=[
            SimpleNamespace(
                execution=SimpleNamespace(time=datetime(2026, 9, 18, 14, 6, 10)),
            ),
        ],
    )
    submitted, _updated, filled_at = extract_trade_times(trade)
    assert submitted is not None and submitted.startswith("2026-09-18T14:06:06")
    assert filled_at is not None and filled_at.startswith("2026-09-18T14:06:10")
    assert not filled_at.startswith("2026-09-18T18:06:10")


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
                    time=datetime(2026, 7, 18, 13, 35, 0),
                ),
            ),
            SimpleNamespace(
                execution=SimpleNamespace(
                    time=datetime(2026, 7, 18, 13, 41, 23),
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
