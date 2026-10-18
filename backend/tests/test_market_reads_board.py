"""Past-day boards and stock-day bars through the front door (``research/market_reads/reads.py``): a board's percents
come back in points like every movers read (the store keeps fractions), a day with no board says so out loud, and a
daily timeframe is refused with where daily bars live."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from leaderboard import playback  # noqa: E402
from market_reads import reads  # noqa: E402


def _answer(rows, source="reconstructed", covered=True, gap=None):
    board = {"recorded": "gainers", "reconstructed": "market"}[source]
    return {"source": source, "minute_ts": 1788961500, "gap": gap, "covered": covered,
            "boards": {board: {"rows": rows}}}


def test_board_percents_come_back_in_points(monkeypatch):
    rows = [{"symbol": "IRD", "rank": 1, "change_pct": 0.456221, "gap_pct": 0.223502},
            {"symbol": "OLB", "rank": 2, "change_pct": None, "gap_pct": 0.5}]
    monkeypatch.setattr(playback, "board_at", lambda day, ts, source: _answer(rows))
    frame = reads.board("2026-09-09", "09:45")
    assert frame["change_pct"].tolist()[0] == pytest.approx(45.6221)
    assert pd.isna(frame["change_pct"].tolist()[1])
    assert frame["gap_pct"].tolist() == pytest.approx([22.3502, 50.0])
    assert "percent points" in frame.attrs["units"]


def test_a_day_without_a_board_says_it_is_not_covered(monkeypatch):
    gap = {"start": 1685606400, "end": 1685664060, "reason": "not_recorded", "stop": None}
    monkeypatch.setattr(playback, "board_at", lambda day, ts, source: _answer([], "recorded", False, gap))
    frame = reads.board("2023-06-01", "09:45")
    assert frame.empty and frame.attrs["covered"] is False
    assert "2023-06-01" in frame.attrs["note"] and "not_recorded" in frame.attrs["note"]


def test_a_daily_timeframe_is_not_a_stock_day_read():
    with pytest.raises(ValueError, match="daily_bars"):
        reads.bars("GME", "2021-01-27", "1d")
    with pytest.raises(ValueError, match="tf must be"):
        reads.bars("GME", "2021-01-27", "5x")
