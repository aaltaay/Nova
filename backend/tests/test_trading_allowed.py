"""trading_allowed SSOT -- same gate as place, not a second lock."""
from __future__ import annotations

import pytest

from constants_bot import BOT_REASON_TRADING_LOCKED
from ibkr.trading_allowed import (
    evaluate_trading_allowed,
    require_places_allowed,
)


@pytest.fixture
def armed_desk():
    """ADR 018: the latch is off by default, so allow-path tests must arm."""
    from ibkr import safety as _safety

    _safety.set_armed(True, reason="test")
    try:
        yield
    finally:
        _safety.set_armed(False, reason="test")


def test_evaluate_allowed_when_assert_orders_ok(monkeypatch, armed_desk):
    monkeypatch.setattr(
        "ibkr.trading_allowed.assert_orders_allowed",
        lambda **_kw: (True, ""),
    )
    monkeypatch.setattr(
        "ibkr.trading_allowed.spend_state",
        lambda _kind: ("paper_armed", ""),
    )
    snap = evaluate_trading_allowed(
        client_enabled=True,
        connected=True,
        account_mode="paper",
        broker_account_kind="paper",
    )
    assert snap["trading_allowed"] is True
    assert snap["trading_allowed_reason"] is None
    assert snap["spend_status"] == "paper_armed"
    assert snap["armed"] is True


def test_evaluate_blocked_while_disarmed_even_when_env_permits(monkeypatch):
    """The env may permit spending; a fresh process still may not (ADR 018)."""
    # conftest arms by default for the legacy suite -- this test is about the
    # latch, so it takes the process back to its real process-start state.
    from ibkr import safety as _safety

    monkeypatch.setattr(_safety, "_armed", False)
    monkeypatch.setattr(
        "ibkr.trading_allowed.assert_orders_allowed",
        lambda **_kw: (True, ""),
    )
    monkeypatch.setattr(
        "ibkr.trading_allowed.spend_state",
        lambda _kind: ("live_armed", ""),
    )
    snap = evaluate_trading_allowed(
        client_enabled=True,
        connected=True,
        account_mode="live",
        broker_account_kind="live",
    )
    assert snap["trading_allowed"] is False
    assert snap["armed"] is False
    assert "disarmed" in snap["trading_allowed_reason"].lower()


def test_evaluate_blocked_matches_place_reason(monkeypatch):
    monkeypatch.setattr(
        "ibkr.trading_allowed.assert_orders_allowed",
        lambda **_kw: (False, "Orders locked — IBKR_ORDERS_ENABLED is off"),
    )
    monkeypatch.setattr(
        "ibkr.trading_allowed.spend_state",
        lambda _kind: ("locked", "Orders locked — IBKR_ORDERS_ENABLED is off"),
    )
    snap = evaluate_trading_allowed(
        client_enabled=True,
        connected=True,
        account_mode="paper",
        broker_account_kind="paper",
    )
    assert snap["trading_allowed"] is False
    assert "ORDERS_ENABLED" in snap["trading_allowed_reason"]


def test_disconnected_is_not_allowed(monkeypatch):
    monkeypatch.setattr(
        "ibkr.trading_allowed.assert_orders_allowed",
        lambda **kw: (False, "IBKR not connected")
        if not kw.get("connected")
        else (True, ""),
    )
    monkeypatch.setattr(
        "ibkr.trading_allowed.spend_state",
        lambda _kind: ("paper_armed", ""),
    )
    snap = evaluate_trading_allowed(
        client_enabled=True,
        connected=False,
        account_mode="paper",
        broker_account_kind="paper",
    )
    assert snap["trading_allowed"] is False
    assert snap["trading_allowed_reason"]


def _fresh_trading_allowed():
    """Fresh module -- autouse conftest pins places_allowed True for other tests."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "ibkr" / "trading_allowed.py"
    spec = importlib.util.spec_from_file_location("trading_allowed_fresh", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_places_allowed_is_true_in_sim_once_armed():
    """ADR 018: Sim routes the order; the arm latch decides there is one."""
    from ibkr import safety as _safety
    from sim.mode import reset_for_tests, set_sim_mode

    reset_for_tests()
    set_sim_mode(True)
    try:
        _safety.set_armed(True)
        ok, reason = _fresh_trading_allowed().places_allowed()
        assert ok is True
        assert reason == ""
    finally:
        reset_for_tests()


def test_places_allowed_is_false_in_sim_while_disarmed():
    """ADR 018 decision 2: a fresh process is disarmed in every venue."""
    from sim.mode import reset_for_tests, set_sim_mode

    reset_for_tests()
    set_sim_mode(True)
    try:
        ok, reason = _fresh_trading_allowed().places_allowed()
        assert ok is False
        assert "disarmed" in reason.lower()
    finally:
        reset_for_tests()


def test_require_places_allowed_uses_bot_reason(monkeypatch):
    monkeypatch.setattr(
        "ibkr.trading_allowed.places_allowed",
        lambda: (False, "spend locked"),
    )
    from bot.errors import BotError

    with pytest.raises(BotError) as exc:
        require_places_allowed()
    assert exc.value.status_code == 409
    assert exc.value.reason == BOT_REASON_TRADING_LOCKED
    assert "spend locked" in str(exc.value)
