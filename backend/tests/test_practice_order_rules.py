"""Per-order practice rules (operator decisions, 2026-09-21): TIF expiry arithmetic and the no-shorts test."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from constants_practice import (
    PRACTICE_SESSION_CLOSE_HOUR_ET,
    PRACTICE_TIF_DAY,
    PRACTICE_TIF_EXPIRED_CODE,
    PRACTICE_TIF_GTC,
    PRACTICE_TIFS,
)
from practice import order_rules
from practice.clock import ET
from practice.ledger import EVENT_EXPIRED, Ledger

MORNING = datetime(2026, 9, 21, 10, 0, tzinfo=ET)  # a Monday, well before the close
CLOSE = MORNING.replace(hour=PRACTICE_SESSION_CLOSE_HOUR_ET)


def test_the_practice_tifs_are_the_execution_commands_own() -> None:
    assert PRACTICE_TIFS == ("DAY", "GTC") and PRACTICE_TIF_DAY == "DAY" and PRACTICE_TIF_GTC == "GTC"


@pytest.mark.parametrize("raw, expected", [
    (None, "DAY"), ("", "DAY"), (" day ", "DAY"), ("gtc", "GTC"), ("GTC", "GTC"),
    ("IOC", None), ("GTD", None), ("OPG", None),
])
def test_normalize_tif_defaults_blank_to_day_and_refuses_what_nova_never_places(raw, expected) -> None:
    assert order_rules.normalize_tif(raw) == expected


def test_next_close_after_is_the_session_close_of_the_placement_day() -> None:
    assert order_rules.next_close_after(MORNING.timestamp()) == CLOSE.timestamp()
    one_second_before = CLOSE - timedelta(seconds=1)
    assert order_rules.next_close_after(one_second_before.timestamp()) == CLOSE.timestamp()


def test_an_order_placed_at_or_after_the_close_belongs_to_the_next_session() -> None:
    next_close = (CLOSE + timedelta(days=1)).timestamp()
    assert order_rules.next_close_after(CLOSE.timestamp()) == next_close
    late = CLOSE.replace(hour=23, minute=30)
    assert order_rules.next_close_after(late.timestamp()) == next_close
    small_hours = (CLOSE + timedelta(days=1)).replace(hour=2)
    assert order_rules.next_close_after(small_hours.timestamp()) == next_close


def test_next_close_is_an_eastern_wall_clock_across_the_dst_change() -> None:
    before = datetime(2026, 11, 1, 1, 0, tzinfo=ET)  # DST ends 2026-11-01 02:00 ET
    close = datetime.fromtimestamp(order_rules.next_close_after(before.timestamp()), ET)
    assert (close.hour, close.minute, close.date()) == (PRACTICE_SESSION_CLOSE_HOUR_ET, 0, before.date())


def test_expiry_ts_is_none_for_gtc_and_the_session_close_for_day() -> None:
    assert order_rules.expiry_ts("GTC", object(), MORNING.timestamp()) is None
    assert order_rules.expiry_ts("DAY", object(), MORNING.timestamp()) == CLOSE.timestamp()


def test_a_reference_that_knows_its_session_names_the_close() -> None:
    class Replay:
        def session_close_ts(self, ts: float) -> float:
            return ts + 60.0

    assert order_rules.session_close_ts(Replay(), 100.0) == 160.0
    assert order_rules.expiry_ts("DAY", Replay(), 100.0) == 160.0
    assert order_rules.session_close_ts(object(), MORNING.timestamp()) == CLOSE.timestamp()


@pytest.mark.parametrize("held, side, qty, short_entry, expected", [
    (0, "SELL", 1, False, True),       # short from flat
    (10, "SELL", 11, False, True),     # sells more than held
    (10, "SELL", 10, False, False),    # closes the position exactly
    (10, "SELL", 3, False, False),     # trims it
    (0, "BUY", 5, False, False),       # a buy is never a short
    (-5, "BUY", 5, False, False),      # covering a legacy short is a buy
    (-5, "SELL", 1, False, True),      # adding to a legacy short
    (100, "SELL", 1, True, True),      # short_entry is explicit and refused whatever is held
    (100, "BUY", 1, True, True),       # ... on any side
])
def test_opening_short_is_a_sell_beyond_the_held_quantity_or_an_explicit_short_entry(
    held, side, qty, short_entry, expected,
) -> None:
    assert order_rules.opening_short(held, side, qty, short_entry) is expected


def test_due_and_print_after_expiry_read_the_rows_expiry() -> None:
    row = {"expires_ts": 100.0}
    assert order_rules.due(row, 99.0) is False and order_rules.due(row, 100.0) is True
    assert order_rules.print_after_expiry(row, 100.0) is False
    assert order_rules.print_after_expiry(row, 100.5) is True
    gtc = {"expires_ts": None}
    assert order_rules.due(gtc, 1e12) is False and order_rules.print_after_expiry(gtc, 1e12) is False


def _row(oid: int, expires_ts: float | None) -> dict:
    return {
        "order_id": oid, "symbol": "IMCC", "side": "BUY", "qty": 1.0, "filled_qty": 0.0,
        "remaining_qty": 1.0, "order_type": "LMT", "limit_price": 9.0, "stop_price": None,
        "status": "Submitted", "placed_ts": 10.0, "source": "nova", "order_source": "manual",
        "bot_id": None, "tif": "GTC" if expires_ts is None else "DAY", "expires_ts": expires_ts,
    }


def test_expire_due_closes_only_the_due_day_orders_as_expired_events_stamped_at_their_close() -> None:
    ledger = Ledger(100_000, created_ts=MORNING.timestamp())
    ledger.place(_row(1, 100.0), ts=10.0, source="manual")
    ledger.place(_row(2, None), ts=10.0, source="manual")
    ledger.place(_row(3, 500.0), ts=10.0, source="manual")
    expired = order_rules.expire_due(ledger, 250.0)
    assert [(r["order_id"], r["status"], r["reason_code"]) for r in expired] == [(1, "Expired", PRACTICE_TIF_EXPIRED_CODE)]
    assert sorted(r["order_id"] for r in ledger.working_orders()) == [2, 3]
    event = ledger.events[-1]
    assert (event["type"], event["ts"], event["source"]) == (EVENT_EXPIRED, 100.0, order_rules.EXPIRY_SOURCE)
    assert order_rules.expire_due(ledger, 250.0) == []  # idempotent
