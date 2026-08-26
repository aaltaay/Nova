"""Persisted chart drawings (ADR 015) -- round-trip, isolation, refuse-loud."""
from __future__ import annotations

import pytest

import chart_drawings as cd
from constants import CHART_DRAWINGS_MAX_PER_SYMBOL, CHART_DRAWINGS_SCHEMA_VERSION


def _line(price: float = 231.5, drawing_id: str = "horizontal-line-1") -> dict:
    return {
        "id": drawing_id,
        "type": "horizontal-line",
        "anchors": [{"time": 1_756_000_000, "price": price}],
        "style": {"lineColor": "#3b82f6", "lineWidth": 1},
        "options": {"visible": True},
    }


def test_empty_symbol_returns_empty_list():
    assert cd.get_drawings("AAPL") == []


def test_replace_round_trips_through_disk():
    cd.replace_drawings("aapl", [_line()])
    # Force a fresh load from the file the previous save wrote.
    cd._loaded = False
    cd._drawings = {}
    stored = cd.get_drawings("AAPL")
    assert len(stored) == 1
    assert stored[0]["type"] == "horizontal-line"
    assert stored[0]["anchors"][0]["price"] == 231.5


def test_symbols_are_isolated():
    cd.replace_drawings("AAPL", [_line(100.0)])
    cd.replace_drawings("TSLA", [_line(200.0, "horizontal-line-2")])
    assert cd.get_drawings("AAPL")[0]["anchors"][0]["price"] == 100.0
    assert cd.get_drawings("TSLA")[0]["anchors"][0]["price"] == 200.0


def test_replace_with_empty_list_clears_symbol():
    cd.replace_drawings("AAPL", [_line()])
    cd.replace_drawings("AAPL", [])
    assert cd.get_drawings("AAPL") == []


def test_clear_drawings_removes_symbol():
    cd.replace_drawings("AAPL", [_line()])
    cd.clear_drawings("AAPL")
    assert cd.get_drawings("AAPL") == []


def test_unknown_keys_are_not_persisted():
    saved = cd.replace_drawings("AAPL", [{**_line(), "evil": "payload"}])
    assert set(saved[0]) == {"id", "type", "anchors", "style", "options"}


def test_trend_line_keeps_both_anchors():
    trend = {
        "id": "trendline-1",
        "type": "trend-line",
        "anchors": [
            {"time": 1_756_000_000, "price": 10.0},
            {"time": 1_756_003_600, "price": 12.0},
        ],
        "style": {},
        "options": {},
    }
    saved = cd.replace_drawings("AAPL", [trend])
    assert [a["price"] for a in saved[0]["anchors"]] == [10.0, 12.0]


@pytest.mark.parametrize(
    "bad",
    [
        {"id": "", "type": "horizontal-line", "anchors": [{"time": 1, "price": 2}]},
        {"id": "x", "type": "", "anchors": [{"time": 1, "price": 2}]},
        {"id": "x", "type": "horizontal-line", "anchors": []},
        {"id": "x", "type": "horizontal-line", "anchors": [{"time": 1}]},
        {"id": "x", "type": "horizontal-line", "anchors": [{"price": 2}]},
        {"id": "x", "type": "horizontal-line", "anchors": [{"time": 1, "price": "abc"}]},
        {"id": "x", "type": "horizontal-line", "anchors": "nope"},
    ],
)
def test_bad_drawings_are_rejected(bad):
    with pytest.raises(ValueError):
        cd.replace_drawings("AAPL", [bad])


def test_non_list_payload_is_rejected():
    with pytest.raises(ValueError):
        cd.replace_drawings("AAPL", {"id": "x"})


def test_empty_symbol_is_rejected():
    with pytest.raises(ValueError):
        cd.replace_drawings("   ", [_line()])


def test_per_symbol_cap_is_enforced():
    too_many = [_line(drawing_id=f"line-{i}") for i in range(CHART_DRAWINGS_MAX_PER_SYMBOL + 1)]
    with pytest.raises(ValueError):
        cd.replace_drawings("AAPL", too_many)


def test_anchor_cap_is_enforced():
    wide = {
        "id": "x",
        "type": "brush",
        "anchors": [{"time": 1_756_000_000 + i, "price": 1.0} for i in range(50)],
    }
    with pytest.raises(ValueError):
        cd.replace_drawings("AAPL", [wide])


def test_unknown_schema_version_is_refused_loud(monkeypatch, caplog):
    import cache as cache_mod

    monkeypatch.setattr(
        cache_mod,
        "load_chart_drawings",
        lambda: {"schema_version": 999, "symbols": {"AAPL": [_line(1.0)]}},
    )
    cd.reset_for_testing()
    cd._loaded = False
    with caplog.at_level("WARNING"):
        assert cd.get_drawings("AAPL") == []
    assert "schema_version" in caplog.text


def test_one_bad_row_does_not_drop_the_good_ones(monkeypatch, caplog):
    import cache as cache_mod

    monkeypatch.setattr(
        cache_mod,
        "load_chart_drawings",
        lambda: {
            "schema_version": CHART_DRAWINGS_SCHEMA_VERSION,
            "symbols": {"AAPL": [{"id": "", "type": "bad"}, _line(42.0)]},
        },
    )
    cd.reset_for_testing()
    cd._loaded = False
    with caplog.at_level("WARNING"):
        stored = cd.get_drawings("AAPL")
    assert len(stored) == 1
    assert stored[0]["anchors"][0]["price"] == 42.0
