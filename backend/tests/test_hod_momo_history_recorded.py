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
import hod_momo_history  # noqa: E402
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
    # No Massive files here: the rebuild says why there is none (hod_momo_rebuild), never "no alerts raised".
    assert rebuild["status"] == "unavailable" and rebuild["reason"]


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


# ── Finding the day's file (#883) ──────────────────────────────────────────────

def test_a_recorded_day_is_found_by_its_file_name():
    cache.save_hod_momo_snapshot_for_date(DAY, [_alert("a", RAISED)], RAISED)
    cache.save_hod_momo_highs_for_date("2026-09-22", {"session_highs": {}})   # a sibling prefix is never the day
    assert cache.hod_momo_snapshot_on_file(DAY) is True
    assert [a["id"] for a in cache.load_hod_momo_snapshot_for_date(DAY)["alerts"]] == ["a"]
    assert hod_momo_history.get_history_day(DAY)["recorded"] is True
    assert cache.hod_momo_snapshot_on_file("2026-09-22") is False


def test_a_day_with_no_file_reads_not_recorded():
    assert cache.hod_momo_snapshot_on_file("2026-07-15") is False
    assert cache.load_hod_momo_snapshot_for_date("2026-07-15") == {}
    assert hod_momo_history.get_history_day("2026-07-15") == {"recorded": False, "alerts": [], "error": None}


def test_a_snapshot_of_an_unknown_schema_is_on_file_but_unreadable():
    Path(cache._dated_path(cache.HOD_MOMO_ALERTS_PREFIX, DAY)).write_text(
        '{"schema_version": 999, "date": "2026-09-21", "alerts": []}', encoding="utf-8",
    )
    day = hod_momo_history.get_history_day(DAY)
    assert day["recorded"] is True and day["alerts"] == [] and DAY in day["error"]


def test_a_request_date_is_only_compared_with_file_names(monkeypatch):
    cache.save_hod_momo_snapshot_for_date(DAY, [_alert("a", RAISED)], RAISED)
    joined: list[str] = []
    real = cache._dated_path
    monkeypatch.setattr(cache, "_dated_path", lambda prefix, date: joined.append(date) or real(prefix, date))
    for odd in (f"../{DAY}", f"x/../{DAY}", f"{DAY}.json", ""):
        assert cache.hod_momo_snapshot_on_file(odd) is False
        assert cache.load_hod_momo_snapshot_for_date(odd) == {}
        assert hod_momo_history.get_history_day(odd) == {"recorded": False, "alerts": [], "error": None}
        assert hod_momo_history.get_history_alerts(odd) == []
    assert joined == []
    assert hod_momo_history.get_history_day(DAY)["recorded"] is True and joined == []


def test_the_rollover_archive_still_merges_into_the_days_file():
    cache.save_hod_momo_snapshot_for_date(DAY, [_alert("a", RAISED)], RAISED)
    import hod_momo_persist
    from hod_momo_models import alert_from_dict

    hod_momo_persist.merge_archive_session_alerts(DAY, [alert_from_dict(_alert("b", RAISED + 60))])
    assert [a["id"] for a in cache.load_hod_momo_snapshot_for_date(DAY)["alerts"]] == ["b", "a"]
