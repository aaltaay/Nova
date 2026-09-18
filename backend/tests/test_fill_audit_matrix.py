"""Fill-latency fixture matrix -- Ahmed follow-up. No live IBKR."""
from __future__ import annotations

from execution.fill_audit import classify_fill_audit
from execution.fill_audit_attach import public_fill_audit
from execution.fill_audit_clock import apply_fill_clock_guard, coherent_face_ms


def test_matrix_a_honest_imcc_sell_3037_warn():
    row = classify_fill_audit(
        order_id=106416,
        symbol="IMCC",
        side="SELL",
        order_type="MKT",
        mode="paper",
        status="Filled",
        nova_placed_at="2026-09-18T14:06:06.963023Z",
        submitted_at="2026-09-18T14:06:06.962023Z",
        filled_at="2026-09-18T18:06:10Z",
        terminal_at="2026-09-18T18:06:10Z",
        has_fill=True,
        rth=True,
    )
    assert row["place_to_fill_ms"] == 3037
    assert row["face_ms"] == 3037
    assert row["level"] == "warn"
    assert row["reason"] == "mkt_rth_slow"
    pub = public_fill_audit(row)
    assert pub is not None
    assert pub["face_ms"] == 3037


def test_matrix_b_second_rounded_buy_is_clock_skew_not_zero():
    row = classify_fill_audit(
        order_id=106411,
        symbol="IMCC",
        side="BUY",
        order_type="MKT",
        mode="paper",
        status="Filled",
        nova_placed_at="2026-09-18T14:05:58.296Z",
        submitted_at="2026-09-18T14:05:58Z",
        filled_at="2026-09-18T14:05:58Z",
        terminal_at="2026-09-18T14:05:58Z",
        has_fill=True,
        rth=True,
    )
    assert row["place_to_fill_ms"] == -296
    assert row["face_ms"] is None
    assert row["reason"] == "clock_skew"
    assert row["level"] == "ok"
    assert row["face_ms"] != 0
    pub = public_fill_audit(row)
    assert pub is not None
    assert pub["face_ms"] is None
    assert pub["place_to_fill_ms"] == -296


def test_matrix_c_edt_shaped_mkt_corrects_lmt_blanks():
    mkt, mkt_reason = apply_fill_clock_guard(
        place_to_fill_ms=14_403_037,
        place_to_submit_ms=-1,
        placed_iso="2026-09-18T14:06:06.963023Z",
        order_type="MKT",
    )
    assert mkt_reason is None
    assert mkt == 3037
    assert coherent_face_ms(mkt, None, None) == 3037

    lmt, lmt_reason = apply_fill_clock_guard(
        place_to_fill_ms=14_403_037,
        place_to_submit_ms=-1,
        placed_iso="2026-09-18T14:06:06.963023Z",
        order_type="LMT",
    )
    assert lmt is None
    assert lmt_reason == "timezone_shaped_clock"
    assert coherent_face_ms(lmt, None, lmt_reason) is None


def test_matrix_d_missing_filled_at_has_no_face():
    row = classify_fill_audit(
        order_id=99,
        symbol="IMCC",
        side="BUY",
        order_type="MKT",
        mode="paper",
        status="Filled",
        nova_placed_at="2026-09-18T14:05:58.296Z",
        submitted_at="2026-09-18T14:05:58.400Z",
        filled_at=None,
        terminal_at=None,
        has_fill=False,
        rth=True,
        status_history=("PendingSubmit", "Filled"),
    )
    assert row.get("place_to_fill_ms") is None
    assert row["face_ms"] is None or row["face_ms"] != 0
    pub = public_fill_audit(
        {
            "place_to_submit_ms": 12,
            "place_to_fill_ms": None,
            "place_to_terminal_ms": None,
            "level": "ok",
            "reason": "filled",
        },
    )
    assert pub is None


def test_matrix_f_hour_skew_zero_residual_is_not_zero_ms():
    """109741-shaped: exact EDT offset must not publish face_ms=0."""
    fill, reason = apply_fill_clock_guard(
        place_to_fill_ms=14_400_000,
        place_to_submit_ms=551,
        placed_iso="2026-09-18T15:02:48.000Z",
        order_type="MKT",
    )
    assert fill is None
    assert reason == "timezone_shaped_clock"
    assert coherent_face_ms(0, None, "filled") is None
    pub = public_fill_audit(
        {
            "place_to_submit_ms": 551,
            "place_to_fill_ms": 14_400_000,
            "place_to_terminal_ms": None,
            "level": "ok",
            "reason": "filled",
            "type": "MKT",
        },
    )
    assert pub is not None
    assert pub["face_ms"] is None
    assert pub["face_ms"] != 0
    assert pub["place_to_fill_ms"] != 0


def test_matrix_e_never_clamps_negative_residual_to_zero():
    fill, reason = apply_fill_clock_guard(
        place_to_fill_ms=14_399_704,
        place_to_submit_ms=-1,
        placed_iso="2026-09-18T14:06:10.296Z",
        order_type="MKT",
    )
    assert fill == -296
    assert fill != 0
    assert reason == "clock_skew"
    assert coherent_face_ms(fill, None, reason) is None
