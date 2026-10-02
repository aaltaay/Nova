"""The loss breakers -- flatten mocked, no live IBKR.

The bot trip and the all-stop compare the desk venue's day P&L with that venue's own lines, write
their record on that venue's dial, lock buys on that venue only, lift at the next 04:00 ET and
compare nothing on a Sim replay (spec D, 2026-09-30).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot import clock
from bot.arming import issue_arm_token
from bot.autonomy import apply_desk_level, apply_patch
from bot.breakers import poll_once, trip_hard, trip_soft
from bot.buy_lock import buy_blocked, buy_refusal, day_lock_active, day_locks, lock_for
from bot.persist import load_session, save_session
from sim.mode import reset_for_tests as reset_venue, set_venue

ET = ZoneInfo("America/New_York")


@pytest.fixture
def flattens(monkeypatch):
    calls: list[int] = []

    async def fake_flatten(*, origin=None):
        calls.append(1)
        return {"ok": True, "attempt": 1}

    monkeypatch.setattr("bot.breakers.flatten_account_with_retry", fake_flatten)
    return calls


@pytest.fixture
def at():
    """Pin the breakers' clock: ``at(datetime)``."""
    def pin(moment: datetime) -> None:
        clock.set_clock_for_tests(lambda: moment)
    yield pin
    clock.set_clock_for_tests(None)


@pytest.fixture
def paper():
    reset_venue()
    set_venue("paper", persist=False)
    yield
    reset_venue()


@pytest.mark.asyncio
async def test_soft_breaker_flattens_latches_and_keeps_its_record(flattens, at):
    at(datetime(2026, 9, 30, 10, 42, tzinfo=ET))
    apply_desk_level(2)
    row = load_session()
    row["bot_qty"] = {"ABCD": 1}
    row["working"] = [{"order_id": 1, "side": "BUY", "qty": 1, "price": 2.0}]
    save_session(row)
    result = await trip_soft(pnl=-61.5)
    assert result["tripped"] == "soft"
    assert flattens == [1]
    row = load_session()
    assert row["level"] == 1                     # ADR 043: the bot is off, Eyes keep proposing
    assert row["armed"] is False and row["deactivated"]["reason"] == "bot_trip"
    assert row["soft_breaker_fired"] is True
    assert row["soft_breaker_until"] == "2026-10-01T04:00:00-04:00"
    assert row["soft_breaker_pnl"] == -61.5 and row["soft_breaker_usd"] == -50.0
    assert row["soft_breaker_at"] == pytest.approx(datetime(2026, 9, 30, 10, 42, tzinfo=ET).timestamp(), abs=5)
    assert row["hard_lock_until_date"] is None
    assert row["bot_qty"] == {}
    assert row["working"] == []
    assert await poll_once(pnl=-60.0) is None


@pytest.mark.asyncio
async def test_hard_breaker_locks_buys_until_4am_with_its_own_words(flattens, at):
    at(datetime(2026, 9, 30, 10, 42, tzinfo=ET))
    apply_desk_level(2)
    result = await trip_hard(pnl=-212.4)
    assert result["tripped"] == "hard"
    row = load_session()
    assert row["level"] == 1                     # ADR 043: off at Eyes, not Off
    assert row["armed"] is False and row["deactivated"]["reason"] == "all_stop"
    assert row["hard_lock_until_date"] == "2026-10-01T04:00:00-04:00"
    assert row["hard_lock_pnl"] == -212.4 and row["hard_lock_usd"] == -200.0
    assert day_lock_active() is True
    blocked, reason = buy_blocked("BUY", "manual")
    assert (blocked, reason) == (True, "BOT_DAY_LOCK")
    assert buy_blocked("BUY", "flatten")[0] is False
    assert buy_blocked("SELL", "manual")[0] is False
    text = buy_refusal("BUY", "manual")["text"]
    assert "tripped at 10:42 ET" in text and "-$212.40" in text and "-$200" in text
    assert "until 04:00 ET Thu Oct 1" in text
    assert buy_refusal("SELL", "manual", short_entry=True) is not None   # a short entry adds exposure too


@pytest.mark.asyncio
async def test_poll_prefers_hard_when_both(monkeypatch):
    apply_desk_level(2)
    seen = []

    async def fake_hard(**kwargs):
        seen.append(("hard", kwargs))
        return {"tripped": "hard"}

    async def fake_soft(**kwargs):
        seen.append(("soft", kwargs))
        return {"tripped": "soft"}

    monkeypatch.setattr("bot.breakers.trip_hard", fake_hard)
    monkeypatch.setattr("bot.breakers.trip_soft", fake_soft)
    out = await poll_once(pnl=-250.0)
    assert out["tripped"] == "hard"
    assert [name for name, _ in seen] == ["hard"]
    assert seen[0][1]["pnl"] == -250.0


@pytest.mark.asyncio
async def test_soft_reenable_allows_l2_again(flattens):
    apply_desk_level(2)
    await trip_soft()
    token = issue_arm_token()
    apply_patch({"reenable": True, "level": 2}, desk=True, arm_token=token)
    row = load_session()
    assert row["soft_breaker_fired"] is False
    assert row["level"] == 2
    again = await poll_once(pnl=-60.0)
    assert again is not None
    assert again["tripped"] == "soft"


@pytest.mark.asyncio
async def test_no_second_trip_between_midnight_and_4am(paper, flattens, at):
    """The regression: yesterday's practice day P&L, read after midnight, never trips again.

    The lock lifted at midnight, so between 00:00 and 04:00 the practice DayPnL (it rolls at
    04:00) was still past the line and the all-stop tripped a second time: a second flatten,
    the bot to Off and a lock on the whole new day.
    """
    apply_desk_level(2)
    at(datetime(2026, 9, 29, 15, 0, tzinfo=ET))
    assert (await poll_once(pnl=-250.0))["tripped"] == "hard"
    assert flattens == [1]
    for hour, minute in ((0, 0), (0, 30), (2, 15), (3, 59)):
        at(datetime(2026, 9, 30, hour, minute, tzinfo=ET))
        assert await poll_once(pnl=-250.0) is None                   # still yesterday's practice day
        assert await poll_once(pnl=-75.0) is None                    # nor the bot trip
        assert day_lock_active() is True
    assert flattens == [1]
    at(datetime(2026, 9, 30, 4, 0, tzinfo=ET))
    assert day_lock_active() is False                                # lifted with the practice day
    assert await poll_once(pnl=0.0) is None                          # and the new day starts flat
    assert flattens == [1]


@pytest.mark.asyncio
async def test_papers_all_stop_locks_paper_only(paper, flattens, at, monkeypatch):
    """#658 item 1, option b: the lock is the venue's own, and switching away and back keeps it."""
    at(datetime(2026, 9, 30, 10, 0, tzinfo=ET))
    apply_desk_level(2)
    assert (await poll_once(pnl=-250.0))["tripped"] == "hard"
    row = load_session()
    assert lock_for(row, "paper")["active"] is True
    assert lock_for(row, "live")["active"] is False
    assert buy_blocked("BUY", "manual", "paper")[0] is True
    # A lock read from a stored dial: Live's own, as the venue change keeps them (bot.venue_levels).
    row["venue_levels"] = {"live": {"hard_lock_until_date": "2026-10-01T04:00:00-04:00", "hard_lock_at": 1.0,
                                    "hard_lock_pnl": -900.0, "hard_lock_usd": -500.0}}
    locks = day_locks(row)
    assert locks["live"]["active"] is True and locks["live"]["pnl"] == -900.0
    assert "Live's all-stop" in locks["live"]["text"] and "-$500" in locks["live"]["text"]
    assert locks["sim"]["active"] is False and locks["sim"]["text"] is None


@pytest.mark.asyncio
async def test_a_sim_replay_compares_nothing(flattens, monkeypatch):
    """Sim off the live edge: a replay's P&L is not today's -- no trip, and the view says so."""
    from bot.breaker_limits import REPLAY_NOTE, view

    reset_venue()
    try:
        set_venue("sim", persist=False)                 # the conftest pins the live edge off: a replay
        apply_desk_level(2)
        assert await poll_once(pnl=-5000.0) is None
        assert flattens == []
        assert view(load_session(), "sim")["note"] == REPLAY_NOTE
        monkeypatch.setattr("sim.session_clock.live_edge", lambda: True)   # at the live edge: as on Paper
        assert (await poll_once(pnl=-250.0))["tripped"] == "hard"
        assert view(load_session(), "sim")["note"] is None
        assert view(load_session(), "paper")["note"] is None
    finally:
        reset_venue()


def test_an_unreadable_session_counts_as_locked_and_says_why(monkeypatch):
    def broken():
        raise ValueError("bot-session.json schema_version=99")

    monkeypatch.setattr("bot.persist.load_session", broken)
    assert day_lock_active("paper") is True
    refusal = buy_refusal("BUY", "manual", "paper")
    assert refusal is not None and "could not read the bot session" in refusal["text"]
    assert "schema_version=99" in refusal["text"]
    assert buy_refusal("BUY", "flatten", "paper") is None


@pytest.mark.asyncio
async def test_flatten_retry_then_alert(monkeypatch):
    from bot.flatten import alert_flatten_failed, flatten_account_with_retry

    calls = {"n": 0}

    async def once(*, origin=None):
        calls["n"] += 1
        return {"ok": False, "error": "nope", "results": []}

    monkeypatch.setattr("bot.flatten.flatten_account_once", once)
    last = await flatten_account_with_retry()
    assert last["ok"] is False
    assert calls["n"] == 2
    alerts = []
    monkeypatch.setattr("alerts.dispatch.dispatch_alert", lambda payload: alerts.append(payload))
    alert_flatten_failed({"error": "nope"})
    assert alerts
    assert "flatten failed" in alerts[0]["text"].lower()
