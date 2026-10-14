"""A day with no HOD Momo history is an absence, not "no alerts raised" (operator rule, 2026-10-12).

The Sim's Massive-rebuilt 2026-07-15 showed "No alerts raised by 07:20 ET" in
the HOD Momo strip, but HOD Momo never ran that day: the history route answered
``[]`` both for a day with no snapshot and for a recorded day with no alert yet.
``recorded`` now tells them apart.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cache  # noqa: E402
from routes import hod_momo as hod_routes  # noqa: E402

DAY = "2026-09-21"
RAISED = 1_790_000_000.0


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(hod_routes.router)
    return TestClient(app)


def _alert(alert_id: str, created_ts: float) -> dict:
    return {"id": alert_id, "ticker": "GRML", "change_pct": 0.31, "created_ts": created_ts}


def test_a_day_with_no_snapshot_is_not_recorded():
    body = _client().get(f"/api/hod-momo/history/2026-07-15?until={RAISED}").json()
    rebuild = body.pop("rebuild")
    assert body == {"date": "2026-07-15", "recorded": False, "source": None, "alerts": [], "error": None}
    # Nothing rebuilt yet: the rebuild says so (hod_momo_rebuild), never "no alerts raised".
    assert rebuild["status"] == "none"


def test_a_recorded_day_with_no_alert_yet_is_recorded_and_empty():
    cache.save_hod_momo_snapshot_for_date(DAY, [], RAISED)
    body = _client().get(f"/api/hod-momo/history/{DAY}?until={RAISED}").json()
    assert body == {"date": DAY, "recorded": True, "source": "recorded", "alerts": [], "error": None, "rebuild": None}


def test_a_recorded_day_keeps_only_the_alerts_raised_by_the_playhead():
    cache.save_hod_momo_snapshot_for_date(DAY, [_alert("b", RAISED + 60), _alert("a", RAISED)], RAISED)
    client = _client()
    early = client.get(f"/api/hod-momo/history/{DAY}?until={RAISED - 1}").json()
    assert early["recorded"] is True and early["alerts"] == []
    body = client.get(f"/api/hod-momo/history/{DAY}?until={RAISED + 30}").json()
    assert [a["id"] for a in body["alerts"]] == ["a"]
    whole = client.get(f"/api/hod-momo/history/{DAY}").json()
    assert [a["id"] for a in whole["alerts"]] == ["b", "a"]


def test_an_unreadable_snapshot_says_so_instead_of_reading_as_empty():
    Path(cache._dated_path(cache.HOD_MOMO_ALERTS_PREFIX, DAY)).write_text("{not json", encoding="utf-8")
    body = _client().get(f"/api/hod-momo/history/{DAY}").json()
    assert body["recorded"] is True
    assert body["alerts"] == []
    assert DAY in body["error"]


def test_a_malformed_date_still_answers_an_empty_object():
    assert _client().get("/api/hod-momo/history/latest").json() == {}
