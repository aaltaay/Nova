"""#91 — per-order TIF and the manual ticket's optional protective legs.

Everything here stays on `execution.service.execute` (ADR 007). No Gateway.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import execution.service as exec_svc
import execution.store as store
import execution.telemetry as telemetry
import ibkr.account as account_mod
import ibkr.client as client_mod
import ibkr.orders as orders_mod
import ibkr.safety as safety_mod
import kill_switch
import strategy.risk as risk_mod
from execution.models import ExecutionCommand
from ibkr.order_build import build_ib_order, normalize_tif, tif_error


@pytest.fixture(autouse=True)
def isolated_execution(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    import execution.broker_send as broker_send

    monkeypatch.setattr(broker_send, "EXECUTION_ACK_WAIT_SEC", 0.05)
    store.init_db()
    telemetry.reset_for_tests()
    risk_mod.reset_day()
    kill_switch._tripped = False
    yield
    telemetry.reset_for_tests()
    risk_mod.reset_day()
    kill_switch._tripped = False


def _arm_paper(monkeypatch, *, buying_power: float = 100_000.0, positions=None):
    monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    monkeypatch.setattr(client_mod, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    monkeypatch.setattr(safety_mod, "orders_enabled", lambda: True)
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": buying_power, "pending": False},
    )
    monkeypatch.setattr(account_mod, "get_positions", lambda: positions or [])


def _spy_place(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def place(**kw):
        calls.append(kw)
        return {"ok": True, "order_id": 11, "error": None, "mode": "paper"}

    monkeypatch.setattr(orders_mod, "place_order", place)
    return calls


def _spy_bracket(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def bracket(**kw):
        calls.append(kw)
        return {
            "ok": True, "parent_order_id": 21, "target_order_id": 22,
            "stop_order_id": 23, "error": None, "mode": "paper",
        }

    monkeypatch.setattr(orders_mod, "place_bracket_order", bracket)
    return calls


def _limit_buy(key: str, **kw) -> ExecutionCommand:
    base = dict(
        operation="place", idempotency_key=key, source="manual", symbol="AAPL",
        side="BUY", qty=1, order_type="LMT", limit_price=1.0,
        skip_risk=True,
    )
    base.update(kw)
    return ExecutionCommand(**base)


def _bracket(key: str, **kw) -> ExecutionCommand:
    base = dict(
        operation="bracket", idempotency_key=key, source="manual", symbol="AAPL",
        side="BUY", qty=1, order_type="LMT", limit_price=10.0, entry_price=10.0,
        stop_price=9.5, target_price=11.0, skip_risk=True,
    )
    base.update(kw)
    return ExecutionCommand(**base)


class TestTifDefaultAndGtc:
    def test_command_default_is_day(self):
        assert _limit_buy("tif-default").tif == "DAY"
        assert normalize_tif(None) == "DAY"
        assert normalize_tif(" gtc ") == "GTC"

    def test_default_place_sends_day(self, monkeypatch):
        _arm_paper(monkeypatch)
        calls = _spy_place(monkeypatch)
        receipt = asyncio.run(exec_svc.execute(_limit_buy("tif-day"), wait_ack=False))
        assert receipt.ok is True
        assert calls[0]["tif"] == "DAY"

    def test_gtc_reaches_the_adapter_and_the_ib_order(self, monkeypatch):
        _arm_paper(monkeypatch)
        calls = _spy_place(monkeypatch)
        receipt = asyncio.run(
            exec_svc.execute(_limit_buy("tif-gtc", tif="GTC"), wait_ack=False)
        )
        assert receipt.ok is True
        assert calls[0]["tif"] == "GTC"
        for order_type, limit, stop in (
            ("MKT", None, None), ("LMT", 5.0, None), ("STP", None, 4.0),
            ("STP LMT", 5.0, 4.0), ("TRAIL", None, 0.25),
        ):
            order = build_ib_order("BUY", 1, order_type, limit, stop, False, "GTC")
            assert order.tif == "GTC", order_type

    def test_invalid_tif_is_refused_before_the_broker(self, monkeypatch):
        _arm_paper(monkeypatch)
        calls = _spy_place(monkeypatch)
        receipt = asyncio.run(
            exec_svc.execute(_limit_buy("tif-ioc", tif="IOC"), wait_ack=False)
        )
        assert receipt.ok is False
        assert receipt.reason_code == "TIF_INVALID"
        assert calls == []

    def test_adapter_refuses_an_unsupported_tif_itself(self):
        assert tif_error("GTD") is not None
        assert tif_error("gtc") is None
        result = orders_mod.place_order(
            symbol="AAPL", side="BUY", qty=1, order_type="MKT", tif="GTD",
        )
        assert result["ok"] is False
        assert "tif" in str(result["error"])

    def test_bracket_legs_carry_tif_and_extended_hours(self, monkeypatch):
        _arm_paper(monkeypatch)
        calls = _spy_bracket(monkeypatch)
        receipt = asyncio.run(
            exec_svc.execute(
                _bracket("tif-bracket", tif="GTC", outside_rth=True), wait_ack=False,
            )
        )
        assert receipt.ok is True
        assert calls[0]["tif"] == "GTC"
        assert calls[0]["outside_rth"] is True

    def test_ib_bracket_helper_applies_tif_to_every_leg(self, monkeypatch):
        from ib_async import IB

        placed: list = []
        reqid = {"n": 100}
        fake_ib = SimpleNamespace(
            client=SimpleNamespace(getReqId=lambda: reqid.__setitem__("n", reqid["n"] + 1) or reqid["n"]),
            placeOrder=lambda contract, order: placed.append(order),
        )
        fake_ib.bracketOrder = lambda *a, **k: IB.bracketOrder(fake_ib, *a, **k)
        monkeypatch.setattr(orders_mod, "_safety_check", lambda: (True, ""))
        monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
        monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
        monkeypatch.setattr(orders_mod, "_ib_sync", lambda fn, label, timeout=15.0: fn())
        out = orders_mod.place_bracket_order(
            symbol="AAPL", side="BUY", qty=1, entry_price=10.0,
            stop_price=9.5, target_price=11.0, tif="GTC", outside_rth=True,
        )
        assert out["ok"] is True
        assert len(placed) == 3
        assert [o.tif for o in placed] == ["GTC", "GTC", "GTC"]
        assert all(o.outsideRth is True for o in placed)

    def test_replace_keeps_the_working_orders_tif(self, monkeypatch):
        from execution.broker_send import _working_tif

        assert _working_tif({"tif": "GTC"}) == "GTC"
        assert _working_tif({"tif": ""}) == "DAY"
        assert _working_tif({"tif": "GTD"}) == "DAY"
        assert _working_tif({}) == "DAY"

        _arm_paper(monkeypatch)
        calls = _spy_place(monkeypatch)
        monkeypatch.setattr(
            orders_mod,
            "open_orders",
            lambda: [{
                "order_id": 77, "symbol": "AAPL", "side": "BUY", "qty": 1.0,
                "order_type": "LMT", "limit_price": 9.0, "stop_price": None,
                "outside_rth": False, "tif": "GTC",
            }],
        )
        receipt = asyncio.run(
            exec_svc.execute(
                ExecutionCommand(
                    operation="replace", idempotency_key="replace-gtc",
                    source="manual", order_id=77, limit_price=9.5,
                    skip_risk=True,
                ),
                wait_ack=False,
            )
        )
        assert receipt.ok is True
        assert calls[0]["tif"] == "GTC"
        assert calls[0]["limit_price"] == 9.5


class TestProtectiveLegDefaults:
    """Defaults off → plain place; defaults on → bracket, same service."""

    def test_defaults_off_is_a_plain_place(self, monkeypatch):
        _arm_paper(monkeypatch)
        places = _spy_place(monkeypatch)
        brackets = _spy_bracket(monkeypatch)
        receipt = asyncio.run(exec_svc.execute(_limit_buy("legs-off"), wait_ack=False))
        assert receipt.ok is True
        assert len(places) == 1
        assert brackets == []

    def test_defaults_on_places_one_bracket(self, monkeypatch):
        _arm_paper(monkeypatch)
        places = _spy_place(monkeypatch)
        brackets = _spy_bracket(monkeypatch)
        receipt = asyncio.run(exec_svc.execute(_bracket("legs-on"), wait_ack=False))
        assert receipt.ok is True
        assert places == []
        assert len(brackets) == 1
        assert brackets[0]["entry_price"] == 10.0
        assert brackets[0]["target_price"] == 11.0
        assert brackets[0]["stop_price"] == 9.5
        assert receipt.parent_order_id == 21
        assert receipt.target_order_id == 22
        assert receipt.stop_order_id == 23

    def test_inverted_legs_are_refused(self, monkeypatch):
        _arm_paper(monkeypatch)
        brackets = _spy_bracket(monkeypatch)
        receipt = asyncio.run(
            exec_svc.execute(
                _bracket("legs-inverted", stop_price=11.0, target_price=9.5),
                wait_ack=False,
            )
        )
        assert receipt.ok is False
        assert receipt.reason_code == "BRACKET_GEOMETRY"
        assert brackets == []

    def test_short_bracket_geometry_is_mirrored(self, monkeypatch):
        _arm_paper(monkeypatch)
        brackets = _spy_bracket(monkeypatch)
        monkeypatch.setattr(safety_mod, "short_enabled", lambda: True)
        monkeypatch.setattr(
            "ibkr.shortability.fetch_shortability", lambda symbol: {"ok": True},
        )
        monkeypatch.setattr(
            "ibkr.shortability.assert_shortable_for_order",
            lambda snap: (True, "OK", None),
        )
        good = asyncio.run(
            exec_svc.execute(
                _bracket(
                    "short-ok", side="SELL", short_entry=True,
                    stop_price=11.0, target_price=9.5,
                ),
                wait_ack=False,
            )
        )
        assert good.ok is True, good.error
        bad = asyncio.run(
            exec_svc.execute(
                _bracket(
                    "short-bad", side="SELL", short_entry=True,
                    stop_price=9.5, target_price=11.0,
                ),
                wait_ack=False,
            )
        )
        assert bad.ok is False
        assert bad.reason_code == "BRACKET_GEOMETRY"
        assert len(brackets) == 1

    def test_side_must_agree_with_short_entry(self, monkeypatch):
        _arm_paper(monkeypatch)
        brackets = _spy_bracket(monkeypatch)
        receipt = asyncio.run(
            exec_svc.execute(_bracket("legs-side", side="SELL"), wait_ack=False)
        )
        assert receipt.ok is False
        assert receipt.reason_code == "BRACKET_SIDE"
        assert brackets == []

    def test_fractional_bracket_qty_is_refused(self, monkeypatch):
        _arm_paper(monkeypatch)
        brackets = _spy_bracket(monkeypatch)
        import execution.qty_gate as qty_gate

        monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", False)
        monkeypatch.setattr(exec_svc, "IBKR_FORCE_ONE_SHARE", False)
        receipt = asyncio.run(
            exec_svc.execute(_bracket("legs-frac", qty=1.5), wait_ack=False)
        )
        assert receipt.ok is False
        assert receipt.reason_code == "QTY_FRACTIONAL_API"
        assert brackets == []

    def test_bracket_respects_buying_power(self, monkeypatch):
        _arm_paper(monkeypatch, buying_power=5.0)
        brackets = _spy_bracket(monkeypatch)
        import execution.qty_gate as qty_gate

        monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", False)
        monkeypatch.setattr(exec_svc, "IBKR_FORCE_ONE_SHARE", False)
        receipt = asyncio.run(
            exec_svc.execute(_bracket("legs-bp", qty=10), wait_ack=False)
        )
        assert receipt.ok is False
        assert receipt.reason_code == "BUYING_POWER"
        assert brackets == []

    def test_long_bracket_while_short_is_refused(self, monkeypatch):
        _arm_paper(monkeypatch, positions=[{"symbol": "AAPL", "qty": -5.0}])
        brackets = _spy_bracket(monkeypatch)
        receipt = asyncio.run(exec_svc.execute(_bracket("legs-short"), wait_ack=False))
        assert receipt.ok is False
        assert receipt.reason_code == "BRACKET_WHILE_SHORT"
        assert brackets == []


class TestGatesStayIntact:
    def test_protective_sources_never_carry_legs(self, monkeypatch):
        _arm_paper(monkeypatch, positions=[{"symbol": "AAPL", "qty": 5.0}])
        brackets = _spy_bracket(monkeypatch)
        for source in ("flatten", "kill", "cancel_working"):
            receipt = asyncio.run(
                exec_svc.execute(
                    _bracket(f"legs-{source}", source=source), wait_ack=False,
                )
            )
            assert receipt.ok is False, source
            assert receipt.reason_code == "BRACKET_SOURCE", source
        assert brackets == []

    def test_flatten_and_kill_places_are_unaffected(self, monkeypatch):
        _arm_paper(monkeypatch, positions=[{"symbol": "AAPL", "qty": 5.0}])
        places = _spy_place(monkeypatch)
        brackets = _spy_bracket(monkeypatch)
        for key, source in (("flat-1", "flatten"), ("kill-1", "kill")):
            receipt = asyncio.run(
                exec_svc.execute(
                    ExecutionCommand(
                        operation="place", idempotency_key=key, source=source,
                        symbol="AAPL", side="SELL", qty=5, order_type="MKT",
                        skip_risk=True,
                    ),
                    wait_ack=False,
                )
            )
            assert receipt.ok is True, source
        assert [call["tif"] for call in places] == ["DAY", "DAY"]
        assert brackets == []

    def test_disarmed_desk_still_refuses_a_bracket(self, monkeypatch):
        _arm_paper(monkeypatch)
        brackets = _spy_bracket(monkeypatch)
        monkeypatch.setattr(safety_mod, "_armed", False)
        receipt = asyncio.run(exec_svc.execute(_bracket("legs-disarmed"), wait_ack=False))
        assert receipt.ok is False
        assert receipt.reason_code == "DISARMED"
        assert brackets == []

    def test_kill_switch_refuses_a_bracket(self, monkeypatch):
        _arm_paper(monkeypatch)
        brackets = _spy_bracket(monkeypatch)
        kill_switch._tripped = True
        receipt = asyncio.run(exec_svc.execute(_bracket("legs-kill"), wait_ack=False))
        assert receipt.ok is False
        assert receipt.reason_code == "KILL_SWITCH"
        assert brackets == []

    def test_auto_live_is_refused_everywhere(self, monkeypatch):
        _arm_paper(monkeypatch)
        places = _spy_place(monkeypatch)
        brackets = _spy_bracket(monkeypatch)
        for cmd in (
            _limit_buy("auto-live-place", source="auto_live"),
            _bracket("auto-live-bracket", source="auto_live"),
            _bracket("auto-paper-bracket", source="auto_paper"),
        ):
            receipt = asyncio.run(exec_svc.execute(cmd, wait_ack=False))
            assert receipt.ok is False
            assert receipt.reason_code == "SOURCE_INVALID"
        assert places == []
        assert brackets == []
