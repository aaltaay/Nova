"""The brain turns itself On each trading morning (ADR 072 Amendment 2, ``traders.md`` "The switches")."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from brain import session, watcher
from traders import switches, view, wake

ET = ZoneInfo("America/New_York")


def at(clock: str, day: str = "2026-11-13") -> float:
    """A clock time on a day (default Friday 2026-11-13) as the desk's timestamp."""
    return datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=ET).timestamp()


@pytest.fixture
def desk(monkeypatch):
    """The desk on a venue a test may change; the brain's schedule as shipped (no ``.env`` word)."""
    from sim import mode

    place = {"venue": "paper"}
    monkeypatch.setattr(mode, "venue", lambda: place["venue"])
    monkeypatch.delenv("NOVA_BRAIN_WAKES", raising=False)
    session.reset_for_tests()
    return place


def test_the_brain_turns_on_at_0400_on_a_trading_day_and_claude_does_not(desk) -> None:
    assert wake.run_pass(at("03:59")) == []                    # 03:59 still belongs to Thursday's desk day
    assert not switches.is_on("brain", at("03:59"))
    assert wake.run_pass(at("04:00")) == ["brain"]
    state, _ = switches.current(at("04:00"))
    assert state["brain"] == {"on": True, "at": at("04:00"), "by": "schedule"}
    assert state["claude"] == {"on": False, "at": None, "by": None}
    assert [e["kind"] for e in session.events(at("04:01"))] == ["switch_on"]
    assert wake.run_pass(at("04:00:05")) == []                 # once a day
    assert len(session.events(at("04:01"))) == 1


def test_your_off_holds_until_the_next_trading_morning(desk) -> None:
    wake.run_pass(at("04:00"))
    switches.set_switch("brain", False, "you", at("09:00"))
    assert wake.run_pass(at("09:00:05")) == [] and wake.run_pass(at("15:00")) == []
    assert wake.run_pass(at("10:00", "2026-11-14")) == []      # Saturday
    assert wake.run_pass(at("10:00", "2026-11-15")) == []      # Sunday
    assert not switches.is_on("brain", at("03:59", "2026-11-16"))
    assert wake.run_pass(at("04:00", "2026-11-16")) == ["brain"]    # Monday: the schedule is honoured again
    assert switches.is_on("brain", at("04:01", "2026-11-16"))


def test_a_press_of_yours_before_the_wake_is_the_last_word_that_day(desk) -> None:
    desk["venue"] = "live"
    assert wake.run_pass(at("04:00")) == []                    # On is refused on Live
    desk["venue"] = "paper"
    switches.set_switch("brain", True, "you", at("08:00"))
    switches.set_switch("brain", False, "you", at("08:30"))
    assert wake.run_pass(at("08:31")) == []
    assert switches.turn_on_untouched("brain", "schedule", at("08:32")) is None
    assert not switches.is_on("brain", at("08:33"))


def test_no_weekend_and_no_holiday_wakes_it(desk) -> None:
    assert wake.run_pass(at("10:00", "2026-11-14")) == []      # Saturday, a fresh desk
    assert wake.run_pass(at("10:00", "2026-11-26")) == []      # Thanksgiving
    assert not switches.is_on("brain", at("10:01", "2026-11-26"))
    assert wake.run_pass(at("04:00", "2026-11-27")) == ["brain"]


def test_it_wakes_at_the_first_moment_on_is_not_refused(desk) -> None:
    desk["venue"] = "live"
    assert wake.run_pass(at("04:00")) == [] and wake.run_pass(at("09:00")) == []
    desk["venue"] = "paper"
    assert wake.run_pass(at("09:00:05")) == ["brain"]          # the desk came back to Paper, the switch untouched


def test_a_desk_first_started_past_flat_by_stays_off(desk) -> None:
    assert wake.run_pass(at("15:55")) == [] and wake.run_pass(at("19:00")) == []
    code, words = switches.on_refusal("brain", at("15:55"))
    assert code == "TRADER_PAST_FLAT_BY"
    assert words == "It is past the brain's flat-by time (15:55 ET): it turns On by itself the next trading morning."
    assert switches.on_refusal("claude", at("15:55"))[1].endswith("it can turn On tomorrow.")


def test_the_env_word_ends_the_schedule_and_the_view_says_which(desk, monkeypatch) -> None:
    assert view.snapshot(at("03:00"))["traders"]["brain"]["wakes"] is True
    assert "wakes" not in view.snapshot(at("03:00"))["traders"]["claude"]
    monkeypatch.setenv("NOVA_BRAIN_WAKES", "0")
    assert wake.run_pass(at("04:00")) == [] and not switches.is_on("brain", at("04:01"))
    assert view.snapshot(at("04:01"))["traders"]["brain"]["wakes"] is False
    assert switches.on_refusal("brain", at("15:55"))[1].endswith("it can turn On tomorrow.")


def test_the_brains_watcher_runs_the_wake_and_survives_its_failure(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(wake, "run_pass", lambda: calls.append(1))
    watcher._wake()
    assert calls == [1]

    def boom():
        raise RuntimeError("the switches file is locked")

    monkeypatch.setattr(wake, "run_pass", boom)
    watcher._wake()                                            # logged, never raised: the next pass tries again
