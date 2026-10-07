"""IBKR's what-if margin: asked without placing anything, kept as each stock's ratio (ADR 048 decision 2)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ibkr import margin_whatif
from practice import margin as practice_margin
from practice.ledger import Ledger
from short_sale import margin, whatif

UNSET = "1.7976931348623157E308"


class FakeIB:
    """Only what the what-if may touch: positions, qualify, whatIfOrderAsync, managedAccounts."""

    def __init__(self, maint: str = "1250.0", positions=None) -> None:
        self.maint = maint
        self.sent: list = []
        self._positions = positions or []

    def positions(self):
        return self._positions

    async def qualifyContractsAsync(self, contract):
        return [contract]

    def whatIfOrderAsync(self, contract, order):
        self.sent.append((contract, order))
        fut = asyncio.get_running_loop().create_future()
        fut.set_result(SimpleNamespace(initMarginChange="2500.0", maintMarginChange=self.maint,
                                       initMarginAfter=UNSET, maintMarginAfter="1250.0",
                                       equityWithLoanAfter="5000.0", warningText=""))
        return fut

    def placeOrder(self, *a, **k):  # pragma: no cover - the test fails if it is ever reached
        raise AssertionError("a what-if must never place an order")

    def managedAccounts(self):
        return ["U1234567"]


@pytest.fixture
def ib(monkeypatch):
    from ibkr import client

    fake = FakeIB()
    monkeypatch.setattr(client, "get_ib", lambda: fake)
    monkeypatch.setattr(client, "is_ready", lambda: True)
    whatif.reset_for_tests()
    yield fake
    whatif.reset_for_tests()


def test_the_what_if_sends_one_limit_and_reads_the_margin_never_placing(ib):
    raw = asyncio.run(margin_whatif.ask("rdyn", "SELL", 416, 5.77, timeout=1.0))
    assert raw["ok"] and raw["maint_change"] == 1250.0 and raw["init_change"] == 2500.0
    assert raw["maint_after"] == 1250.0 and raw["init_after"] is None   # IBKR's unset double is no figure
    (contract, order), = ib.sent
    assert contract.symbol == "RDYN" and order.action == "SELL" and order.orderType == "LMT"
    assert order.totalQuantity == 416 and order.lmtPrice == 5.77


def test_a_held_stock_is_not_asked_about(ib):
    ib._positions = [SimpleNamespace(contract=SimpleNamespace(symbol="RDYN"), position=-100)]
    raw = asyncio.run(margin_whatif.ask("RDYN", "SELL", 416, 5.77, timeout=1.0))
    assert not raw["ok"] and "holds -100 RDYN" in raw["error"] and ib.sent == []


def test_an_answer_becomes_the_stocks_ratio_over_the_published_rules(ib):
    raw = asyncio.run(margin_whatif.ask("RDYN", "SELL", 416, 5.77, timeout=1.0))
    got = whatif.remember(raw)
    # Published: $5 a share at 5.77 -> 2,080; IBKR said 1,250.
    assert got.published == pytest.approx(2080.0) and got.ratio == pytest.approx(1250.0 / 2080.0)
    assert whatif.ratio("RDYN", "short") == (pytest.approx(1250.0 / 2080.0), "IBKR what-if")
    assert whatif.ratio("RDYN", "long") == (1.0, "published rules")
    assert whatif.ratio("RDYN", "short", published_only=True)[1] == "published rules"


def test_no_maintenance_is_no_answer_and_says_why(ib):
    assert whatif.remember({"ok": True, "symbol": "X", "side": "BUY", "qty": 10, "price": 3.0,
                            "maint_change": None}) is None
    assert "no maintenance" in whatif.last_error("X", "BUY")
    assert whatif.remember({"ok": False, "symbol": "X", "side": "BUY", "error": "IBKR is not connected"}) is None
    assert whatif.last_error("X", "BUY") == "IBKR is not connected"


def test_a_volatile_names_extra_charge_shrinks_practice_buying_power():
    ledger = Ledger(5000.0, created_ts=1_700_000_000.0)
    ok, needed, available = ledger.can_afford("ABC", "BUY", 1000, 10.0)
    assert (ok, needed, available) == (True, 10_000.0, 20_000.0)       # 4x: the published 25%
    ledger.margin_ratio = lambda symbol, side: (2.0, "IBKR what-if") if symbol == "ABC" else (1.0, "published rules")
    ok, needed, available = ledger.can_afford("ABC", "BUY", 1000, 10.0)
    assert (ok, needed) == (True, 20_000.0)
    assert ledger.can_afford("ABC", "BUY", 1001, 10.0)[0] is False


def test_a_short_is_measured_in_margin_and_none_under_2000():
    ok, needed, available = practice_margin.check("SELL", 400, 4.0, 0.0, 5000.0, 0.0, maint=0.0)
    assert (ok, needed, available) == (True, 1600.0, 5000.0)        # 100% of value from $2.50 to $5
    assert practice_margin.check("SELL", 400, 4.0, 0.0, 1999.0, 0.0, maint=0.0)[0] is False
    # A cover needs nothing.
    assert practice_margin.check("BUY", 400, 4.0, -400.0, 5000.0, 1600.0, maint=1600.0)[:2] == (True, 0.0)


def test_held_shorts_count_their_tiers_in_maintenance_and_buying_power():
    rows = [{"symbol": "RDYN", "qty": -400, "market_price": 4.0}, {"symbol": "ABC", "qty": 100, "market_price": 10.0}]
    assert practice_margin.maintenance(rows) == pytest.approx(1600.0 + 250.0)
    assert practice_margin.buying_power(5000.0, 2600.0, 1850.0) == pytest.approx((5000.0 - 1850.0) * 4)


def test_the_ratio_scales_the_liquidation_price():
    plain = margin.short_liquidation_price(equity=5000.0, other_maint=0.0, qty=400, mark=6.0)
    dear = margin.short_liquidation_price(equity=5000.0, other_maint=0.0, qty=400, mark=6.0, ratio=1.5)
    assert dear < plain
    assert margin.cushion(equity=5000.0, other_maint=0.0, qty=400, entry=6.0, ratio=1.5)["requirement"] == 3000.0
