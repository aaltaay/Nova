"""The Watchlist and the Scanner WATCH column grade the rows the Scanner shows (QA W6).

RVOL, float and news are added to a scanner row at read time
(``scanner_surface.surface_rows``, ADR 008). Grading the raw cache marked every
name "no relative volume data / float unknown / no news" while the same row on
the board showed all three.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import routes.strategy as strategy_routes  # noqa: E402
import scanner_news_badge as snb  # noqa: E402
import scanner_surface  # noqa: E402
from fundamentals import _fundamentals_cache  # noqa: E402
from runtime_state import get_runtime_state  # noqa: E402


@pytest.fixture
def desk(monkeypatch):
    monkeypatch.setattr("alpaca._get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scanner_surface._hod_momo, "is_blocked", lambda s: (s or "").upper() == "BLOK")
    monkeypatch.setattr("catalysts.live.request", lambda symbols: None)
    monkeypatch.setattr("catalysts.live.verdict_for", lambda symbol, now=None: None)
    snb.reset_for_testing()
    state = get_runtime_state()
    prev = (state.gapper_cache, state.gainer_cache)
    state.gainer_cache = []
    yield state
    state.gapper_cache, state.gainer_cache = prev
    snb.reset_for_testing()


def _pillars(entry: dict) -> dict[str, dict]:
    return {p["name"]: p for p in entry["pillars"]}


def test_watchlist_grades_the_rvol_float_and_news_the_board_shows(desk, monkeypatch):
    monkeypatch.setitem(_fundamentals_cache, "TOPS", {"average_volume": 100_000.0, "float_shares": 4_242_083})
    snb.record({"TOPS": "2026-09-22T08:30:00Z"})
    desk.gapper_cache = [
        {"symbol": "TOPS", "price": 1.42, "change_pct": 0.978, "gap_percent": 0.978, "volume": 1_244_000},
    ]

    [entry] = strategy_routes.watchlist()["entries"]
    pillars = _pillars(entry["five_pillars"])

    assert pillars["relative_volume"]["passed"] is True, pillars["relative_volume"]["detail"]
    assert pillars["relative_volume"]["detail"].startswith("12.4x")
    assert pillars["catalyst"]["passed"] is True
    assert pillars["float"]["passed"] is True
    assert pillars["price"]["passed"] is False  # $1.42 is under the $2 floor
    assert entry["five_pillars"]["pass_count"] == 4
    assert entry["sub_scores"]["relative_volume"] > 0
    # ADR 008: the cached row itself is never written.
    assert "rel_volume" not in desk.gapper_cache[0]
    assert "has_news" not in desk.gapper_cache[0]


def test_the_blocklist_leaves_the_watchlist_like_it_leaves_the_board(desk):
    desk.gapper_cache = [
        {"symbol": "BLOK", "price": 5.0, "change_pct": 0.5, "volume": 10},
        {"symbol": "GDC", "price": 5.0, "change_pct": 0.5, "volume": 10},
    ]
    assert [e["symbol"] for e in strategy_routes.watchlist()["entries"]] == ["GDC"]


def test_a_move_past_100_percent_is_never_read_as_one_percent(desk):
    desk.gapper_cache = [
        {"symbol": "GRML", "price": 9.42, "change_pct": 2.3051, "gap_percent": 1.5649, "volume": 10},
        {"symbol": "SLOW", "price": 9.42, "change_pct": 0.04, "gap_percent": 0.04, "volume": 10},
    ]

    results = {r["symbol"]: _pillars(r) for r in strategy_routes.five_pillars_all()["results"]}

    assert results["GRML"]["change_pct"]["passed"] is True
    assert results["GRML"]["change_pct"]["detail"].startswith("230.5%")
    # A fraction up to 1.0 is still a fraction: +4% stays +4%.
    assert results["SLOW"]["change_pct"]["passed"] is False
    assert results["SLOW"]["change_pct"]["detail"].startswith("4.0%")
    # The wire value in the cache is untouched.
    assert desk.gapper_cache[0]["change_pct"] == 2.3051


def test_one_symbol_lookup_grades_the_surfaced_row(desk, monkeypatch):
    monkeypatch.setitem(_fundamentals_cache, "TOPS", {"average_volume": 100_000.0, "float_shares": 4_242_083})
    desk.gapper_cache = [{"symbol": "TOPS", "price": 3.0, "change_pct": 0.5, "volume": 1_000_000}]

    body = strategy_routes.five_pillars_one("tops")

    assert _pillars(body)["relative_volume"]["passed"] is True
    assert _pillars(body)["float"]["passed"] is True


def test_watchlist_rows_carry_the_table_columns(desk, monkeypatch):
    monkeypatch.setitem(_fundamentals_cache, "GRML", {"average_volume": 100_000.0, "float_shares": 3_100_000})
    desk.gapper_cache = [
        {"symbol": "GRML", "price": 8.61, "change_pct": 2.3051, "gap_percent": 1.5649, "volume": 1_820_000},
    ]

    [entry] = strategy_routes.watchlist()["entries"]

    assert entry["price"] == 8.61
    assert entry["change_pct"] == pytest.approx(2.3051)  # a fraction on the wire, never 1.2%
    assert entry["rel_volume"] == pytest.approx(18.2)
    assert entry["float_shares"] == 3_100_000
    assert entry["catalyst"] is None  # no source looked: unknown, not "no news"


def test_watchlist_rows_carry_todays_catalyst_verdict(desk, monkeypatch):
    seen = []
    verdict = {"verdict": "catalyst", "category": "fda_regulatory", "strength": "strong", "title": "FDA clears",
               "source": "globenewswire", "published_ts": 1_790_000_000.0, "news_pending": False,
               "url": "https://example.test", "sources_answered": ["alpaca"], "rules_version": 4}
    monkeypatch.setattr("catalysts.live.request", lambda symbols: seen.extend(symbols))
    monkeypatch.setattr("catalysts.live.verdict_for", lambda symbol, now=None: verdict if symbol == "GRML" else None)
    desk.gapper_cache = [
        {"symbol": "GRML", "price": 8.61, "change_pct": 0.42, "volume": 10},
        {"symbol": "QUIET", "price": 5.0, "change_pct": 0.2, "volume": 10},
    ]

    entries = {e["symbol"]: e for e in strategy_routes.watchlist()["entries"]}

    assert sorted(seen) == ["GRML", "QUIET"]  # the fetch is queued, never awaited
    assert entries["GRML"]["catalyst"] == {
        "verdict": "catalyst", "category": "fda_regulatory", "strength": "strong", "title": "FDA clears",
        "source": "globenewswire", "published_ts": 1_790_000_000.0, "news_pending": False,
    }
    assert entries["QUIET"]["catalyst"] is None
