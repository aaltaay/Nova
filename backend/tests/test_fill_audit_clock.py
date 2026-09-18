"""Timezone-shaped fill-clock guard -- fixtures only. No live IBKR."""
from __future__ import annotations

from execution.fill_audit_clock import (
    apply_fill_clock_guard,
    ny_offset_ms,
    timezone_shaped_residual_ms,
)


def test_ny_offset_ms_edt_is_four_hours():
    assert ny_offset_ms("2026-09-18T14:06:06.963023Z") == 14_400_000


def test_ny_offset_ms_est_is_five_hours():
    assert ny_offset_ms("2026-01-15T15:00:00.000Z") == 18_000_000


def test_imcc_sell_pair_is_timezone_shaped():
    residual = timezone_shaped_residual_ms(
        14_403_037,
        -1,
        "2026-09-18T14:06:06.963023Z",
    )
    assert residual == 3037


def test_imcc_buy_slightly_under_offset_is_timezone_shaped():
    residual = timezone_shaped_residual_ms(
        14_399_704,
        -1,
        "2026-09-18T14:06:10.296Z",
    )
    assert residual == -296


def test_mkt_timezone_shaped_corrects_to_residual():
    fill, reason = apply_fill_clock_guard(
        place_to_fill_ms=14_403_037,
        place_to_submit_ms=-1,
        placed_iso="2026-09-18T14:06:06.963023Z",
        order_type="MKT",
    )
    assert reason is None
    assert fill == 3037


def test_mkt_buy_under_offset_is_clock_skew_not_zero():
    """TZ residual -296 is clock skew -- do not invent a 0ms fill."""
    fill, reason = apply_fill_clock_guard(
        place_to_fill_ms=14_399_704,
        place_to_submit_ms=-1,
        placed_iso="2026-09-18T14:06:10.296Z",
        order_type="MKT",
    )
    assert fill == -296
    assert reason == "clock_skew"


def test_imcc_buy_whole_second_stamps_are_clock_skew():
    """BUY 106411: IBKR submitted/filled share 14:05:58; Nova is 296ms later."""
    from execution.fill_audit_clock import is_clock_skew_ms

    fill, reason = apply_fill_clock_guard(
        place_to_fill_ms=-296,
        place_to_submit_ms=-296,
        placed_iso="2026-09-18T14:05:58.296Z",
        order_type="MKT",
    )
    assert fill == -296
    assert reason == "clock_skew"
    assert is_clock_skew_ms(-296) is True
    assert is_clock_skew_ms(3037) is False
    assert is_clock_skew_ms(0) is False


def test_lmt_timezone_shaped_is_refused():
    fill, reason = apply_fill_clock_guard(
        place_to_fill_ms=14_403_037,
        place_to_submit_ms=-1,
        placed_iso="2026-09-18T14:06:06.963023Z",
        order_type="LMT",
    )
    assert fill is None
    assert reason == "timezone_shaped_clock"


def test_mkt_three_hour_same_second_is_impossible():
    fill, reason = apply_fill_clock_guard(
        place_to_fill_ms=10_800_000,
        place_to_submit_ms=12,
        placed_iso="2026-09-18T14:06:06.000Z",
        order_type="MKT",
    )
    assert fill is None
    assert reason == "impossible_fill_clock"


def test_real_three_second_mkt_is_unchanged():
    fill, reason = apply_fill_clock_guard(
        place_to_fill_ms=180,
        place_to_submit_ms=12,
        placed_iso="2026-09-16T14:05:00.000Z",
        order_type="MKT",
    )
    assert reason is None
    assert fill == 180


def test_est_shaped_mkt_corrects():
    fill, reason = apply_fill_clock_guard(
        place_to_fill_ms=18_003_000,
        place_to_submit_ms=1,
        placed_iso="2026-01-15T15:00:00.000Z",
        order_type="MKT",
    )
    assert reason is None
    assert fill == 3000
