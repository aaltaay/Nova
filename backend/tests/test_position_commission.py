"""Session commission join -- CommissionReport only, never avg_cost - fill."""
from __future__ import annotations

from ibkr.position_commission import attach_session_commissions


def test_attach_uses_real_report_only(monkeypatch):
    monkeypatch.setattr(
        "execution.store_facts.session_commission_by_symbol",
        lambda **_k: {"SPCX": 1.0},
    )
    monkeypatch.setattr(
        "execution.closed_blotter.session_start_ts",
        lambda: 0.0,
    )
    out = attach_session_commissions([
        {"symbol": "SPCX", "qty": 1, "avg_cost": 151.48},
        {"symbol": "ZTG", "qty": 1, "avg_cost": 1.76},
    ])
    assert out[0]["commission"] == 1.0
    assert out[1]["commission"] is None


def test_empty_rows_stay_empty():
    assert attach_session_commissions([]) == []
