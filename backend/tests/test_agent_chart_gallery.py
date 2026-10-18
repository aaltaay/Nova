"""Generated immutable historical chart contracts; no market records or broker."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_desk.chart_gallery import aggregate_five, create_app, digest, load_gallery


@pytest.fixture
def selection(tmp_path: Path):
    folder = tmp_path / "bars"
    folder.mkdir()
    projection = dict(day="2030-01-02", ticker="FIXTURE",
                      m_semantics="minute_START", time_zone="America/New_York",
                      price_units="raw_same_session_2030-01-02",
                      observed_source_start_m=360, observed_source_end_exclusive_m=370,
                      bars=[dict(m=m, o=2, h=3, l=1, c=2.5, v=10) for m in range(360, 370)])
    part = folder / "01.json"
    part.write_text(json.dumps(projection), encoding="utf-8")
    entry = dict(day=projection["day"], ticker="FIXTURE", as_of_m=365,
                 annotations=[dict(kind="horizontal_line", price=2.4, label="Example", color="blue")],
                 bar_projection=dict(path=str(part), sha256=digest(part)))
    data = dict(schema_version=1, kind="historical_ohlcv", family="GENERATED_FIXTURE", selected=[entry])
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path, data, part, projection


def rewrite(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def update_projection(selection):
    path, data, part, projection = selection
    rewrite(part, projection)
    data["selected"][0]["bar_projection"]["sha256"] = digest(part)
    rewrite(path, data)


def test_wire_repeat_reads_and_hashes_are_immutable(selection):
    path, _, _, _ = selection
    app = create_app(path, digest(path), "http://127.0.0.1:5179", "generated-instance")
    with TestClient(app) as client:
        first = client.get("/api/agent/chart-gallery")
        assert first.status_code == 200 and first.content == client.get("/api/agent/chart-gallery").content
        assert first.headers["etag"] == '"' + digest(path) + '"'
        assert first.headers["x-nova-chart-instance"] == "generated-instance"
        wire = first.json()
        assert wire["kind"] == "historical_ohlcv"
        item = wire["entries"][0]
        assert item["bars_1m"][0]["t"] == "2030-01-02T11:00:00+00:00"
        assert item["as_of_t"] == "2030-01-02T11:05:00+00:00"
        assert item["bars_5m"][0] == dict(t="2030-01-02T11:00:00+00:00", o=2, h=3, l=1, c=2.5, v=50)
        assert set(item["source"]) == {"selection_sha256", "projection_sha256"}
        assert client.post("/api/agent/chart-gallery").status_code == 405


def test_full_session_has_no_implicit_boundary_or_window(selection):
    path, data, _, projection = selection
    data["selected"][0].pop("as_of_m")
    projection["observed_source_end_exclusive_m"] = 500
    projection["bars"] = [dict(m=m, o=2, h=3, l=1, c=2.5, v=10) for m in range(360, 500)]
    update_projection(selection)
    item = load_gallery(path, digest(path))["entries"][0]
    assert len(item["bars_1m"]) == 140 and "as_of_m" not in item and "as_of_t" not in item


def test_bad_hash_fails_before_service(selection):
    with pytest.raises(ValueError, match="Selection SHA256"):
        load_gallery(selection[0], "0" * 64)


def test_projection_hash_and_path_escape_fail_closed(selection):
    path, data, part, _ = selection
    part.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Projection SHA256"):
        load_gallery(path, digest(path))
    data["selected"][0]["bar_projection"]["path"] = str(path)
    rewrite(path, data)
    with pytest.raises(ValueError, match="outside selection"):
        load_gallery(path, digest(path))


def test_missing_minute_never_creates_flat_five_minute_bar(selection):
    one = load_gallery(selection[0], digest(selection[0]))["entries"][0]["bars_1m"]
    assert aggregate_five(one[:2] + one[3:]) == aggregate_five(one[5:])


@pytest.mark.parametrize("minute,refused", [(364, True), (366, False)])
def test_invalid_prefix_refused_later_unavailable_is_gap(selection, minute, refused):
    path, _, _, projection = selection
    projection["bars"][minute - 360]["c"] = None
    update_projection(selection)
    if refused:
        with pytest.raises(ValueError, match="Invalid visible-prefix"):
            load_gallery(path, digest(path))
    else:
        item = load_gallery(path, digest(path))["entries"][0]
        assert len(item["bars_1m"]) == 9 and len(item["bars_5m"]) == 1


def test_duplicate_identity_refused_but_distinct_boundary_allowed(selection):
    path, data, _, _ = selection
    second = copy.deepcopy(data["selected"][0])
    data["selected"].append(second)
    rewrite(path, data)
    with pytest.raises(ValueError, match="unique and chronological"):
        load_gallery(path, digest(path))
    second["as_of_m"] = 366
    rewrite(path, data)
    assert len(load_gallery(path, digest(path))["entries"]) == 2


@pytest.mark.parametrize("annotation", [
    {"kind": "unknown", "label": "Example"},
    {"kind": [], "label": "Example"},
    {"kind": "horizontal_line", "price": True, "label": "Example"},
    {"kind": "horizontal_line", "price": float("inf"), "label": "Example"},
    {"kind": "horizontal_line", "price": 2, "label": "Example", "color": []},
    {"kind": "horizontal_line", "price": 2, "label": "Example", "extra": 1},
    {"kind": "time_marker", "minute": 1440, "label": "Example"},
    {"kind": "time_marker", "minute": 360, "label": "Example\n"},
])
def test_annotations_reject_unknown_or_unsafe_values(selection, annotation):
    path, data, _, _ = selection
    data["selected"][0]["annotations"] = [annotation]
    rewrite(path, data)
    with pytest.raises(ValueError):
        load_gallery(path, digest(path))


@pytest.mark.parametrize("value", [True, -1, 1441, 3.5, None])
def test_invalid_as_of_boundary(selection, value):
    path, data, _, _ = selection
    data["selected"][0]["as_of_m"] = value
    rewrite(path, data)
    with pytest.raises(ValueError, match="as-of"):
        load_gallery(path, digest(path))


def test_unknown_metadata_is_never_forwarded(selection):
    path, data, _, _ = selection
    data["selected"][0]["untrusted_metadata"] = {"value": "unrelated"}
    rewrite(path, data)
    with pytest.raises(ValueError, match="object fields"):
        load_gallery(path, digest(path))


@pytest.mark.parametrize("field,value", [("m", 370), ("m", True), ("m", 360), ("v", False)])
def test_bad_minutes_and_prefix_numeric_types(selection, field, value):
    path, _, _, projection = selection
    projection["bars"][1][field] = value
    update_projection(selection)
    with pytest.raises(ValueError):
        load_gallery(path, digest(path))
