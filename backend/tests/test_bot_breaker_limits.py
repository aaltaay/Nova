"""The loss breakers' thresholds are the operator's, per venue, and they survive a restart
(operator ask 2026-09-24: "move that slider ... make sure these changes are persistent")."""
from __future__ import annotations

import json

import pytest

from bot import persist
from bot.audit import list_entries
from bot.autonomy import apply_desk_level, apply_patch
from bot.breaker_limits import limits, view
from bot.breakers import poll_once
from bot.errors import BotError
from bot.persist import load_session
from bot.session import get_session
from constants_bot import BOT_REASON_BREAKER_INVALID
from sim.mode import reset_for_tests as reset_venue, set_venue


@pytest.fixture
def paper():
    reset_venue()
    set_venue("paper")
    yield
    reset_venue()


def test_every_venue_starts_on_the_defaults():
    row = load_session()
    for venue in ("live", "paper", "sim", None, "moon"):
        assert limits(row, venue) == {"soft_usd": -50.0, "hard_usd": -200.0}
    v = view(row, "paper")
    assert v["venue"] == "paper" and v["custom"] is False
    assert v["bounds"]["soft_usd"] == [-1000.0, -5.0] and v["bounds"]["hard_usd"] == [-5000.0, -10.0]


def test_moving_papers_bot_trip_leaves_live_where_it_was(paper):
    apply_patch({"breakers": {"soft_usd": -100}}, desk=True)
    row = load_session()
    assert limits(row, "paper") == {"soft_usd": -100.0, "hard_usd": -200.0}
    assert limits(row, "live") == {"soft_usd": -50.0, "hard_usd": -200.0}
    assert get_session()["breakers"]["soft_usd"] == -100.0 and get_session()["breakers"]["custom"] is True
    [line] = [r for r in list_entries(limit=20) if r["action"] == "breakers"]
    assert line["outcome"] == "paper" and "bot trip -50 -> -100" in line["reason"]


def test_a_named_venue_is_the_one_changed(paper):
    apply_patch({"breakers": {"venue": "live", "soft_usd": -25, "hard_usd": -100}}, desk=True)
    row = load_session()
    assert limits(row, "live") == {"soft_usd": -25.0, "hard_usd": -100.0}
    assert limits(row, "paper") == {"soft_usd": -50.0, "hard_usd": -200.0}


def test_values_snap_to_five_dollars(paper):
    apply_patch({"breakers": {"soft_usd": -72.4}}, desk=True)
    assert limits(load_session(), "paper")["soft_usd"] == -70.0


@pytest.mark.parametrize("patch, words", [
    ({"soft_usd": -2000}, "bot trip is between"),
    ({"soft_usd": 10}, "bot trip is between"),
    ({"hard_usd": -9000}, "all-stop is between"),
    ({"soft_usd": -300}, "above the all-stop"),                   # under the -200 all-stop
    ({"soft_usd": -150, "hard_usd": -100}, "above the all-stop"),
    ({"soft_usd": "a lot"}, "dollar amount"),
    ({"venue": "moon", "soft_usd": -60}, "per venue"),
])
def test_a_threshold_out_of_bounds_is_refused_by_name(paper, patch, words):
    with pytest.raises(BotError) as refused:
        apply_patch({"breakers": patch}, desk=True)
    assert refused.value.reason == BOT_REASON_BREAKER_INVALID and words in refused.value.message
    assert limits(load_session(), "paper") == {"soft_usd": -50.0, "hard_usd": -200.0}


@pytest.mark.asyncio
async def test_the_breaker_poll_reads_the_venues_own_thresholds(paper, monkeypatch):
    apply_desk_level(2)
    apply_patch({"breakers": {"soft_usd": -100}}, desk=True)
    tripped: list[str] = []

    async def fake_soft(*_a, **_k):
        tripped.append("soft")
        return {"tripped": "soft"}

    async def fake_hard(*_a, **_k):
        tripped.append("hard")
        return {"tripped": "hard"}

    monkeypatch.setattr("bot.breakers.trip_soft", fake_soft)
    monkeypatch.setattr("bot.breakers.trip_hard", fake_hard)
    assert await poll_once(pnl=-60.0) is None              # past the old -50, inside the new -100
    assert (await poll_once(pnl=-101.0))["tripped"] == "soft"
    assert (await poll_once(pnl=-201.0))["tripped"] == "hard"
    set_venue("live")                                       # Live still trips at -50
    assert (await poll_once(pnl=-60.0))["tripped"] == "soft"


def test_the_thresholds_survive_a_restart(paper):
    apply_patch({"breakers": {"soft_usd": -120, "hard_usd": -400}, "caps": {"max_shares": 3}}, desk=True)
    path = persist._session_path()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["breakers"]["paper"] == {"soft_usd": -120.0, "hard_usd": -400.0}
    persist._session = None                                 # a fresh process reads the file
    row = load_session()
    assert limits(row, "paper") == {"soft_usd": -120.0, "hard_usd": -400.0}
    assert row["caps"]["max_shares"] == 3
    assert not path.with_suffix(path.suffix + ".tmp").exists()   # written through a rename


def test_a_damaged_threshold_on_disk_reads_the_defaults(paper):
    row = load_session()
    row["breakers"] = {"paper": {"soft_usd": -500, "hard_usd": -100}, "live": "junk"}   # soft under hard
    persist.save_session(row)
    persist._session = None
    assert limits(load_session(), "paper") == {"soft_usd": -50.0, "hard_usd": -200.0}


def test_moving_back_onto_the_defaults_forgets_the_venues_pair(paper):
    apply_patch({"breakers": {"soft_usd": -100}}, desk=True)
    assert get_session()["breakers"]["custom"] is True
    apply_patch({"breakers": {"soft_usd": -50, "hard_usd": -200}}, desk=True)
    view_now = get_session()["breakers"]
    assert view_now["custom"] is False and view_now["soft_usd"] == -50.0
    assert "paper" not in (load_session().get("breakers") or {})
