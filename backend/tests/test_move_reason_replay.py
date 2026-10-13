"""Why it's moving on a Sim replay desk: the replayed day is named and not read, never today's facts (ADR 028).

Verified 2026-10-12: the Sim on SDEV 2026-10-02 showed "Not a big move today (-3.9%)" -- the wall clock's
day. The replay here is a real historical window in a private Sim store (the IBKR download path).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from move_reason import facts as facts_mod
from sim import session_clock as clock
from sim.mode import set_venue
from tests.test_bot_sim_replay import DAY, SYM, go, load_window
from tests.test_sim_practice import isolated  # noqa: F401 -- autouse: a private Sim store and clean replay

client = TestClient(app)


def test_a_replay_desk_names_the_replayed_day_and_reads_nothing(monkeypatch):
    def today(*a, **k):
        raise AssertionError("today's facts were gathered on a replay desk")

    monkeypatch.setattr(facts_mod, "gather", today)
    set_venue("sim", persist=False)
    load_window()
    go(75)

    res = client.get(f"/api/why/{SYM.lower()}")

    assert res.status_code == 200
    body = res.json()
    assert (body["symbol"], body["replay"], body["session_date"]) == (SYM, True, DAY)
    assert body["generated_at"] == clock.now_et().timestamp()
    assert body["likely"]["kind"] == "not_read"
    assert body["likely"]["label"] == "Not read on a Sim replay of Sep 18"
    assert body["likely"]["detail"].startswith("Its facts are today's")
    assert body["checks"] == [] and body["facts"] == {}


def test_the_live_desk_still_reads(monkeypatch):
    seen = []

    def gather(symbol, now=None):
        seen.append(symbol)
        return {"symbol": symbol, "change_pct": 0.032}

    monkeypatch.setattr(facts_mod, "gather", gather)
    set_venue("paper", persist=False)

    body = client.get(f"/api/why/{SYM}").json()

    assert seen == [SYM] and body["replay"] is False
    assert body["likely"]["label"] == "Not a big move today (+3.2%)"
