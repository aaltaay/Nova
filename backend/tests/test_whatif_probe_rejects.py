"""IBKR's refusals of Nova's margin what-if are the probe's answer, never an order's (Sentry review, 2026-10-13).

On 2026-10-12/13 the live desk logged 128 ERROR lines from ``ib_async.wrapper`` that reached Sentry: 76 Error 110
(``GET /api/short-check/JBDI?price=5.4701``: the plan's sub-penny entry on a $5 stock), 41 Error 201 "short stock
positions can only be held in a margin account" (the ticket and plan's what-if on the Live cash account) and 11
Error 201 "available settled cash" (a Paper buy's background what-if). None was an order: ib_async logs "Canceled
order" for every rejected Trade, and none appeared.
"""
from __future__ import annotations

import asyncio
import logging
import time
from types import SimpleNamespace

import pytest

from constants_shorts import SHORT_WHATIF_REQID_TTL_SEC, SHORT_WHATIF_RETRY_SEC
from ibkr import margin_whatif
from short_sale import whatif

CASH_SHORT = ("Order rejected - reason:Short stock positions can only be held in a margin account "
              "(you are using a cash account).")
CASH_BUY = ("Order rejected - reason:AVAILABLE SETTLED CASH CONVERTED TO BASE: 347.44 USD CASH NEEDED FOR THIS "
            "ORDER AND OTHER PENDING ORDERS: 2525.00 USD")
OFF_TICK = "The price does not conform to the minimum price variation for this contract."
SHORT_REASON = "the IBKR account is a cash account, which cannot hold a short"


@pytest.fixture(autouse=True)
def _clean():
    margin_whatif.reset_for_tests()
    whatif.reset_for_tests()
    yield
    margin_whatif.reset_for_tests()
    whatif.reset_for_tests()


@pytest.mark.parametrize("raw, ticked", [
    (5.4701, 5.47), (5.8101, 5.81), (3.89, 3.89), (1.004, 1.0), (0.51234, 0.5123), (0.99996, 1.0),
    (0.00001, 0.0001),
])
def test_a_price_goes_on_the_listed_tick(raw, ticked):
    assert margin_whatif.on_tick(raw) == pytest.approx(ticked, abs=1e-9)


def test_plain_reasons_for_ibkrs_refusals():
    assert margin_whatif.plain_reason(201, CASH_SHORT) == SHORT_REASON
    assert margin_whatif.plain_reason(201, CASH_BUY) == (
        "the IBKR account is a cash account, and its settled cash (347.44 USD) is under the 2525.00 USD this "
        "order needs")
    assert "off the stock's tick" in margin_whatif.plain_reason(110, OFF_TICK)
    assert margin_whatif.plain_reason(201, "Order rejected - reason:Something new.") == \
        "IBKR refused it: Something new (Error 201)"


@pytest.fixture
def real_ib(monkeypatch):
    """ib_async's own IB and wrapper (the pinned commit) with nothing on the wire: the request registry,
    the error handler and errorEvent are the library's, so the reqId match is proven against it."""
    from ib_async import IB

    from ibkr import client
    from ibkr.log_filters import install_ibkr_log_filters

    ib = IB()
    sent: list = []
    ids = iter(range(4242, 4300))
    monkeypatch.setattr(ib.client, "getReqId", lambda: next(ids))
    monkeypatch.setattr(ib.client, "placeOrder", lambda *a: sent.append(a))

    async def qualify(contract):
        return [contract]

    monkeypatch.setattr(ib, "qualifyContractsAsync", qualify)
    monkeypatch.setattr(client, "get_ib", lambda: ib)
    monkeypatch.setattr(client, "is_ready", lambda: True)
    install_ibkr_log_filters()
    return SimpleNamespace(ib=ib, sent=sent)


def _ask_refused(real, code: int, text: str, symbol="JBDI", side="SELL", qty=33, price=5.4701) -> dict:
    """Ask the what-if and answer it the way IBKR answered the live desk: an error on its orderId."""
    async def run():
        task = asyncio.create_task(margin_whatif.ask(symbol, side, qty, price, timeout=1.0))
        while not real.sent:
            await asyncio.sleep(0)
        order_id, _contract, order = real.sent[-1]
        assert order.whatIf is True       # ib_async's what-if copy, never a real order
        real.ib.wrapper.error(order_id, code, text, "")
        return await task

    return asyncio.run(run())


def _wrapper_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "ib_async.wrapper"]


def test_the_what_if_asks_on_the_tick_never_a_sub_penny_over_a_dollar(real_ib):
    _ask_refused(real_ib, 201, CASH_SHORT)
    (_, _, order), = real_ib.sent
    assert order.lmtPrice == 5.47 and order.action == "SELL" and order.totalQuantity == 33


def test_a_cash_accounts_short_refusal_is_a_warning_in_plain_words(real_ib, caplog):
    caplog.set_level(logging.INFO, logger="ib_async.wrapper")
    raw = _ask_refused(real_ib, 201, CASH_SHORT)
    assert raw["ok"] is False and raw["error"] == SHORT_REASON and raw["price"] == 5.47
    (rec,) = _wrapper_records(caplog)
    assert rec.levelno == logging.WARNING
    assert rec.getMessage() == (
        f"IBKR refused Nova's margin what-if for SELL 33 JBDI @ 5.47 (nothing was placed): {SHORT_REASON}. "
        "Nova uses the published margin rules for JBDI (IBKR Error 201, reqId 4242)")
    whatif.remember(raw)
    assert whatif.last_error("JBDI", "SELL") == SHORT_REASON


def test_a_paper_buys_settled_cash_refusal_is_a_warning_too(real_ib, caplog):
    caplog.set_level(logging.INFO, logger="ib_async.wrapper")
    raw = _ask_refused(real_ib, 201, CASH_BUY, symbol="LNKS", side="BUY", qty=1000, price=2.525)
    assert "settled cash (347.44 USD)" in raw["error"]
    (rec,) = _wrapper_records(caplog)
    assert rec.levelno == logging.WARNING and "for BUY 1000 LNKS @ 2.52" in rec.getMessage()


def test_an_unexpected_code_on_the_what_if_stays_an_error_with_the_probe_named(real_ib, caplog):
    caplog.set_level(logging.INFO, logger="ib_async.wrapper")
    raw = _ask_refused(real_ib, 110, OFF_TICK)
    assert raw["ok"] is False and "off the stock's tick" in raw["error"]
    (rec,) = _wrapper_records(caplog)
    assert rec.levelno == logging.ERROR and "Nova's margin what-if for SELL 33 JBDI" in rec.getMessage()


def test_a_201_on_an_orders_reqid_stays_an_error(real_ib, caplog):
    caplog.set_level(logging.INFO, logger="ib_async.wrapper")
    _ask_refused(real_ib, 201, CASH_SHORT)                # reqId 4242 is the probe's
    caplog.clear()
    real_ib.ib.wrapper.error(9001, 201, CASH_SHORT, "")   # Nova sent no what-if under 9001: an order's
    (rec,) = _wrapper_records(caplog)
    assert rec.levelno == logging.ERROR
    assert rec.getMessage().startswith("Error 201, reqId 9001: Order rejected - reason:Short stock")


def test_a_what_if_reqid_is_the_probes_only_for_a_while():
    margin_whatif._note(77, "SELL 10 ABC @ 3", "ABC")
    line = f"Error 201, reqId 77: {CASH_SHORT}"
    assert margin_whatif.probe_line(line) is not None
    assert margin_whatif.probe_line(line, now=time.time() + SHORT_WHATIF_REQID_TTL_SEC + 1) is None
    assert margin_whatif.probe_line(f"Error 201, reqId 78: {CASH_SHORT}") is None


def test_a_refused_stock_is_not_asked_again_before_the_retry_gap(monkeypatch):
    from ibkr import client

    monkeypatch.setattr(client, "is_ready", lambda: True)
    whatif.remember({"ok": False, "symbol": "JBDI", "side": "SELL", "error": SHORT_REASON, "ts": time.time()})
    assert whatif.due("JBDI", "SELL") is False
    assert whatif.request("JBDI", "SELL", 33, 5.47) is False
    assert whatif.due("JBDI", "SELL", now=time.time() + SHORT_WHATIF_RETRY_SEC + 1) is True
    assert whatif.due("JBDI", "BUY") is True        # the other side was never refused


def test_the_margin_rule_says_why_ibkrs_figure_is_missing(short_market_open):
    from short_sale import check, halts, ssr
    from short_sale import facts as short_facts

    def margin_rule(whatif_error):
        facts = short_facts.Facts(
            venue="paper", symbol="JBDI", now=short_market_open, replay=False,
            borrow={"shortable_shares": 30_000, "state": "shortable_est", "age_sec": 1.0, "stale": False},
            borrow_why=None, whatif=None, ssr=ssr.SsrRead("off", "No SSR."),
            halt=halts.HaltRead("clear", "trading"), bid=5.46, ask=5.48, last=5.47, whatif_error=whatif_error)
        summary = {"connected": True, "pending": False, "NetLiquidation": 5_000.0, "ExcessLiquidity": 5_000.0,
                   "BuyingPower": 20_000.0, "account_class": "margin", "ibkr_account_class": "margin"}
        account = check.Account(summary=summary, positions=[], held_long=0.0, held_short=0.0)
        order = check.Order(symbol="JBDI", qty=33, entry=5.47, stop=6.07)
        return next(r for r in check.rules(order, facts, account, live_key=None) if r.id == "margin")

    refused = margin_rule(SHORT_REASON)
    assert refused.text.startswith("Margin (published rules): ")
    assert refused.text.endswith(f"IBKR's what-if gave none: {SHORT_REASON}.")
    assert refused.numbers["whatif_error"] == SHORT_REASON
    plain = margin_rule(None)
    assert "what-if" not in plain.text and plain.numbers["whatif_error"] is None
