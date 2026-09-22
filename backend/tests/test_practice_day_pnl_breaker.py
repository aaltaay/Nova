"""QA W2 / W3 (2026-09-22): the breaker compares today's practice P&L, not the lifetime realized."""
from __future__ import annotations

from datetime import datetime

import pytest

from practice.clock import ET
from practice.ledger import Ledger

DAY1 = datetime(2026, 9, 21, 10, 0, tzinfo=ET).timestamp()
DAY2 = datetime(2026, 9, 22, 10, 0, tzinfo=ET).timestamp()


def _row(oid: int, side: str, qty: float = 10) -> dict:
    return {
        "order_id": oid, "symbol": "IMCC", "side": side, "qty": float(qty), "filled_qty": 0.0,
        "remaining_qty": float(qty), "order_type": "MKT", "limit_price": None, "stop_price": None,
        "status": "Submitted", "placed_ts": DAY1, "source": "nova", "order_source": "manual",
        "bot_id": None,
    }


def _losing_day_one() -> Ledger:
    """Day 1: buy 10 @ 20, sell 10 @ 14 -- about -$60 realized; then a new day starts."""
    ledger = Ledger(100_000, created_ts=DAY1)
    ledger.place(_row(1, "BUY"), ts=DAY1, source="manual")
    ledger.fill(1, ts=DAY1 + 1, price=20.0, basis="quote")
    ledger.place(_row(2, "SELL"), ts=DAY1 + 2, source="manual")
    ledger.fill(2, ts=DAY1 + 3, price=14.0, basis="quote")
    assert ledger.rollover(DAY2) is True
    return ledger


def test_realized_today_resets_at_the_practice_day_boundary():
    ledger = _losing_day_one()
    assert ledger.realized < -59
    assert ledger.realized_today() == pytest.approx(0.0)
    assert ledger.day_pnl() == pytest.approx(0.0)
    snap = ledger.snapshot("paper")
    assert snap["realized_today"] == 0.0
    assert snap["realized_pnl"] < -59  # the lifetime figure stays for the Account page


def test_a_ledger_down_60_since_reset_does_not_trip_the_breaker_on_a_flat_new_day():
    from bot.day_pnl import day_pnl_usd

    ledger = _losing_day_one()
    summary = {
        "practice": True,
        "RealizedPnL": round(ledger.realized_today(), 2),
        "UnrealizedPnL": round(ledger.unrealized_pnl(), 2),
        "DayPnL": round(ledger.day_pnl(), 2),
    }
    # Session commissions must not be subtracted again: the ledger's cash already paid them.
    assert day_pnl_usd(summary, commission_total=12.34) == pytest.approx(0.0)


def test_off_the_practice_venues_the_meter_is_unchanged():
    from bot.day_pnl import day_pnl_usd

    live = {"RealizedPnL": -10.0, "UnrealizedPnL": 4.0}
    assert day_pnl_usd(live, commission_total=1.5) == pytest.approx(-7.5)


def test_the_practice_summary_carries_todays_realized_and_the_day_pnl(monkeypatch, tmp_path):
    from practice import broker as broker_mod

    broker = broker_mod.for_venue("sim")
    ledger = _losing_day_one()
    monkeypatch.setattr(broker, "ledger", ledger, raising=False)
    monkeypatch.setattr(broker, "_refresh_marks", lambda: None, raising=False)
    summary = broker.account_summary()
    assert summary["RealizedPnL"] == 0.0
    assert summary["DayPnL"] == 0.0
    assert summary["practice"] is True
