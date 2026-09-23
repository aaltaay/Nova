"""Sim moves to another day with nothing loaded; the board's date menu and HOD history (ADR 023)."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sim import session_clock
from sim.routes import router as sim_router

ET = ZoneInfo("America/New_York")


@pytest.fixture
def client(monkeypatch):
    from sim.mode import set_venue

    session_clock.reset_for_tests()
    set_venue("sim", persist=False)
    app = FastAPI()
    app.include_router(sim_router)
    with TestClient(app) as c:
        yield c
    session_clock.reset_for_tests()
    set_venue("paper", persist=False)


def test_moving_to_a_past_day_parks_paused_at_seven(client):
    out = client.post("/api/sim/clock", json={"session_date": "2026-09-18"}).json()
    assert out["session_date"] == "2026-09-18" and out["paused"] is True
    assert datetime.fromisoformat(out["sim_time_et"]).strftime("%H:%M") == "07:00"
    assert out["live_edge"] is False and out["replay_source"] == "none"
    # Scrubbing on that day stays on that day.
    moved = client.post("/api/sim/clock", json={"minute_from_open": 4 * 60}).json()
    assert moved["session_date"] == "2026-09-18"
    assert datetime.fromisoformat(moved["sim_time_et"]).strftime("%H:%M") == "08:00"


def test_null_returns_to_today(client):
    client.post("/api/sim/clock", json={"session_date": "2026-09-18"})
    out = client.post("/api/sim/clock", json={"session_date": None}).json()
    assert out["paused"] is False and out["scrubbed"] is False
    assert out["session_date"] != "2026-09-18" or datetime.now(ET).date().isoformat() == "2026-09-18"


@pytest.mark.parametrize("day, why", [
    ("2026-09-19", "exchange day"),   # a Saturday
    ("2099-01-02", ""),               # outside the calendar or in the future
    ("not-a-date", ""),
])
def test_a_day_the_desk_cannot_open_is_422(client, day, why):
    res = client.post("/api/sim/clock", json={"session_date": day})
    assert res.status_code == 422 and why in res.json()["detail"]


def test_moving_to_another_day_needs_sim(client):
    from sim.mode import set_venue

    set_venue("paper", persist=False)
    assert client.post("/api/sim/clock", json={"session_date": "2026-09-18"}).status_code == 409


def _loaded(monkeypatch, date: str, source: str = "historical") -> list:
    from sim import replay

    calls: list = []
    monkeypatch.setattr(replay, "status_payload", lambda: {"replay_date": date, "replay_source": source})
    monkeypatch.setattr(replay, "set_replay", lambda d, s, **_k: calls.append((d, s)) or {})
    return calls


def test_moving_days_unloads_a_replay_of_another_date(client, monkeypatch):
    calls = _loaded(monkeypatch, "2026-09-17", "capture")
    client.post("/api/sim/clock", json={"session_date": "2026-09-18"})
    assert calls == [(None, None)]


def test_picking_the_loaded_replays_own_day_opens_the_whole_day(client, monkeypatch):
    # A download of SPY 06:45-09:00 on Sep 18 narrowed the clock; picking Sep 18
    # in the calendar means "watch the whole day", so it is unloaded (not deleted).
    calls = _loaded(monkeypatch, "2026-09-18")
    out = client.post("/api/sim/clock", json={"session_date": "2026-09-18"}).json()
    assert calls == [(None, None)]
    assert datetime.fromisoformat(out["session_open_et"]).strftime("%H:%M") == "04:00"
    assert datetime.fromisoformat(out["session_close_et"]).strftime("%H:%M") == "20:00"


def test_returning_to_today_keeps_todays_own_replay(client, monkeypatch):
    today = datetime.now(ET).date().isoformat()
    calls = _loaded(monkeypatch, today, "capture")
    client.post("/api/sim/clock", json={"session_date": None})
    assert calls == []


def _write_snapshot(cache_dir, prefix, day, key, rows):
    (cache_dir / f"{prefix}-{day}.json").write_text(json.dumps({"date": day, key: rows, "schema_version": 1}))


def test_history_dates_list_every_board_and_read_the_split_movers(tmp_path, monkeypatch):
    import cache

    root = tmp_path / "hist"
    root.mkdir()
    monkeypatch.setattr(cache, "_CACHE_DIR", str(root))
    monkeypatch.setattr(cache, "accept_schema", lambda data, *_a, **_k: data)
    _write_snapshot(root, "gappers", "2026-09-10", "gappers", [{"symbol": "G"}])
    _write_snapshot(root, "gainers", "2026-09-11", "gainers", [{"symbol": "W"}])
    _write_snapshot(root, "losers", "2026-09-14", "losers", [{"symbol": "L"}])
    _write_snapshot(root, "afterhours", "2026-09-15", "afterhours", [])  # empty: not offered
    assert cache.list_history_dates("gappers") == ["2026-09-10"]
    assert cache.list_history_dates("movers") == ["2026-09-14", "2026-09-11"]
    assert cache.list_history_dates("all") == ["2026-09-14", "2026-09-11", "2026-09-10"]


def test_hod_history_until_keeps_only_alerts_raised_by_then():
    from hod_momo_history_filter import raised_by

    t0 = datetime(2026, 9, 18, 7, 0, tzinfo=ET).timestamp()
    alerts = [
        {"id": "a", "created_ts": t0},
        {"id": "b", "created_ts": t0 + 120},
        {"id": "c", "timestamp": datetime(2026, 9, 18, 7, 1, tzinfo=ET).isoformat()},
        {"id": "d"},  # no time of its own: never shown as if it had happened
        "junk",
    ]
    assert [a["id"] for a in raised_by(alerts, t0 + 60)] == ["a", "c"]
