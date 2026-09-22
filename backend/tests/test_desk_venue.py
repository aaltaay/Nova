"""ADR 020 -- the desk venue is live | paper | sim, persisted as desk-venue.json v2.

Covers the venue model in ``sim/mode.py`` (readers, ``set_venue``, the legacy
``set_sim_mode`` wrapper), the v1 -> v2 file migration and refuse-loud rule,
``status_payload`` per venue, and the ``/api/desk/venue`` routes next to the
legacy ``POST /api/sim`` toggle.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from constants_sim import (
    DESK_VENUE_FILE,
    DESK_VENUE_LEGACY_SCHEMA_VERSION,
    DESK_VENUE_SCHEMA_VERSION,
    NOVA_BROKER_ENV,
)
from ibkr import safety as _safety
from sim import mode as _mode
from sim.mode import (
    is_paper_venue,
    is_practice_venue,
    is_sim_mode,
    reset_for_tests,
    set_sim_mode,
    set_venue,
    status_payload,
    venue,
)


def setup_function() -> None:
    reset_for_tests()


def teardown_function() -> None:
    reset_for_tests()


def _restart() -> None:
    """Drop in-process state the way a fresh interpreter would -- keeping disk."""
    _mode._override = None
    _mode._venue_loaded = False
    _mode.os.environ.pop(NOVA_BROKER_ENV, None)
    _safety.set_armed(False, reason="simulated process start")


def _write(payload: dict) -> None:
    path = Path(DESK_VENUE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _stored() -> dict:
    return json.loads(Path(DESK_VENUE_FILE).read_text(encoding="utf-8"))


# ── The venue model ──────────────────────────────────────────────────────────

def test_default_venue_is_the_ibkr_door_and_nothing_practice() -> None:
    assert venue() == "live"
    assert is_sim_mode() is False
    assert is_paper_venue() is False
    assert is_practice_venue() is False


@pytest.mark.parametrize(
    ("bootstrap", "expected"),
    [("sim", "sim"), ("paper", "paper"), ("live", "live"), ("ibkr", "live"), ("", "live")],
)
def test_nova_broker_bootstrap_names_the_venue(monkeypatch, bootstrap: str, expected: str) -> None:
    monkeypatch.setenv(NOVA_BROKER_ENV, bootstrap)
    assert venue() == expected


@pytest.mark.parametrize("target", ["live", "paper", "sim"])
def test_set_venue_settles_and_persists_a_v2_file(target: str) -> None:
    payload = set_venue(target)
    assert venue() == target
    assert payload["venue"] == target
    assert payload["persisted"] is True
    assert (is_sim_mode(), is_paper_venue(), is_practice_venue()) == (
        target == "sim", target == "paper", target != "live",
    )
    assert _stored() == {"schema_version": DESK_VENUE_SCHEMA_VERSION, "venue": target}
    assert "armed" not in _stored()


def test_set_venue_normalizes_and_refuses_unknown_values() -> None:
    assert set_venue(" Paper ")["venue"] == "paper"
    with pytest.raises(ValueError):
        set_venue("ibkr")
    with pytest.raises(ValueError):
        set_venue("")
    assert venue() == "paper", "a refused value must not move the desk"


@pytest.mark.parametrize(("before", "after"), [("paper", "live"), ("paper", "sim"), ("sim", "paper"), ("live", "paper")])
def test_every_venue_change_disarms(before: str, after: str) -> None:
    set_venue(before)
    _safety.set_armed(True, reason="operator")
    set_venue(after)
    assert _safety.armed() is False, "carrying an arm across a venue change hands the operator a different desk armed"


def test_persist_false_keeps_the_settled_file() -> None:
    set_venue("paper")
    set_venue("sim", persist=False)
    assert venue() == "sim"
    assert _stored()["venue"] == "paper"
    _restart()
    assert venue() == "paper"


def test_the_sim_feed_runs_on_the_sim_venue_only(monkeypatch) -> None:
    from sim import feed

    calls: list[str] = []
    monkeypatch.setattr(feed, "start_sim_feed_threadsafe", lambda: calls.append("start"))
    monkeypatch.setattr(feed, "stop_sim_feed_threadsafe", lambda: calls.append("stop"))
    set_venue("paper")
    set_venue("live")
    assert calls == ["stop", "stop"], "Paper reads the live market like Live -- no replay feed"
    set_venue("sim")
    assert calls[-1] == "start"


# ── Legacy wrappers ──────────────────────────────────────────────────────────

def test_set_sim_mode_is_a_wrapper_over_set_venue() -> None:
    on = set_sim_mode(True)
    assert venue() == "sim" and is_sim_mode() is True
    assert on["sim"] is True and on["mode"] == "sim" and on["venue"] == "sim"
    assert on["persisted"] is True and on["bootstrap_persisted"] is False
    off = set_sim_mode(False)
    assert venue() == "live", "off is the IBKR door, exactly what 'ibkr' meant before ADR 020"
    assert off["sim"] is False and off["mode"] is None and off["venue"] == "live"


def test_is_sim_mode_means_the_sim_venue_not_any_practice_venue() -> None:
    set_venue("paper")
    assert is_sim_mode() is False
    assert is_practice_venue() is True


# ── desk-venue.json: v2, v1 migration, refuse-loud ───────────────────────────

@pytest.mark.parametrize("stored", ["live", "paper", "sim"])
def test_a_v2_file_restores_its_venue_disarmed(stored: str) -> None:
    _write({"schema_version": DESK_VENUE_SCHEMA_VERSION, "venue": stored})
    _restart()
    assert venue() == stored
    assert _safety.armed() is False


@pytest.mark.parametrize(("legacy", "expected"), [("sim", "sim"), ("ibkr", "paper")])
def test_a_v1_file_migrates_and_is_rewritten_as_v2(caplog, legacy: str, expected: str) -> None:
    _write({"schema_version": DESK_VENUE_LEGACY_SCHEMA_VERSION, "venue": legacy})
    _restart()
    with caplog.at_level("INFO"):
        resolved = venue()
    assert resolved == expected, "ibkr -> paper is the safe direction; Live is always an explicit click"
    assert _stored() == {"schema_version": DESK_VENUE_SCHEMA_VERSION, "venue": expected}
    assert _safety.armed() is False
    assert any("migrated" in r.message for r in caplog.records)
    _restart()
    assert venue() == expected, "the rewritten v2 file reads back the same"


def test_a_v1_file_with_an_unknown_value_falls_back_and_is_left_alone(caplog) -> None:
    _write({"schema_version": DESK_VENUE_LEGACY_SCHEMA_VERSION, "venue": "paper"})
    _restart()
    with caplog.at_level("WARNING"):
        assert venue() == "live"
    assert _stored()["schema_version"] == DESK_VENUE_LEGACY_SCHEMA_VERSION, "never rewritten on refusal"
    assert any("venue" in r.message for r in caplog.records)


def test_an_unknown_schema_version_refuses_loud_and_stays_disarmed(caplog) -> None:
    set_venue("paper")
    _safety.set_armed(True, reason="operator")
    _write({"schema_version": DESK_VENUE_SCHEMA_VERSION + 1, "venue": "paper"})
    _restart()
    with caplog.at_level("WARNING"):
        assert venue() == "live", "an unknown version must not pick a venue"
    assert _safety.armed() is False
    assert any("schema_version" in r.message for r in caplog.records)
    assert _stored()["schema_version"] == DESK_VENUE_SCHEMA_VERSION + 1, "left for a downgrade to read"


def test_a_v2_file_with_a_legacy_value_falls_back(caplog) -> None:
    _write({"schema_version": DESK_VENUE_SCHEMA_VERSION, "venue": "ibkr"})
    _restart()
    with caplog.at_level("WARNING"):
        assert venue() == "live"
    assert any("no usable 'venue'" in r.message for r in caplog.records)


# ── status_payload per venue ─────────────────────────────────────────────────

def test_status_payload_names_the_venue_and_its_spend_status() -> None:
    set_venue("live")
    live = status_payload()
    assert (live["venue"], live["practice"], live["sim"], live["mode"], live["broker"]) == (
        "live", False, False, None, "ibkr",
    )
    assert live["spend_status"] is None

    set_venue("paper")
    paper = status_payload()
    assert (paper["venue"], paper["practice"], paper["sim"], paper["mode"], paper["broker"]) == (
        "paper", True, False, "paper", "paper",
    )
    assert paper["armed"] is False and paper["spend_status"] == "locked_disarmed"
    _safety.set_armed(True, reason="test")
    assert status_payload()["spend_status"] == "paper_armed"

    set_venue("sim")
    sim = status_payload()
    assert (sim["venue"], sim["practice"], sim["sim"], sim["mode"], sim["broker"]) == (
        "sim", True, True, "sim", "sim",
    )
    assert sim["spend_status"] == "locked_disarmed"
    _safety.set_armed(True, reason="test")
    assert status_payload()["spend_status"] == "sim_armed"


# ── /api/desk/venue and the legacy /api/sim toggle ───────────────────────────

def _client() -> TestClient:
    from routes.desk import router as desk_router
    from sim.routes import router as sim_router

    app = FastAPI()
    app.include_router(desk_router)
    app.include_router(sim_router)
    return TestClient(app)


def test_get_venue_route_reports_venue_and_schema_version() -> None:
    assert _client().get("/api/desk/venue").json() == {
        "venue": "live", "schema_version": DESK_VENUE_SCHEMA_VERSION,
    }


@pytest.mark.parametrize("target", ["paper", "sim", "live"])
def test_post_venue_route_settles_the_venue(target: str) -> None:
    client = _client()
    _safety.set_armed(True, reason="operator")
    res = client.post("/api/desk/venue", json={"venue": target})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True and body["venue"] == target
    assert body["schema_version"] == DESK_VENUE_SCHEMA_VERSION
    assert body["armed"] is False, "a venue click never arms; it disarms"
    assert body["persisted"] is True
    assert client.get("/api/desk/venue").json()["venue"] == target
    assert _stored()["venue"] == target


@pytest.mark.parametrize("bad", ["ibkr", "", "replay"])
def test_post_venue_route_refuses_unknown_venues(bad: str) -> None:
    client = _client()
    set_venue("paper")
    res = client.post("/api/desk/venue", json={"venue": bad})
    assert res.status_code == 400
    assert "venue must be one of" in res.json()["detail"]
    assert venue() == "paper"


def test_post_venue_route_accepts_case_and_whitespace() -> None:
    assert _client().post("/api/desk/venue", json={"venue": " SIM "}).json()["venue"] == "sim"


def test_legacy_sim_toggle_keeps_working_beside_the_venue_route() -> None:
    client = _client()
    body = client.post("/api/sim", json={"enabled": True}).json()
    assert body["sim"] is True and body["venue"] == "sim"
    assert client.get("/api/desk/venue").json()["venue"] == "sim"
    off = client.post("/api/sim", json={"enabled": False}).json()
    assert off["sim"] is False and off["venue"] == "live"
    assert client.get("/api/sim").json()["venue"] == "live"
