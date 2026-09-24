"""Sensor 19, the operator's focus (ADR 033): desk windows report, one answer comes back."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from main import app
from sensors import focus_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh():
    focus_store.reset_for_tests()
    yield
    focus_store.reset_for_tests()


def window(**over):
    report = {
        "schema_version": 1, "role": "main", "window_id": "main", "instance_id": "a1b2", "focused": True,
        "visible": True, "page": "trader", "tab": None, "symbol": "gctk", "symbol_source": "trader_tab",
        "trader_tabs": ["GCTK", "PFSA"], "last_input_ts": time.time() - 3, "reason": "focus", "ui_tag": "v993",
    }
    report.update(over)
    return report


def electron(**over):
    report = {
        "schema_version": 1, "role": "electron", "window_id": "electron-main", "app_focused": True,
        "focused_window_id": "main", "reason": "focus",
        "windows": [
            {"window_id": "main", "focused": True, "visible": True, "minimized": False,
             "display": {"id": "2779098405", "label": "DELL U2720Q", "index": 1, "count": 2, "primary": False,
                         "scale_factor": 1.5}},
            {"window_id": "trader:PFSA", "focused": False, "visible": True, "minimized": False,
             "display": {"id": "1", "label": "Primary", "index": 2, "count": 2, "primary": True, "scale_factor": 1.0}},
        ],
    }
    report.update(over)
    return report


def focus():
    body = client.get("/sensors/focus").json()
    assert body["sensor"] == "focus" and body["status"] == "live"
    return body


def test_nothing_reported_is_a_stated_absence():
    body = focus()
    assert body["data"]["symbol"] is None and body["data"]["nova_in_front"] is None
    assert "No Nova window has reported" in body["error"]


def test_a_window_report_answers_the_symbol_page_and_last_input():
    assert client.post("/sensors/focus", json=window()).json() == {"ok": True}
    data = focus()["data"]
    assert data["symbol"] == "GCTK" and data["page"] == "trader" and data["symbol_source"] == "trader_tab"
    assert data["nova_in_front"] is True and data["focus_source"] == "window"
    assert data["last_input_age_sec"] == pytest.approx(3, abs=1)
    assert data["windows"][0]["trader_tabs"] == ["GCTK", "PFSA"]
    assert data["venue"] in ("live", "paper", "sim") and "eyes" in data["note"]


def test_electron_names_the_window_in_front_and_its_monitor():
    client.post("/sensors/focus", json=window())
    client.post("/sensors/focus", json=window(role="popout", window_id="trader:PFSA", instance_id="c3d4",
                                              symbol="PFSA", focused=False))
    client.post("/sensors/focus", json=electron(focused_window_id="trader:PFSA", windows=[
        {"window_id": "main", "focused": False, "visible": True, "minimized": False, "display": None},
        {"window_id": "trader:PFSA", "focused": True, "visible": True, "minimized": False,
         "display": {"id": "1", "label": "Primary", "index": 2, "count": 2, "primary": True, "scale_factor": 1.0}},
    ]))
    data = focus()["data"]
    assert data["focus_source"] == "electron" and data["symbol"] == "PFSA" and data["window_id"] == "trader:PFSA"
    assert data["display"]["index"] == 2 and data["display"]["primary"] is True


def test_nova_behind_another_app_answers_the_window_last_in_front():
    client.post("/sensors/focus", json=window())
    client.post("/sensors/focus", json=window(focused=False, reason="blur"))
    client.post("/sensors/focus", json=electron(app_focused=False, focused_window_id=None))
    data = focus()["data"]
    assert data["nova_in_front"] is False and data["symbol"] == "GCTK"


def test_a_stale_window_is_not_an_answer():
    focus_store.record_window(window(symbol="GCTK"), now=time.time() - 120)
    body = focus()
    assert body["data"]["symbol"] is None and body["error"]


def test_a_changed_symbol_moves_since_and_is_listed_in_recent():
    focus_store.record_window(window(symbol="GCTK"), now=100.0)
    focus_store.record_window(window(symbol="GCTK", reason="heartbeat"), now=105.0)
    focus_store.record_window(window(symbol="PFSA", reason="symbol"), now=110.0)
    answer = focus_store.resolve(now=112.0)
    assert answer["symbol"] == "PFSA" and answer["since"] == 110.0
    assert [r["symbol"] for r in answer["recent"]] == ["PFSA", "GCTK"]


@pytest.mark.parametrize("over", [
    {"role": "robot"},
    {"symbol": "not a ticker"},
    {"page": "casino"},
    {"schema_version": 2},
    {"window_id": "bad id with spaces"},
])
def test_a_bad_report_is_refused(over):
    assert client.post("/sensors/focus", json=window(**over)).status_code == 422


def test_an_oversized_report_is_refused():
    body = b'{"x":"' + b"a" * 20000 + b'"}'
    assert client.post("/sensors/focus", content=body).status_code == 413


def test_the_focus_sensor_is_in_the_catalog():
    rows = {row["sensor"]: row for row in client.get("/sensors").json()["sensors"]}
    assert rows["focus"]["path"] == "/sensors/focus" and rows["focus"]["needs_symbol"] is False
    assert rows["book-pulls"]["needs_symbol"] is True
