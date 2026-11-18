"""Cash vs Margin classify -- no live Gateway."""
from __future__ import annotations

from ibkr.account_class import attach_account_class, classify_account_class


def test_ahmed_individual_bp_near_cash_is_cash():
    assert (
        classify_account_class(
            {
                "AccountType": "INDIVIDUAL",
                "TradingType": "STKNOPT",
                "BuyingPower": 376.0,
                "TotalCashValue": 383.0,
                "NetLiquidation": 540.0,
                "WhatIfPMEnabled": "true",
            }
        )
        == "cash"
    )


def test_explicit_tokens_win_over_numbers():
    assert classify_account_class({"AccountType": "CASH", "BuyingPower": 9000}) == "cash"
    assert classify_account_class({"AccountType": "MARGIN", "BuyingPower": 10}) == "margin"
    assert classify_account_class({"AccountType": "INDIVIDUAL", "TradingType": "CASH"}) == "cash"


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("IBKR_ACCOUNT_CLASS", "margin")
    assert (
        classify_account_class(
            {"AccountType": "CASH", "BuyingPower": 376.0, "TotalCashValue": 383.0}
        )
        == "margin"
    )
    monkeypatch.setenv("IBKR_ACCOUNT_CLASS", "cash")
    assert classify_account_class({"AccountType": "MARGIN"}) == "cash"
    monkeypatch.setenv("IBKR_ACCOUNT_CLASS", "nope")
    assert classify_account_class({"AccountType": "INDIVIDUAL"}) == "cash"


def test_bp_vs_cash_bands():
    assert classify_account_class({"BuyingPower": 100.0, "TotalCashValue": 100.0}) == "cash"
    assert classify_account_class({"BuyingPower": 114.0, "TotalCashValue": 100.0}) == "cash"
    assert classify_account_class({"BuyingPower": 130.0, "TotalCashValue": 100.0}) == "cash"
    assert classify_account_class({"BuyingPower": 150.0, "TotalCashValue": 100.0}) == "margin"


def test_excess_liquidity_leverage_is_margin():
    assert (
        classify_account_class({"BuyingPower": 3000.0, "ExcessLiquidity": 1000.0})
        == "margin"
    )


def test_ibkrs_trading_type_word_decides_before_any_figure():
    """IBKR's TradingType-S ("Account Type" in its Account Value Keys) is the account's class."""
    # The operator's Live cash account, 2026-11-17.
    live_cash = {"AccountType": "INDIVIDUAL", "TradingType": "STKCASH", "BuyingPower": 5083.04,
                 "TotalCashValue": 5083.04, "ExcessLiquidity": 5083.04, "NetLiquidation": 5287.03}
    assert classify_account_class(live_cash) == "cash"
    # The word wins over figures that look leveraged, and over figures that look like cash.
    assert classify_account_class({**live_cash, "BuyingPower": 20_000.0}) == "cash"
    used_up = {"AccountType": "INDIVIDUAL", "TradingType": "STKMRGN", "BuyingPower": 0.0,
               "TotalCashValue": -13_000.0, "ExcessLiquidity": 0.0}
    assert classify_account_class(used_up) == "margin"


def test_a_margin_account_holding_a_short_stays_margin():
    """A short's proceeds sit in cash, so buying power under cash is no proof of a cash account."""
    short = {"AccountType": "INDIVIDUAL", "TradingType": "STKNOPT", "BuyingPower": 11_600.0,
             "TotalCashValue": 13_300.0, "ExcessLiquidity": 2_900.0}
    assert classify_account_class(short) == "margin"
    borrowing = {"AccountType": "INDIVIDUAL", "BuyingPower": 14_000.0, "TotalCashValue": -1_000.0,
                 "ExcessLiquidity": 3_500.0}
    assert classify_account_class(borrowing) == "margin"


def test_a_cash_account_holding_stock_stays_cash():
    """Buying power equal to excess liquidity and to cash is no leverage, whatever the stock is worth."""
    assert classify_account_class({"AccountType": "INDIVIDUAL", "BuyingPower": 383.0, "TotalCashValue": 383.0,
                                   "ExcessLiquidity": 383.0, "NetLiquidation": 5_400.0}) == "cash"
    assert classify_account_class({"BuyingPower": 0.0, "TotalCashValue": 0.0, "ExcessLiquidity": 0.0}) == "cash"


def test_trading_type_from_the_account_values_reaches_the_summary():
    from types import SimpleNamespace

    from ibkr.account_summary import summary_from_items

    def item(tag, value):
        return SimpleNamespace(tag=tag, value=value, currency="")

    figures = [item("AccountType", "INDIVIDUAL"), item("BuyingPower", "5083.04"), item("TotalCashValue", "5083.04")]
    cash = summary_from_items([*figures, item("TradingType-S", "STKCASH")], mode="live")
    assert (cash["TradingType"], cash["account_class"], cash["ibkr_account_class"]) == ("STKCASH", "cash", "cash")
    margin = summary_from_items([*figures, item("TradingType-S", "STKMRGN")], mode="live")
    assert (margin["TradingType"], margin["account_class"], margin["ibkr_account_class"]) == (
        "STKMRGN", "margin", "margin")


def test_bp_alone_does_not_invent_margin():
    assert classify_account_class({"BuyingPower": 50_000.0}) == "cash"
    assert classify_account_class({"AccountType": "INDIVIDUAL", "BuyingPower": 50_000.0}) == "cash"


def test_attach_skips_disconnected():
    raw = {"connected": False, "mode": "disconnected"}
    assert "account_class" not in attach_account_class(raw)
    connected = attach_account_class({"connected": True, "mode": "live", "AccountType": "INDIVIDUAL"})
    assert connected["account_class"] == "cash"
    assert connected["AccountType"] == "INDIVIDUAL"


def test_ibkrs_own_class_never_takes_the_override(monkeypatch):
    """ADR 048 step 6: a Live short needs IBKR's word; the .env override decides only the header's chip."""
    from ibkr.account_class import ibkr_account_class

    cash_like = {"connected": True, "mode": "live", "AccountType": "INDIVIDUAL", "BuyingPower": 383.0,
                 "TotalCashValue": 383.0}
    monkeypatch.setenv("IBKR_ACCOUNT_CLASS", "margin")
    assert ibkr_account_class(cash_like) == "cash"
    stamped = attach_account_class(cash_like)
    assert (stamped["account_class"], stamped["ibkr_account_class"], stamped["account_class_source"]) == (
        "margin", "cash", "override")
    monkeypatch.delenv("IBKR_ACCOUNT_CLASS")
    margin_like = {**cash_like, "BuyingPower": 20_000.0, "TotalCashValue": 5_000.0}
    stamped = attach_account_class(margin_like)
    assert (stamped["account_class"], stamped["ibkr_account_class"], stamped["account_class_source"]) == (
        "margin", "margin", "ibkr")
