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


def test_bp_alone_does_not_invent_margin():
    assert classify_account_class({"BuyingPower": 50_000.0}) == "cash"
    assert classify_account_class({"AccountType": "INDIVIDUAL", "BuyingPower": 50_000.0}) == "cash"


def test_attach_skips_disconnected():
    raw = {"connected": False, "mode": "disconnected"}
    assert "account_class" not in attach_account_class(raw)
    connected = attach_account_class({"connected": True, "mode": "live", "AccountType": "INDIVIDUAL"})
    assert connected["account_class"] == "cash"
    assert connected["AccountType"] == "INDIVIDUAL"
