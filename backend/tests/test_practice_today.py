"""Orders (Today) on a practice venue is the venue's practice day (QA W4, 2026-09-22).

The practice ledger keeps every closed order since its last reset; the blotter
listed all of them as "Orders . today", so the Working card said "Filled Today
10" beside three real fills. The day is the 04:00 ET rollover of the venue's
own clock -- the wall clock on Paper, the replay playhead on Sim.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from execution.closed_blotter import DeskLedger, overlay_closed_orders
from practice import broker as practice_broker
from practice import today
from practice.broker import for_venue, reset_for_tests
from sim.fill_model import Reference

NOW = 1_700_000_000.0  # Tue 2023-11-14 17:13:20 ET
DAY = 86_400.0


class FakeLive:
    def __init__(self) -> None:
        self.now = NOW

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
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake)
    reset_for_tests()


def test_yesterdays_orders_leave_the_paper_blotter_at_the_rollover(paper) -> None:
    paper.broker.place("IMCC", "BUY", 2, "MKT")
    paper.broker.place("IMCC", "BUY", 1, "LMT", limit_price=9.0)  # rests into tomorrow
    paper.ref.now = NOW + DAY
    paper.broker.place("IMCC", "SELL", 2, "MKT")
    closed = overlay_closed_orders(
        paper.broker.closed_orders(), ledger_rows=[], desk=DeskLedger(practice=True, mode="paper"),
    )
    assert [(row["side"], row["qty"]) for row in closed] == [("SELL", 2.0)]
    # The resting order is still working -- the working list is never day-scoped.
    assert [row["order_id"] for row in paper.broker.working_orders()] == [2]
    # The ledger itself keeps every row for history and the startup sweep.
    assert len(paper.broker.closed_orders()) == 2


def test_the_day_start_is_the_venues_clock(paper) -> None:
    paper.ref.now = NOW + DAY
    assert today.day_start("paper") == pytest.approx(NOW + DAY - (17 * 3600 + 13 * 60 + 20) + 4 * 3600)


def test_an_unreadable_clock_lists_every_row(monkeypatch) -> None:
    monkeypatch.setattr(today, "day_start", lambda _venue: None)
    rows = [{"order_id": 1, "updated_at": "2020-01-01T00:00:00+00:00"}]
    assert today.closed_today(rows, None, "paper") == rows


def test_iso_stamps_parse_with_or_without_z() -> None:
    assert today.iso_ts("2026-09-22T08:31:00Z") == today.iso_ts("2026-09-22T08:31:00+00:00")
    assert today.iso_ts("") is None and today.iso_ts(None) is None and today.iso_ts("not a time") is None
