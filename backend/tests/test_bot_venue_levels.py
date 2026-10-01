"""The bot's level belongs to a venue (operator report 2026-09-30).

"When I switch between L0 and L2 in the paper, it stays persistent when I
switch to live, and I feel like that shouldn't happen."
"""
from __future__ import annotations

import json

import pytest

from bot import persist
from bot.arming import is_desk_active, issue_arm_token
from bot.audit import list_entries
from bot.autonomy import apply_patch
from bot.persist import load_session, save_session
from bot.session import get_session
from sim.mode import reset_for_tests as reset_venue, set_venue


@pytest.fixture
def paper():
    reset_venue()
    set_venue("paper", persist=False)
    yield
    reset_venue()


def _strategy_on_paper() -> None:
    apply_patch({"level": 2, "setup_levels": {"first_pullback": 2, "bull_flag": 1}}, desk=True)
    issue_arm_token()
    assert is_desk_active(load_session())


def test_papers_strategy_does_not_follow_the_desk_to_live(paper):
    _strategy_on_paper()
    set_venue("live", persist=False)
    view = get_session()
    assert view["level"] == 0 and view["armed"] is False and "strategy" not in view
    assert view["setup_levels"]["bull_flag"] == 0 and view["setup_levels"]["first_pullback"] == 0
    assert view["deactivated"]["reason"] == "venue"
    assert view["level_venue"] == "live"
    assert view["levels_by_venue"] == {"live": 0, "paper": 2, "sim": 0}


def test_coming_back_finds_the_level_but_not_active(paper):
    _strategy_on_paper()
    set_venue("live", persist=False)
    apply_patch({"level": 1}, desk=True)             # Eyes on Live is Live's own
    set_venue("paper", persist=False)
    view = get_session()
    assert view["level"] == 2 and view["armed"] is False
    assert view["setup_levels"]["bull_flag"] == 1
    assert view["levels_by_venue"] == {"live": 1, "paper": 2, "sim": 0}
    set_venue("live", persist=False)
    assert get_session()["level"] == 1


def test_the_switch_is_on_the_timeline(paper):
    _strategy_on_paper()
    set_venue("live", persist=False)
    [row] = [r for r in list_entries(limit=50) if r["action"] == "venue" and r["outcome"] == "paper->live"]
    assert row["outcome"] == "paper->live"
    assert row["inputs"] == {"from": "paper", "to": "live", "level_before": 2, "level_after": 0,
                             "deactivated": True}
    assert "Activate again" in row["reason"]


def test_the_same_venue_again_changes_nothing(paper):
    _strategy_on_paper()
    set_venue("paper", persist=False)
    view = get_session()
    assert view["level"] == 2 and view["armed"] is True


def test_an_old_session_belongs_to_the_venue_it_was_set_on(paper):
    row = load_session()
    row["level"] = 2
    row.pop("level_venue", None)
    save_session(row)
    set_venue("live", persist=False)
    assert get_session()["levels_by_venue"] == {"live": 0, "paper": 2, "sim": 0}


def test_a_restart_on_another_venue_takes_that_venues_level(paper):
    """The venue file changed while Nova was stopped: the session follows the desk."""
    _strategy_on_paper()
    reset_venue()
    set_venue("live", persist=False)                 # the desk starts on Live ...
    raw = json.loads((persist._session_path()).read_text(encoding="utf-8"))
    raw.update(level=2, level_venue="paper", armed=True, desk_arm_token="t")
    persist._session_path().write_text(json.dumps(raw), encoding="utf-8")
    persist._session = None                          # ... and reads a Paper session from disk
    row = load_session()
    assert row["level"] == 0 and row["level_venue"] == "live" and not is_desk_active(row)
    assert json.loads(persist._session_path().read_text(encoding="utf-8"))["level_venue"] == "live"


# -- the rest of the bot's state follows the venue too (audit, 2026-09-30) ------------------
async def _no_flatten(*, origin=None):
    return {"ok": True, "attempt": 1}


@pytest.mark.asyncio
async def test_a_bot_trip_on_paper_never_silences_lives(paper, monkeypatch):
    from bot.breakers import poll_once

    monkeypatch.setattr("bot.breakers.flatten_account_with_retry", _no_flatten)
    assert (await poll_once(pnl=-60.0))["tripped"] == "soft"          # Paper's trip
    assert get_session()["soft_breaker_fired"] is True
    set_venue("live", persist=False)
    assert get_session()["soft_breaker_fired"] is False
    assert (await poll_once(pnl=-60.0))["tripped"] == "soft"          # Live's own still fires
    set_venue("paper", persist=False)
    assert get_session()["soft_breaker_fired"] is True                # Paper's latch is Paper's


@pytest.mark.asyncio
async def test_a_bot_trip_latch_lapses_at_midnight(paper, monkeypatch):
    from bot.breakers import poll_once

    monkeypatch.setattr("bot.breakers.flatten_account_with_retry", _no_flatten)
    row = load_session()
    row.update(soft_breaker_fired=True, soft_breaker_until="2026-01-02")   # a trip from January
    save_session(row)
    assert get_session()["soft_breaker_fired"] is False
    assert (await poll_once(pnl=-60.0))["tripped"] == "soft"


@pytest.mark.asyncio
async def test_the_all_stop_trips_again_after_an_earlier_days_lock_lifted(paper, monkeypatch):
    from bot.breakers import poll_once

    monkeypatch.setattr("bot.breakers.flatten_account_with_retry", _no_flatten)
    row = load_session()
    row["hard_lock_until_date"] = "2026-01-02"                        # it tripped once, in January
    save_session(row)
    result = await poll_once(pnl=-250.0)
    assert result is not None and result["tripped"] == "hard"
    assert get_session()["day_lock_active"] is True


def test_the_daily_entry_cap_counts_this_venues_entries(paper):
    from bot.audit import record
    from bot.entry_rules import entries_today, venue_day

    record(action="buy_market", outcome="ok", inputs={"symbol": "ABCD", "venue_day": venue_day()})
    assert entries_today() == 1
    set_venue("live", persist=False)
    assert entries_today() == 0
    old = {"action": "buy_market", "outcome": "ok", "inputs": {"venue_day": venue_day()}}
    assert entries_today(rows=[old]) == 1                            # an unstamped row counts everywhere


@pytest.mark.asyncio
async def test_papers_working_order_is_never_cancelled_on_live(paper, monkeypatch):
    import bot.ttl as ttl
    from bot.risk import remember_working

    sent: list = []

    async def fake_execute(cmd, **_k):
        sent.append(cmd)
        raise AssertionError("a Paper order id reached the execution door on Live")

    monkeypatch.setattr("execution.service.execute", fake_execute)
    remember_working(order_id=12, symbol="ABCD", side="BUY", qty=1, price=2.0, kind="buy_limit_ask_offset",
                     ttl_sec=1)
    set_venue("live", persist=False)
    assert load_session()["working"] == []                            # Live's own list
    row = load_session()
    row["working"] = [{"order_id": 12, "symbol": "ABCD", "side": "BUY", "qty": 1, "price": 2.0,
                       "expire_ts": 1.0, "venue": "paper"}]                # left behind by an older build
    save_session(row)
    assert await ttl.cancel_due() == [] and sent == []
    set_venue("paper", persist=False)
    assert [w["order_id"] for w in load_session()["working"]] == [12]  # still Paper's to cancel


@pytest.mark.asyncio
async def test_papers_bot_trade_cannot_be_taken_over_on_live(paper):
    from bot.errors import BotError
    from bot.first_pullback.runner import hand_over

    row = load_session()
    row["trade"] = {"symbol": "ABCD", "venue": "paper", "state": "open", "qty": 10, "target_order_id": 12}
    save_session(row)
    set_venue("live", persist=False)
    with pytest.raises(BotError) as refused:
        await hand_over("ABCD")
    assert "is on paper" in refused.value.message
