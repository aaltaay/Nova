"""Orders (Today) and Day P&L roll at the trading session, not at the calendar (2026-10-19).

The desk's day is ``market.session_key_et``: 04:00 ET, and a weekend or holiday belongs to the last exchange
day. Two views drifted off it: Live's Orders (Today) cut only the ledger side and let the Gateway's own rows
of earlier days through, and the practice day (Day P&L, practice orders) turned every calendar day at 04:00,
so Saturday zeroed Friday's figures while the boards still showed Friday. Every case is read with the clock
frozen at Monday 00:30 ET, Monday 10:00 ET and Saturday 10:00 ET of the week of 2026-10-19.

The loss limit keeps the calendar clock on purpose (ADR 056): the last test pins that.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import market
from execution import closed_blotter
from execution.closed_blotter import DeskLedger, overlay_closed_orders
from loss_limit import accounts as loss_accounts
from practice import broker as practice_broker
from practice import history
from practice.broker import for_venue, reset_for_tests
from practice.clock import day_start_ts, session_day_start_ts
from sim.fill_model import Reference

ET = ZoneInfo("America/New_York")


def et(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=ET)


MON_0030 = et(10, 19, 0, 30)
MON_1000 = et(10, 19, 10)
SAT_1000 = et(10, 17, 10)
SESSION_START = {  # the 04:00 ET each frozen clock's session began at
    MON_0030: et(10, 16, 4),
    MON_1000: et(10, 19, 4),
    SAT_1000: et(10, 16, 4),
}
LIVE = DeskLedger(practice=False, mode="live")


def freeze(monkeypatch, when: datetime) -> None:
    monkeypatch.setattr(market, "now_et", lambda: when)


def ib_row(order_id: int, when: datetime, **kw) -> dict:
    stamp = when.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
    row = {
        "order_id": order_id, "symbol": "IMCC", "side": "BUY", "qty": 100, "filled_qty": 100.0,
        "remaining_qty": 0.0, "order_type": "MKT", "limit_price": None, "stop_price": None,
        "avg_fill_price": 4.1, "outside_rth": False, "status": "Filled", "submitted_at": stamp,
        "updated_at": stamp, "filled_at": stamp, "held_until": None, "perm_id": None,
    }
    row.update(kw)
    return row


THURSDAY = ib_row(1, et(10, 15, 15))
FRIDAY = ib_row(2, et(10, 16, 15))
MONDAY_PRE = ib_row(3, et(10, 19, 8))


def listed(rows: list[dict]) -> list[int]:
    return sorted(row["order_id"] for row in overlay_closed_orders(rows, ledger_rows=[], desk=LIVE))


def test_the_session_start_follows_the_trading_day(monkeypatch) -> None:
    for when, start in SESSION_START.items():
        freeze(monkeypatch, when)
        assert closed_blotter.session_start_ts() == start.timestamp()


def test_live_blotter_at_monday_0030_is_still_fridays_session(monkeypatch) -> None:
    freeze(monkeypatch, MON_0030)
    assert listed([THURSDAY, FRIDAY]) == [2]


def test_live_blotter_at_monday_1000_drops_fridays_orders(monkeypatch) -> None:
    freeze(monkeypatch, MON_1000)
    assert listed([THURSDAY, FRIDAY, MONDAY_PRE]) == [3]


def test_live_blotter_on_saturday_still_lists_fridays_orders(monkeypatch) -> None:
    freeze(monkeypatch, SAT_1000)
    assert listed([THURSDAY, FRIDAY]) == [2]


def test_a_gateway_row_with_no_clock_stays_listed(monkeypatch) -> None:
    """IBKR gives a completed order read back after a connect no time: shown, never hidden."""
    freeze(monkeypatch, MON_1000)
    undated = ib_row(4, MON_1000, updated_at=None, submitted_at=None, filled_at=None)
    assert listed([FRIDAY, undated]) == [4]


def test_an_order_closed_this_session_that_was_placed_yesterday_stays(monkeypatch) -> None:
    freeze(monkeypatch, MON_1000)
    cancelled = ib_row(5, et(10, 16, 9), status="Cancelled", filled_qty=0.0,
                       updated_at=ib_row(5, et(10, 19, 9))["updated_at"])
    assert listed([cancelled]) == [5]


# -- the practice day ---------------------------------------------------------------------------------


def test_practice_day_start_walks_back_over_the_weekend() -> None:
    assert session_day_start_ts(MON_0030.timestamp()) == et(10, 16, 4).timestamp()
    assert session_day_start_ts(MON_1000.timestamp()) == et(10, 19, 4).timestamp()
    assert session_day_start_ts(SAT_1000.timestamp()) == et(10, 16, 4).timestamp()
    # Weekdays are the plain calendar clock's.
    assert session_day_start_ts(et(10, 21, 10).timestamp()) == day_start_ts(et(10, 21, 10).timestamp())
    assert session_day_start_ts(et(10, 21, 3).timestamp()) == et(10, 20, 4).timestamp()


def test_the_calendar_clock_still_turns_on_saturday() -> None:
    assert day_start_ts(SAT_1000.timestamp()) == et(10, 17, 4).timestamp()


class FakeLive:
    def __init__(self, now: float) -> None:
        self.now = now

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True)

    def admission(self, symbol: str):
        return True, "OK", None

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return self.now


@pytest.fixture
def paper(monkeypatch):
    reset_for_tests()
    fake = FakeLive(et(10, 16, 10).timestamp())  # Friday 10:00 ET
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    broker = for_venue("paper")
    broker.place("IMCC", "BUY", 100, "MKT")
    broker.place("IMCC", "SELL", 100, "MKT")
    yield SimpleNamespace(broker=broker, ref=fake)
    reset_for_tests()


def test_paper_day_p_and_l_keeps_fridays_day_through_the_weekend(paper) -> None:
    friday = paper.broker.ledger.day_started_ts
    assert friday == et(10, 16, 4).timestamp()
    paper.ref.now = SAT_1000.timestamp()
    assert paper.broker.rollover() is False
    assert paper.broker.ledger.day_started_ts == friday
    paper.ref.now = MON_0030.timestamp()
    assert paper.broker.rollover() is False
    paper.ref.now = MON_1000.timestamp()
    assert paper.broker.rollover() is True
    assert paper.broker.ledger.day_started_ts == et(10, 19, 4).timestamp()


def test_a_weekend_rollover_an_older_build_stored_does_not_reset_the_day(paper) -> None:
    ledger = paper.broker.ledger
    friday = et(10, 16, 4).timestamp()
    ledger.events.append({"type": "rollover", "ts": et(10, 17, 4).timestamp(), "equity": 1.0, "wall_ts": 0.0})
    ledger.events.append({"type": "rollover", "ts": et(10, 18, 4).timestamp(), "equity": 1.0, "wall_ts": 0.0})
    ledger._derive()
    assert ledger.day_started_ts == friday
    ledger.events.append({"type": "rollover", "ts": et(10, 19, 4).timestamp(), "equity": 1.0, "wall_ts": 0.0})
    ledger._derive()
    assert ledger.day_started_ts == et(10, 19, 4).timestamp()


def test_paper_orders_today_lists_fridays_round_trip_on_saturday(paper) -> None:
    paper.ref.now = SAT_1000.timestamp()
    out = overlay_closed_orders(
        paper.broker.closed_orders(), ledger_rows=[], desk=DeskLedger(practice=True, mode="paper"),
    )
    assert [row["side"] for row in out] == ["SELL", "BUY"]
    paper.ref.now = MON_1000.timestamp()
    assert overlay_closed_orders(
        paper.broker.closed_orders(), ledger_rows=[], desk=DeskLedger(practice=True, mode="paper"),
    ) == []


def test_history_keys_saturday_to_fridays_row() -> None:
    assert history._day_of(SAT_1000.timestamp()) == "2026-10-16"
    assert history._day_of(MON_0030.timestamp()) == "2026-10-16"
    assert history._day_of(MON_1000.timestamp()) == "2026-10-19"


def test_the_loss_limit_still_turns_over_on_the_calendar_day(paper) -> None:
    """ADR 056's reset is a money gate: Saturday 04:00 starts a new count even though Day P&L reads Friday."""
    paper.ref.now = et(10, 16, 11).timestamp()
    assert [s["symbol"] for s in loss_accounts._practice("paper").stocks] == ["IMCC"]
    paper.ref.now = SAT_1000.timestamp()
    assert loss_accounts._practice("paper").stocks == []
    assert paper.broker.ledger.day_started_ts == et(10, 16, 4).timestamp()
