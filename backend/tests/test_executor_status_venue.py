"""Executor status and the auto_paper gate follow the desk venue (ADR 020, second pass).

The Auto Paper controls enable on ``ibkr_connected && ibkr_mode == "paper"``.
On Nova's Paper venue the live Gateway only feeds the desk, so ``ibkr_mode``
must be the venue, not the Gateway's port label; on Live it stays IBKR's own
label. ``auto_paper_gate_status`` on a practice venue needs the venue's feed
and the ADR 018 arm, never the IBKR env gates (ADR 020 decision 4).
"""
from __future__ import annotations

import pytest

from ibkr import client as _client
from ibkr import safety as _safety
from nova_os import control_mode
from sim.mode import reset_for_tests, set_venue
from strategy import executor
from strategy import risk as _risk


@pytest.fixture(autouse=True)
def _venue_and_gateway(monkeypatch):
    reset_for_tests()
    monkeypatch.setattr(_client, "is_connected", lambda: True)
    monkeypatch.setattr(_client, "account_mode", lambda: "live")
    monkeypatch.setattr(_client, "broker_account_kind", lambda: "live")
    monkeypatch.setattr(_client, "is_enabled", lambda: True)
    monkeypatch.setattr(_risk, "can_trade", lambda: (True, "OK"))
    monkeypatch.setattr(control_mode, "is_nyse_holiday", lambda: False)
    yield
    reset_for_tests()


# ── executor.status() ────────────────────────────────────────────────────────

def test_status_reports_the_paper_venue_as_paper_while_the_live_gateway_feeds_it() -> None:
    set_venue("paper")
    status = executor.status()
    assert (status["ibkr_mode"], status["venue"], status["ibkr_connected"]) == ("paper", "paper", True)


def test_status_reports_sim_on_the_sim_venue() -> None:
    set_venue("sim")
    status = executor.status()
    assert (status["ibkr_mode"], status["venue"]) == ("sim", "sim")


def test_status_keeps_ibkrs_own_label_on_live(monkeypatch) -> None:
    set_venue("live")
    assert (executor.status()["ibkr_mode"], executor.status()["venue"]) == ("live", "live")
    monkeypatch.setattr(_client, "account_mode", lambda: "paper")  # the legacy paper Gateway, by hand
    assert executor.status()["ibkr_mode"] == "paper"
    monkeypatch.setattr(_client, "is_connected", lambda: False)
    monkeypatch.setattr(_client, "account_mode", lambda: "disconnected")
    status = executor.status()
    assert (status["ibkr_mode"], status["ibkr_connected"]) == ("disconnected", False)


def test_ibkr_connected_stays_the_transport_truth_on_paper(monkeypatch) -> None:
    set_venue("paper")
    monkeypatch.setattr(_client, "is_connected", lambda: False)
    status = executor.status()
    assert (status["ibkr_mode"], status["ibkr_connected"]) == ("paper", False)


# ── control_mode.auto_paper_gate_status() ────────────────────────────────────

def test_auto_paper_opens_on_the_paper_venue_with_the_live_feed_and_the_arm(monkeypatch) -> None:
    set_venue("paper")
    monkeypatch.setattr(_safety, "orders_enabled", lambda: False)  # the IBKR env gate is Live-only
    _safety.set_armed(True, reason="test")
    assert control_mode.auto_paper_gate_status() == (True, "OK")


def test_auto_paper_on_a_practice_venue_still_needs_the_arm_latch() -> None:
    set_venue("paper")
    _safety.set_armed(False, reason="test")
    ok, reason = control_mode.auto_paper_gate_status()
    assert ok is False and reason == _safety.DISARMED_REASON


def test_auto_paper_on_paper_needs_the_live_feed(monkeypatch) -> None:
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    monkeypatch.setattr(_client, "is_connected", lambda: False)
    ok, reason = control_mode.auto_paper_gate_status()
    assert ok is False and "paper" in reason and "not connected" in reason


def test_auto_paper_on_sim_needs_no_gateway(monkeypatch) -> None:
    set_venue("sim")
    _safety.set_armed(True, reason="test")
    monkeypatch.setattr(_client, "is_connected", lambda: False)
    assert control_mode.auto_paper_gate_status() == (True, "OK")


def test_auto_paper_on_a_practice_venue_keeps_risk_and_the_holiday_gate(monkeypatch) -> None:
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    monkeypatch.setattr(_risk, "can_trade", lambda: (False, "daily loss limit"))
    assert control_mode.auto_paper_gate_status() == (False, "daily loss limit")
    monkeypatch.setattr(_risk, "can_trade", lambda: (True, "OK"))
    monkeypatch.setattr(control_mode, "is_nyse_holiday", lambda: True)
    assert control_mode.auto_paper_gate_status()[1] == "auto_paper blocked: NYSE holiday"


def test_auto_paper_on_live_keeps_every_ibkr_gate() -> None:
    set_venue("live")
    _safety.set_armed(True, reason="test")
    ok, reason = control_mode.auto_paper_gate_status()
    assert ok is False and "requires paper Gateway" in reason
