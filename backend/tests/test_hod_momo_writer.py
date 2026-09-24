"""HOD Momo's disk writer: the hot paths never write on a loop, and nothing a
forced save or the rollover archive writes is overtaken by a queued snapshot (#553)."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time

import pytest

import cache as cache_mod
import hod_momo as hm
import hod_momo_alerts as alerts
import hod_momo_persist as persist
import hod_momo_session as session
import hod_momo_writer as writer
from constants import HOD_MOMO_ALERTS_PREFIX, HOD_MOMO_HIGHS_PREFIX
from hod_momo_state import HodMomoState


def _alert(alert_id: str, created_ts: float = 0.0) -> hm.AlertObject:
    return hm.AlertObject(
        id=alert_id,
        timestamp="2026-07-15T14:00:00Z",
        ticker="SOBR",
        strategy_id=12,
        strategy_name="Running Up",
        price=1.0,
        change_pct=1.0,
        rvol=2.0,
        float_shares=1e6,
        gap_pct=None,
        volume=1,
        momentum_pct=None,
        created_ts=created_ts,
    )


def _on_disk(prefix: str, date: str) -> dict | None:
    try:
        with open(cache_mod._dated_path(prefix, date), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _alert_ids(date: str) -> list[str] | None:
    data = _on_disk(HOD_MOMO_ALERTS_PREFIX, date)
    return None if data is None else [row["id"] for row in data["alerts"]]


@pytest.fixture
def write_threads(monkeypatch) -> list[int]:
    """The thread of every ``cache._atomic_write`` call (the write still happens)."""
    seen: list[int] = []
    original = cache_mod._atomic_write

    def _recording(path, payload):
        seen.append(threading.get_ident())
        original(path, payload)

    monkeypatch.setattr(cache_mod, "_atomic_write", _recording)
    return seen


@pytest.fixture
def gate():
    """Holds the writer thread on a job until set, so a snapshot stays queued."""
    held = threading.Event()
    writer.submit("gate", "test", lambda: held.wait(5.0))
    yield held
    held.set()


@pytest.fixture
def day(monkeypatch) -> list[str]:
    """The session key HOD Momo's files are named by; tests move it."""
    today = ["2026-07-15"]
    monkeypatch.setattr(cache_mod, "_today_et", lambda: today[0])
    monkeypatch.setattr(session, "session_key_et", lambda now=None: today[0])
    return today


def test_hot_path_saves_never_write_on_the_calling_thread(write_threads, day):
    state = hm.replace_state(HodMomoState())
    state.today_alerts = [_alert("a1"), _alert("a2")]
    state.session_highs = {"SOBR": 1.5}

    persist.save_alerts()
    persist.save_highs()
    assert writer.drain(timeout=5.0) is True

    assert len(write_threads) == 2
    assert threading.get_ident() not in write_threads
    assert _alert_ids("2026-07-15") == ["a1", "a2"]
    assert _on_disk(HOD_MOMO_HIGHS_PREFIX, "2026-07-15")["session_highs"] == {"SOBR": 1.5}


def _run_consolidation_tick(monkeypatch) -> int:
    """One tick of the HTTP loop's consolidation task; returns the loop's thread."""
    async def _no_notify(_alert_dict) -> None:
        return None

    monkeypatch.setattr(alerts, "notify_hod_alert_async", _no_notify)
    loop_thread: list[int] = []

    async def _once() -> None:
        loop_thread.append(threading.get_ident())
        task = asyncio.create_task(alerts.flush_consolidated_loop())
        await asyncio.sleep(1.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:  # maintainer: allow-swallow the test ends the task
            pass

    asyncio.run(_once())
    return loop_thread[0]


def test_consolidation_tick_emits_without_writing_on_the_loop(monkeypatch, write_threads, day):
    state = hm.replace_state(HodMomoState())
    now = time.time()
    state.pending_consolidation["SOBR"] = [(now - 1.0, _alert("burst", created_ts=now))]

    loop_thread = _run_consolidation_tick(monkeypatch)
    assert writer.drain(timeout=5.0) is True

    assert [a.id for a in state.today_alerts] == ["burst"]
    assert write_threads and loop_thread not in write_threads
    assert _alert_ids("2026-07-15") == ["burst"]


def test_consolidation_tick_keeps_the_save_interval(monkeypatch, write_threads, day):
    """The tick used to force a pending save every second; it waits out the interval now."""
    state = hm.replace_state(HodMomoState())
    state.today_alerts = [_alert("a1")]
    state.alerts_dirty = True
    state.last_alert_save_mono = time.monotonic()  # saved just now
    state.highs_dirty = True
    state.last_highs_save_mono = time.monotonic()

    _run_consolidation_tick(monkeypatch)
    assert writer.drain(timeout=5.0) is True

    assert write_threads == []
    assert state.alerts_dirty is True and state.highs_dirty is True


def test_snapshot_is_written_for_the_date_it_was_taken(gate, day):
    state = hm.replace_state(HodMomoState())
    state.today_alerts = [_alert("late")]
    state.session_highs = {"SOBR": 2.0}

    persist.save_alerts()
    persist.save_highs()
    day[0] = "2026-07-16"  # the session key rolls before the writer gets to it
    gate.set()
    assert writer.drain(timeout=5.0) is True

    assert _alert_ids("2026-07-15") == ["late"]
    assert _on_disk(HOD_MOMO_HIGHS_PREFIX, "2026-07-15")["session_highs"] == {"SOBR": 2.0}
    assert _alert_ids("2026-07-16") is None
    assert _on_disk(HOD_MOMO_HIGHS_PREFIX, "2026-07-16") is None


def test_rollover_archive_is_not_overtaken_by_a_queued_snapshot(gate, day):
    """A snapshot queued for day D, then the rollover's archive of D: the merged
    set stays on disk (the archive waits for the queued write, then reads)."""
    state = hm.replace_state(HodMomoState())
    state.session_date = "2026-07-15"
    state.today_alerts = [_alert("first", created_ts=1.0)]
    persist.save_alerts()  # queued behind the gate: D = [first]
    state.today_alerts.insert(0, _alert("second", created_ts=2.0))  # deferred

    day[0] = "2026-07-16"
    threading.Timer(0.2, gate.set).start()
    assert session.check_and_reset_session() is True
    assert writer.drain(timeout=5.0) is True

    assert _alert_ids("2026-07-15") == ["second", "first"]
    assert _alert_ids("2026-07-16") == []


def test_forced_save_lands_after_a_queued_one(gate, day):
    state = hm.replace_state(HodMomoState())
    state.today_alerts = [_alert("stale")]
    persist.save_alerts()  # queued
    state.today_alerts = []

    threading.Timer(0.2, gate.set).start()
    hm.clear_today_alerts()  # forced save of []
    assert writer.drain(timeout=5.0) is True

    assert _alert_ids("2026-07-15") == []


def test_shutdown_flush_lands_a_queued_snapshot(gate, day):
    state = hm.replace_state(HodMomoState())
    state.today_alerts = [_alert("queued")]
    persist.save_alerts()
    assert state.alerts_dirty is False  # queued, not deferred

    threading.Timer(0.2, gate.set).start()
    persist.flush_pending_alert_save()

    assert _alert_ids("2026-07-15") == ["queued"]


def test_drain_gives_up_after_its_timeout(gate, caplog):
    with caplog.at_level(logging.WARNING, logger="hod_momo_writer"):
        assert writer.drain(timeout=0.05) is False
    assert any("still busy" in r.message for r in caplog.records)
    gate.set()
    assert writer.drain(timeout=5.0) is True


def test_a_newer_snapshot_of_a_file_replaces_the_queued_one(gate):
    ran: list[str] = []
    writer.submit("alerts", "2026-07-15", lambda: ran.append("older"))
    writer.submit("alerts", "2026-07-15", lambda: ran.append("newer"))
    writer.submit("highs", "2026-07-15", lambda: ran.append("highs"))
    gate.set()
    assert writer.drain(timeout=5.0) is True
    assert ran == ["newer", "highs"]


def test_a_failed_write_is_logged_and_the_writer_goes_on(caplog):
    ran: list[str] = []

    def _boom() -> None:
        raise OSError("disk full")

    with caplog.at_level(logging.WARNING, logger="hod_momo_writer"):
        writer.submit("alerts", "2026-07-15", _boom)
        writer.submit("highs", "2026-07-15", lambda: ran.append("highs"))
        assert writer.drain(timeout=5.0) is True
    assert ran == ["highs"]
    assert any("alerts for 2026-07-15 failed" in r.message for r in caplog.records)
