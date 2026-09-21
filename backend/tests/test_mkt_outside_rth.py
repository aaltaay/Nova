"""Market orders need regular hours (operator decision, 2026-09-21).

No exchange takes an unpriced order outside 09:30-16:00 ET and IBKR holds an
RTH-only MKT until the next open, so Nova refuses a non-protective MKT on
every venue -- ``MKT_OUTSIDE_RTH`` at the execution door
(``execution.session_gate``) and again in ``PracticeBroker.place``
(``practice.order_rules.mkt_outside_rth``). The clock is the venue's: the
wall clock on Live and Paper, the replay playhead on Sim. The conftest pins
both checks open for the rest of the suite; these tests restore them.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from constants_nova_os import NOVA_OS_NYSE_HOLIDAYS
from constants_practice import MKT_OUTSIDE_RTH_CODE, MKT_OUTSIDE_RTH_REASON
from execution import practice_checks, session_gate
from execution.flatten_exit import flatten_needs_extended_hours_unpatched
from execution.models import ExecutionCommand
from execution.validate import validate_command
from ibkr import safety as _safety
from market import regular_hours_at
from practice import broker as practice_broker
from practice import order_rules
from practice.broker import for_venue, reset_for_tests
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

ET = ZoneInfo("America/New_York")


def et(y: int, m: int, d: int, hh: int, mm: int) -> dt.datetime:
    return dt.datetime(y, m, d, hh, mm, tzinfo=ET)


# 2026-09-21 is a Monday; 2026-09-19 a Saturday.
MONDAY_OPEN = et(2026, 9, 21, 10, 0)
MONDAY_AFTER = et(2026, 9, 21, 17, 10)


# ── the predicate ────────────────────────────────────────────────────────────

def test_regular_hours_is_weekday_0930_to_1600_et() -> None:
    assert regular_hours_at(et(2026, 9, 21, 9, 30))
    assert regular_hours_at(et(2026, 9, 21, 15, 59))
    assert not regular_hours_at(et(2026, 9, 21, 9, 29))
    assert not regular_hours_at(et(2026, 9, 21, 16, 0))
    assert not regular_hours_at(MONDAY_AFTER)
    assert not regular_hours_at(et(2026, 9, 19, 10, 30))  # Saturday


def test_a_weekday_nyse_holiday_is_not_regular_hours() -> None:
    holiday = next(h for h in sorted(NOVA_OS_NYSE_HOLIDAYS) if dt.date.fromisoformat(h).weekday() < 5)
    y, m, d = (int(x) for x in holiday.split("-"))
    assert not regular_hours_at(et(y, m, d, 10, 30))


def test_flatten_still_answers_from_the_same_clock() -> None:
    assert flatten_needs_extended_hours_unpatched(MONDAY_AFTER)
    assert not flatten_needs_extended_hours_unpatched(MONDAY_OPEN)


# ── the execution door ───────────────────────────────────────────────────────

@pytest.fixture
def real_gate(monkeypatch):
    """Restore the conftest-pinned clock and arm the desk (a venue change disarms, ADR 018)."""
    monkeypatch.setattr(session_gate, "regular_hours_now", session_gate.regular_hours_now_unpatched)
    reset_venue()
    yield
    reset_venue()


def _at(monkeypatch, when: dt.datetime) -> None:
    monkeypatch.setattr(session_gate, "venue_now_et", lambda: when)


def _cmd(**overrides) -> ExecutionCommand:
    fields = {
        "operation": "place", "idempotency_key": "mkt-rth", "source": "manual",
        "symbol": "GRML", "side": "BUY", "qty": 1, "order_type": "MKT",
    }
    fields.update(overrides)
    return ExecutionCommand(**fields)


def _on(venue: str) -> None:
    set_venue(venue)
    _safety.set_armed(True, reason="test")


def test_live_refuses_a_market_order_after_the_close(real_gate, monkeypatch) -> None:
    _on("live")
    _at(monkeypatch, MONDAY_AFTER)
    ok, detail, code = validate_command(_cmd())
    assert (ok, code) == (False, MKT_OUTSIDE_RTH_CODE)
    assert detail == MKT_OUTSIDE_RTH_REASON
    assert "use a limit at the ask" in detail


def test_live_refuses_a_market_order_premarket_and_on_a_weekend(real_gate, monkeypatch) -> None:
    _on("live")
    _at(monkeypatch, et(2026, 9, 21, 8, 0))
    assert validate_command(_cmd())[2] == MKT_OUTSIDE_RTH_CODE
    _at(monkeypatch, et(2026, 9, 19, 10, 30))
    assert validate_command(_cmd())[2] == MKT_OUTSIDE_RTH_CODE


def test_a_limit_order_after_the_close_is_not_the_gates_business(real_gate, monkeypatch) -> None:
    _on("live")
    _at(monkeypatch, MONDAY_AFTER)
    ok, _detail, code = validate_command(_cmd(order_type="LMT", limit_price=8.86))
    assert code != MKT_OUTSIDE_RTH_CODE


def test_a_market_order_in_regular_hours_passes_the_gate(real_gate, monkeypatch) -> None:
    _on("live")
    _at(monkeypatch, MONDAY_OPEN)
    assert validate_command(_cmd())[2] != MKT_OUTSIDE_RTH_CODE


@pytest.mark.parametrize("source", sorted(_safety.PROTECTIVE_SOURCES))
def test_protective_sources_may_still_send_a_market_close(real_gate, monkeypatch, source) -> None:
    _on("live")
    _at(monkeypatch, MONDAY_AFTER)
    assert validate_command(_cmd(source=source, side="SELL"))[2] != MKT_OUTSIDE_RTH_CODE


def test_a_bot_market_buy_after_hours_is_refused_like_the_operators(real_gate, monkeypatch) -> None:
    _on("live")
    _at(monkeypatch, MONDAY_AFTER)
    ok, detail, code = validate_command(_cmd(source="bot"))
    assert (ok, code) == (False, MKT_OUTSIDE_RTH_CODE)


# ── the venue's clock ────────────────────────────────────────────────────────

class _Ref:
    def __init__(self, now: dt.datetime) -> None:
        self.now = now.timestamp()

    def now_ts(self) -> float:
        return self.now

    def admission(self, symbol: str):
        return True, "OK", None


def _sim_broker(monkeypatch, playhead: dt.datetime) -> None:
    fake = SimpleNamespace(reference=_Ref(playhead))
    monkeypatch.setattr(practice_checks, "venue_broker", lambda: fake)


def test_sim_judges_by_the_playhead_not_the_wall_clock(real_gate, monkeypatch) -> None:
    _on("sim")
    monkeypatch.setattr(session_gate, "now_et", lambda: MONDAY_AFTER)  # wall clock: after the close
    _sim_broker(monkeypatch, MONDAY_OPEN)  # replay: 10:00
    assert validate_command(_cmd())[2] != MKT_OUTSIDE_RTH_CODE


def test_sim_refuses_a_market_order_when_the_replay_is_after_the_close(real_gate, monkeypatch) -> None:
    _on("sim")
    monkeypatch.setattr(session_gate, "now_et", lambda: MONDAY_OPEN)  # wall clock: regular hours
    _sim_broker(monkeypatch, MONDAY_AFTER)  # replay: 17:10
    assert validate_command(_cmd())[2] == MKT_OUTSIDE_RTH_CODE


def test_a_venue_without_a_clock_falls_back_to_wall_time_loudly(real_gate, monkeypatch, caplog) -> None:
    _on("sim")
    monkeypatch.setattr(session_gate, "now_et", lambda: MONDAY_AFTER)

    def broken():
        raise RuntimeError("nothing loaded")

    monkeypatch.setattr(practice_checks, "venue_broker", broken)
    with caplog.at_level("WARNING"):
        assert validate_command(_cmd())[2] == MKT_OUTSIDE_RTH_CODE
    assert "venue clock unavailable" in caplog.text


# ── the practice broker's own copy ───────────────────────────────────────────

class FakeLive:
    def __init__(self, now: dt.datetime) -> None:
        self.now = now.timestamp()

    def reference(self, symbol: str) -> Reference:
        return Reference(8.60, 8.58, 8.86, live=True)

    def admission(self, symbol: str):
        return True, "OK", None

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return self.now


@pytest.fixture
def paper(monkeypatch):
    monkeypatch.setattr(order_rules, "mkt_outside_rth", order_rules.mkt_outside_rth_unpatched)
    reset_venue()
    reset_for_tests()
    fake = FakeLive(MONDAY_AFTER)
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake)
    reset_for_tests()
    reset_venue()


def test_the_broker_refuses_an_after_hours_market_buy_and_never_fills_it(paper) -> None:
    out = paper.broker.place("GRML", "BUY", 1, order_type="MKT", source="manual")
    assert out.get("ok") is False
    assert out.get("reason_code") == MKT_OUTSIDE_RTH_CODE
    assert paper.broker.ledger.held_qty("GRML") == 0


def test_the_broker_fills_the_same_order_in_regular_hours(paper) -> None:
    paper.ref.now = MONDAY_OPEN.timestamp()
    out = paper.broker.place("GRML", "BUY", 1, order_type="MKT", source="manual")
    assert out.get("ok") is True
    assert paper.broker.ledger.held_qty("GRML") == 1


def test_the_broker_lets_a_protective_close_through_after_hours(paper) -> None:
    paper.ref.now = MONDAY_OPEN.timestamp()
    assert paper.broker.place("GRML", "BUY", 1, order_type="MKT", source="manual").get("ok") is True
    paper.ref.now = MONDAY_AFTER.timestamp()
    out = paper.broker.place("GRML", "SELL", 1, order_type="MKT", source="flatten", protective=True)
    assert out.get("ok") is True
    assert paper.broker.ledger.held_qty("GRML") == 0


def test_a_limit_after_hours_still_fills_on_the_broker(paper) -> None:
    out = paper.broker.place("GRML", "BUY", 1, order_type="LMT", limit_price=8.86, source="manual")
    assert out.get("ok") is True
