"""Order-outcome honesty -- fixtures + CI tripwires. No live IBKR."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from constants import (
    IBKR_ERROR_NO_OPENING_TRADES,
    IBKR_ERROR_OUTSIDE_RTH_IGNORED,
)
from execution.order_outcome import (
    assert_outcome_honest,
    is_soft_warning,
    latest_hard_error,
    reduce_order_events,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "order_outcome"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_2109_is_soft_warning():
    assert is_soft_warning(IBKR_ERROR_OUTSIDE_RTH_IGNORED) is True
    assert is_soft_warning(201) is False
    assert is_soft_warning(None) is False


def test_latest_hard_error_skips_2109_then_keeps_201():
    code, msg = latest_hard_error((
        (2109, "outsideRth ignored"),
        (201, "No Opening Trades: Small Cap"),
    ))
    assert code == IBKR_ERROR_NO_OPENING_TRADES
    assert msg is not None and "Small Cap" in msg


def test_latest_hard_error_none_when_only_2109():
    code, msg = latest_hard_error(((2109, "outsideRth ignored"),))
    assert code is None
    assert msg is None


def test_spcx_success_2109_then_fill_is_not_a_reject():
    fixture = _load("spcx_success.json")
    out = reduce_order_events(
        fixture["events"],
        limit_price=fixture.get("limit_price"),
    )
    assert_outcome_honest(out)
    assert out.verdict == "filled"
    assert out.open_reject_modal is False
    assert out.hard_error_code is None
    assert out.filled_qty == 1.0
    assert out.avg_fill_price == pytest.approx(150.48)
    assert out.filled_at == "2026-09-16T14:05:12.100Z"
    assert out.commission == pytest.approx(1.000003)
    assert "rejected" not in (out.hard_error_message or "").lower()


def test_ztg_fail_uses_201_not_2109_and_never_invents_a_fill():
    fixture = _load("ztg_fail.json")
    out = reduce_order_events(
        fixture["events"],
        limit_price=fixture.get("limit_price"),
        stop_price=fixture.get("stop_price"),
    )
    assert_outcome_honest(out)
    assert out.verdict == "rejected"
    assert out.display_failed is True
    assert out.open_reject_modal is True
    assert out.hard_error_code == IBKR_ERROR_NO_OPENING_TRADES
    assert out.hard_error_message is not None
    assert "Small Cap" in out.hard_error_message
    assert "2109" not in out.hard_error_message
    assert out.filled_qty == 0.0
    assert out.avg_fill_price is None
    assert out.filled_at is None
    assert out.commission is None


def test_ci_fails_if_failed_plus_filled_is_constructed():
    from execution.order_outcome import OrderOutcome

    lie = OrderOutcome(
        verdict="rejected",
        ib_status="Inactive",
        filled_qty=1.0,
        avg_fill_price=1.76,
        filled_at=None,
        hard_error_code=201,
        hard_error_message="Error 201",
        open_reject_modal=True,
        commission=None,
        status_history=("PendingSubmit", "Inactive"),
    )
    with pytest.raises(AssertionError, match="Failed\\+Filled"):
        assert_outcome_honest(lie)


def test_ci_fails_if_reject_modal_opens_on_2109_alone():
    from execution.order_outcome import OrderOutcome

    lie = OrderOutcome(
        verdict="rejected",
        ib_status="PreSubmitted",
        filled_qty=0.0,
        avg_fill_price=None,
        filled_at=None,
        hard_error_code=2109,
        hard_error_message="Warning 2109",
        open_reject_modal=True,
        commission=None,
        status_history=("PendingSubmit", "PreSubmitted"),
    )
    with pytest.raises(AssertionError, match="soft warning"):
        assert_outcome_honest(lie)


def test_status_filled_without_exec_is_not_a_fill():
    out = reduce_order_events((
        {"kind": "status", "status": "PendingSubmit"},
        {"kind": "status", "status": "Filled", "filled": 1, "avg_fill": 1.76},
    ), limit_price=1.76)
    assert_outcome_honest(out)
    assert out.verdict != "filled"
    assert out.filled_qty == 0.0
    assert out.avg_fill_price is None
