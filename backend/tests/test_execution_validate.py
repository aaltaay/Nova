"""check_account_and_position must fail closed when IBKR positions/summary
cannot be read — and distinguish POSITION_UNAVAILABLE from NO_POSITION."""
from __future__ import annotations

import execution.validate as validate
import ibkr.account as account_mod
import ibkr.client as client_mod
from execution.models import ExecutionCommand
from ibkr.errors import IbkrAccountError


def _sell_cmd(qty: float = 10.0, source: str = "manual") -> ExecutionCommand:
    return ExecutionCommand(
        operation="place",
        idempotency_key="k1",
        source=source,
        symbol="AAPL",
        side="SELL",
        qty=qty,
        order_type="MKT",
    )


def _limit_buy(qty: float = 10.0, limit_price: float = 50.0) -> ExecutionCommand:
    return ExecutionCommand(
        operation="place",
        idempotency_key="buy-1",
        source="manual",
        symbol="AAPL",
        side="BUY",
        qty=qty,
        order_type="LMT",
        limit_price=limit_price,
    )


def test_position_qty_uses_long_qty(monkeypatch):
    monkeypatch.setattr(account_mod, "long_qty", lambda sym: 7.0 if sym == "AAPL" else 0.0)
    assert validate._position_qty("AAPL") == 7.0


def test_position_qty_raises_when_long_qty_raises(monkeypatch):
    def boom(_sym):
        raise IbkrAccountError("get_positions failed: boom")

    monkeypatch.setattr(account_mod, "long_qty", boom)
    try:
        validate._position_qty("AAPL")
        assert False, "expected IbkrAccountError"
    except IbkrAccountError as exc:
        assert "boom" in str(exc)


def test_sell_refused_position_unavailable_when_read_fails(monkeypatch):
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)

    def boom(_sym):
        raise IbkrAccountError("get_positions failed: boom")

    monkeypatch.setattr(account_mod, "long_qty", boom)
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": 100_000.0, "pending": False},
    )
    ok, detail, reason = validate.check_account_and_position(_sell_cmd())
    assert ok is False
    assert reason == "POSITION_UNAVAILABLE"
    assert "unavailable" in detail.lower()


def test_sell_refused_no_position_when_verified_flat(monkeypatch):
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(account_mod, "long_qty", lambda _sym: 0.0)
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": 100_000.0},
    )
    ok, detail, reason = validate.check_account_and_position(_sell_cmd())
    assert ok is False
    assert reason == "NO_POSITION"
    assert "no long position" in detail


def test_sell_allowed_when_long_qty_covers(monkeypatch):
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(account_mod, "long_qty", lambda _sym: 10.0)
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": 100_000.0},
    )
    ok, detail, reason = validate.check_account_and_position(_sell_cmd(qty=10.0))
    assert ok is True
    assert reason is None


def test_oversell_still_blocked(monkeypatch):
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(account_mod, "long_qty", lambda _sym: 5.0)
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": 100_000.0},
    )
    ok, detail, reason = validate.check_account_and_position(_sell_cmd(qty=10.0))
    assert ok is False
    assert reason == "OVERSELL"


def test_source_flatten_skips_anti_short(monkeypatch):
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)

    def boom(_sym):
        raise IbkrAccountError("should not be called for flatten source")

    monkeypatch.setattr(account_mod, "long_qty", boom)
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": 100_000.0},
    )
    ok, _detail, reason = validate.check_account_and_position(
        _sell_cmd(qty=1.0, source="flatten")
    )
    assert ok is True
    assert reason is None


def test_priced_buy_refused_when_account_values_raises(monkeypatch):
    """BuyingPower fail-open regression: accountValues() throw must refuse LMT BUY."""
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)

    def boom():
        raise IbkrAccountError("get_account_summary failed: boom")

    monkeypatch.setattr(account_mod, "get_account_summary", boom)
    ok, detail, reason = validate.check_account_and_position(_limit_buy())
    assert ok is False
    assert reason == "BUYING_POWER_UNKNOWN"
    assert "BuyingPower" in detail


def test_is_whole_share_qty():
    assert validate.is_whole_share_qty(1) is True
    assert validate.is_whole_share_qty(10.0) is True
    assert validate.is_whole_share_qty(0.0642) is False
    assert validate.is_whole_share_qty(0) is False
    assert validate.is_whole_share_qty(-1) is False


def test_place_rejects_fractional_qty_preflight(monkeypatch):
    """IBKR Error 10243 — never submit fractional lots via the API."""
    import ibkr.safety as safety_mod

    monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    monkeypatch.setattr(client_mod, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(
        safety_mod,
        "assert_orders_allowed",
        lambda **_k: (True, "OK"),
    )
    ok, detail, reason = validate.validate_command(_sell_cmd(qty=0.0642))
    assert ok is False
    assert reason == "QTY_FRACTIONAL_API"
    assert "10243" in detail
