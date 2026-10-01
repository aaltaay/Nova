"""The day P&L the breakers compare: IBKR's realized + unrealized on Live, never less commissions again.

IBKR counts every commission in both figures (TWS: realized P&L is "(execution price + commissions
to open) - (execution price + commissions to close)", and the average cost behind unrealized P&L
is "(execution price + commission) / quantity"). Until spec D (2026-09-30) the breakers subtracted
the session's commission reports a second time and tripped that many dollars early.
"""
from __future__ import annotations

import pytest

from bot import day_pnl
from bot.day_pnl import day_pnl_usd, read_account_day_pnl
from sim.mode import reset_for_tests as reset_venue, set_venue


@pytest.fixture
def live(monkeypatch):
    reset_venue()
    set_venue("live", persist=False)
    monkeypatch.setattr("execution.closed_blotter.session_start_ts", lambda: 0.0)
    monkeypatch.setattr("execution.store_facts.session_commission_by_symbol",
                        lambda *, since_ts: {"ABCD": 2.25, "WXYZ": 1.75})
    yield
    reset_venue()


def test_day_pnl_is_ibkrs_realized_plus_unrealized():
    summary = {"RealizedPnL": -40.0, "UnrealizedPnL": -20.0}
    assert day_pnl_usd(summary) == -60.0


def test_day_pnl_missing_one_leg():
    assert day_pnl_usd({"RealizedPnL": -12.0}) == -12.0
    assert day_pnl_usd({"UnrealizedPnL": 3.0}) == 3.0


def test_day_pnl_none_when_no_legs():
    assert day_pnl_usd({}) is None
    assert day_pnl_usd(None) is None
    assert day_pnl_usd({"RealizedPnL": float("nan")}) is None


def test_live_commissions_are_never_subtracted_twice(live, monkeypatch):
    """A round trip that lost $36 before $4 of commissions reads -$40 in IBKR -- and -$40 here."""
    monkeypatch.setattr("ibkr.account.get_account_summary",
                        lambda: {"connected": True, "RealizedPnL": -40.0, "UnrealizedPnL": 0.0})
    pnl, meter = read_account_day_pnl()
    assert pnl == -40.0                                  # it read -44.0 before
    assert meter["day_pnl"] == -40.0 and meter["source"] == "account_summary"
    assert meter["commissions"] == 4.0 and meter["commissions_in_figure"] is True
    assert "already inside" in meter["compares"]
    assert meter["venue"] == "live" and meter["compared"] is True


def test_a_disconnected_account_is_a_stated_unknown(live, monkeypatch):
    monkeypatch.setattr("ibkr.account.get_account_summary", lambda: {"connected": False})
    pnl, meter = read_account_day_pnl()
    assert pnl is None
    assert "Gateway disconnected" in meter["error"]


def test_an_unreadable_summary_is_a_stated_unknown(live, monkeypatch):
    def boom():
        raise RuntimeError("accountValues failed")

    monkeypatch.setattr("ibkr.account.get_account_summary", boom)
    pnl, meter = read_account_day_pnl()
    assert pnl is None and meter["source"] == "error"
    assert "accountValues failed" in meter["error"] and "Nothing" in meter["compares"]


def test_paper_compares_the_ledgers_day_pnl(monkeypatch):
    reset_venue()
    try:
        set_venue("paper", persist=False)
        monkeypatch.setattr("ibkr.account.get_account_summary",
                            lambda: {"practice": True, "DayPnL": -12.0, "RealizedPnL": -10.0})
        pnl, meter = read_account_day_pnl()
        assert pnl == -12.0 and meter["source"] == "practice_ledger_day_pnl"
        assert meter["compares"].startswith("Paper's day P&L since 04:00 ET")
    finally:
        reset_venue()


def test_a_sim_replay_compares_nothing(monkeypatch):
    reset_venue()
    try:
        set_venue("sim", persist=False)                # the conftest pins the live edge off
        monkeypatch.setattr("ibkr.account.get_account_summary",
                            lambda: {"practice": True, "DayPnL": -900.0})
        pnl, meter = read_account_day_pnl()
        assert pnl is None and meter["compared"] is False and meter["source"] == "replay"
        assert "Sim replay" in meter["note"]
    finally:
        reset_venue()
        day_pnl.reset_for_tests()
