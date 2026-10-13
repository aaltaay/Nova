"""The decision journal writes a line when a symbol's verdict changes kind, and reads a day back."""
from __future__ import annotations

import logging

import pytest

import hod_momo_decision_journal as journal


@pytest.fixture()
def on(monkeypatch, tmp_path):
    """The journal on, writing to this test's log dir (conftest silences it everywhere else)."""
    monkeypatch.setenv("NOVA_LOG_DIR", str(tmp_path))
    log = logging.getLogger("hod_momo.decisions")
    level = log.level
    log.setLevel(logging.INFO)
    journal._last_kind.clear()
    journal._last_day = None
    yield tmp_path
    journal._listener.stop()  # drain the queue so the reads below see every line
    journal._listener.start()
    log.setLevel(level)


def _blocked(reason: str) -> list[dict]:
    return [{"id": 10, "passed": False, "blocked_by": reason}, {"id": 1, "passed": False, "blocked_by": "disabled"}]


def test_reason_kind_drops_the_figures():
    assert journal.reason_kind("hod(price=6.899<hod=8.808)") == "hod"
    assert journal.reason_kind("surge:2.65 < 5.0% in 5min") == "surge"
    assert journal.reason_kind("master_liquidity:rvol(0.91<1.50)") == "master_liquidity:rvol"
    assert journal.reason_kind("hod:stale_new(70s>60s)") == "hod:stale_new"
    assert journal.reason_kind(None) is None


def test_a_line_per_change_of_kind_not_per_tick(on):
    t = 1_791_893_990.0  # 2026-10-13 08:19:50 ET
    snap = {"volume": 103_000, "rvol": 0.95}
    assert journal.note(t, "PFAI", 2.92, snap, "master_liquidity:rvol(0.95<1.50)", [])
    assert not journal.note(t + 1, "PFAI", 2.93, snap, "master_liquidity:rvol(0.96<1.50)", [])  # same kind
    assert journal.note(t + 47, "PFAI", 5.5, snap, None, [{"id": 10, "passed": True, "blocked_by": ""}])
    assert journal.note(t + 50, "PFAI", 5.0, snap, None, _blocked("hod(price=5<hod=5.94)"))
    journal._listener.stop()
    journal._listener.start()

    rows = journal.read("PFAI", "2026-10-13", directory=on)
    assert [r["gate"] for r in rows] == ["master_liquidity:rvol(0.95<1.50)", None, None]
    assert rows[1]["fired"] == [10]
    assert rows[2]["blocked"] == {"10": "hod(price=5<hod=5.94)"}  # disabled strategies are left out
    assert rows[0]["schema_version"] == 1
    assert journal.read("PFAI", "2026-10-13", start=t + 10, directory=on)[0]["price"] == 5.5
    assert journal.read("NOPE", "2026-10-13", directory=on) == []
    assert journal.read("PFAI", "2026-10-12", directory=on) == []
