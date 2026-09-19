"""After-hours flatten planner -- never RTH-only MKT off weekday RTH."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from execution import flatten_exit as fe
from execution.flatten_exit import (
    FLATTEN_EH_NO_MARK,
    flatten_needs_extended_hours_unpatched,
    flatten_sweep_limit,
    plan_flatten_exit,
    ticket_to_command_fields,
)


@pytest.fixture(autouse=True)
def _real_flatten_clock(monkeypatch):
    monkeypatch.setattr(
        fe,
        "flatten_needs_extended_hours",
        flatten_needs_extended_hours_unpatched,
    )

ET = ZoneInfo("America/New_York")
# Friday 2026-09-18 10:30 ET -- weekday RTH.
RTH_FRIDAY = datetime(2026, 9, 18, 10, 30, tzinfo=ET)
# Saturday 10:30 ET looks like clock-RTH if weekday is ignored.
SATURDAY_CLOCK_RTH = datetime(2026, 9, 19, 10, 30, tzinfo=ET)
# Friday after the close.
AH_FRIDAY = datetime(2026, 9, 18, 17, 0, tzinfo=ET)
# Independence Day observed -- weekday clock-RTH on a holiday.
HOLIDAY_CLOCK_RTH = datetime(2026, 7, 3, 10, 30, tzinfo=ET)


def test_weekday_rth_stays_market_inside_rth():
    assert flatten_needs_extended_hours_unpatched(RTH_FRIDAY) is False
    ticket = plan_flatten_exit("SELL", now=RTH_FRIDAY, bid=10.0)
    assert ticket.ok is True
    assert ticket.order_type == "MKT"
    assert ticket.outside_rth is False
    assert ticket.limit_price is None
    assert ticket_to_command_fields(ticket) == {
        "order_type": "MKT",
        "outside_rth": False,
        "limit_price": None,
    }


def test_saturday_clock_rth_is_extended():
    assert flatten_needs_extended_hours_unpatched(SATURDAY_CLOCK_RTH) is True
    ticket = plan_flatten_exit("SELL", now=SATURDAY_CLOCK_RTH, bid=9.5, last=9.6)
    assert ticket.ok is True
    assert ticket.order_type == "LMT"
    assert ticket.outside_rth is True
    assert ticket.limit_price == 9.5
    assert ticket.quote_source == "bid"


def test_after_hours_sell_hits_bid_buy_hits_ask():
    sell = plan_flatten_exit("SELL", now=AH_FRIDAY, bid=10.0, ask=10.2, last=10.1)
    assert sell.ok is True
    assert sell.order_type == "LMT"
    assert sell.outside_rth is True
    assert sell.limit_price == 10.0
    buy = plan_flatten_exit("BUY", now=AH_FRIDAY, bid=10.0, ask=10.2, last=10.1)
    assert buy.ok is True
    assert buy.limit_price == 10.2
    assert buy.quote_source == "ask"


def test_holiday_clock_rth_falls_back_to_last():
    assert flatten_needs_extended_hours_unpatched(HOLIDAY_CLOCK_RTH) is True
    ticket = plan_flatten_exit("SELL", now=HOLIDAY_CLOCK_RTH, last=4.25)
    assert ticket.ok is True
    assert ticket.order_type == "LMT"
    assert ticket.outside_rth is True
    assert ticket.limit_price == 4.25
    assert ticket.quote_source == "last"


def test_after_hours_without_mark_refuses_rth_mkt():
    ticket = plan_flatten_exit("SELL", now=AH_FRIDAY)
    assert ticket.ok is False
    assert ticket.error == FLATTEN_EH_NO_MARK
    assert ticket.outside_rth is True


def test_sweep_ignores_non_positive_quotes():
    assert flatten_sweep_limit("SELL", bid=0, ask=1, last=-1) is None
    assert flatten_sweep_limit("SELL", bid=None, last=3.5) == (3.5, "last")
