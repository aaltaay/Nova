"""Sub-minute projections and trade markers on the frozen chart gallery; generated fixtures only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_desk.chart_gallery import digest, load_gallery

DAY = "2030-01-02"


def build(tmp_path: Path, *, bars=None, entry_extra=None, projection_extra=None, annotations=None):
    folder = tmp_path / "bars"
    folder.mkdir(exist_ok=True)
    projection = dict(day=DAY, ticker="FIXTURE", s_semantics="second_START", bar_seconds=10,
                      time_zone="America/New_York", price_units="raw_same_session_" + DAY,
                      observed_source_start_s=25200, observed_source_end_exclusive_s=25260,
                      bars=bars if bars is not None else
                      [dict(s=s, o=2, h=3, l=1, c=2.5, v=10) for s in range(25200, 25260, 10)])
    projection.update(projection_extra or {})
    part = folder / "01.json"
    part.write_text(json.dumps(projection), encoding="utf-8")
    entry = dict(day=DAY, ticker="FIXTURE", bar_seconds=10,
                 annotations=annotations if annotations is not None else [
                     dict(kind="trade_marker", side="buy", second=25212.5, price=2.4, label="Buy 2.40"),
                     dict(kind="trade_marker", side="sell", second=25241, price=2.9, label="Sell 2.90", color="gold"),
                     dict(kind="horizontal_line", price=1.5, label="Stop", color="grey")],
                 bar_projection=dict(path=str(part), sha256=digest(part)))
    entry.update(entry_extra or {})
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(dict(schema_version=1, kind="historical_ohlcv", family="GENERATED_FIXTURE",
                                    selected=[entry])), encoding="utf-8")
    return path


def test_ten_second_bars_reach_the_wire_with_their_own_clock(tmp_path):
    path = build(tmp_path)
    item = load_gallery(path, digest(path))["entries"][0]
    assert item["bar_seconds"] == 10
    assert item["bars_1m"] == [] and item["bars_5m"] == []
    assert len(item["bars_sub"]) == 6
    assert item["bars_sub"][0]["t"] == "2030-01-02T12:00:00+00:00"
    assert item["bars_sub"][1]["t"] == "2030-01-02T12:00:10+00:00"
    assert [a["kind"] for a in item["annotations"]] == ["trade_marker", "trade_marker", "horizontal_line"]


def test_minute_entries_carry_no_sub_minute_fields(tmp_path):
    folder = tmp_path / "bars"
    folder.mkdir()
    part = folder / "01.json"
    part.write_text(json.dumps(dict(day=DAY, ticker="FIXTURE", m_semantics="minute_START",
                                    time_zone="America/New_York", price_units="raw_same_session_" + DAY,
                                    observed_source_start_m=0, observed_source_end_exclusive_m=1440,
                                    bars=[dict(m=420, o=2, h=3, l=1, c=2.5, v=10)])), encoding="utf-8")
    entry = dict(day=DAY, ticker="FIXTURE", bar_projection=dict(path=str(part), sha256=digest(part)),
                 annotations=[dict(kind="trade_marker", side="buy", second=25230, price=2.4, label="Buy")])
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(dict(schema_version=1, kind="historical_ohlcv", family="F", selected=[entry])),
                    encoding="utf-8")
    item = load_gallery(path, digest(path))["entries"][0]
    assert "bar_seconds" not in item and "bars_sub" not in item
    assert item["annotations"][0]["side"] == "buy"


@pytest.mark.parametrize("extra", [dict(bar_seconds=7), dict(bar_seconds=60), dict(bar_seconds=True),
                                   dict(as_of_m=420)])
def test_unsupported_bar_size_or_boundary_refuses(tmp_path, extra):
    path = build(tmp_path, entry_extra=extra)
    with pytest.raises(ValueError):
        load_gallery(path, digest(path))


@pytest.mark.parametrize("bars", [
    [dict(s=25205, o=2, h=3, l=1, c=2.5, v=10)],                       # not on the 10 s grid
    [dict(s=25210, o=2, h=3, l=1, c=2.5, v=10), dict(s=25200, o=2, h=3, l=1, c=2.5, v=10)],  # out of order
    [dict(s=25300, o=2, h=3, l=1, c=2.5, v=10)],                       # outside the observed window
    [dict(s=25200, o=2, h=1, l=3, c=2.5, v=10)],                       # high below low
    [dict(m=420, o=2, h=3, l=1, c=2.5, v=10)],                         # minute row in a seconds projection
    [],
])
def test_bad_second_rows_fail_closed(tmp_path, bars):
    path = build(tmp_path, bars=bars)
    with pytest.raises(ValueError):
        load_gallery(path, digest(path))


def test_projection_bar_size_must_match_the_entry(tmp_path):
    path = build(tmp_path, projection_extra=dict(bar_seconds=5))
    with pytest.raises(ValueError):
        load_gallery(path, digest(path))


@pytest.mark.parametrize("marker", [
    dict(kind="trade_marker", side="short", second=25212, price=2.4, label="X"),
    dict(kind="trade_marker", side="buy", second=86400, price=2.4, label="X"),
    dict(kind="trade_marker", side="buy", second=-1, price=2.4, label="X"),
    dict(kind="trade_marker", side="buy", second=25212, price=0, label="X"),
    dict(kind="trade_marker", side="buy", second=25212, price=2.4, label="X", color="url(x)"),
    dict(kind="trade_marker", side="buy", second=25212, price=2.4, label="X", extra=1),
    dict(kind="trade_marker", side="buy", second=True, price=2.4, label="X"),
])
def test_bad_trade_markers_refuse(tmp_path, marker):
    path = build(tmp_path, annotations=[marker])
    with pytest.raises(ValueError):
        load_gallery(path, digest(path))
