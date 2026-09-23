"""
Unit tests for the watchlist composite scoring module — mock data only.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategy.watchlist import build_watchlist, score_watchlist_entry


def _mock_candidate(**overrides) -> dict:
    base = {
        "symbol": "MOCK",
        "price": 5.00,
        "change_pct": 0.15,
        "rel_volume": 6.0,
        "has_news": True,
        "newest_headline_at": datetime.now(timezone.utc).isoformat(),
        "float": 8_000_000,
    }
    base.update(overrides)
    return base


class TestScoreWatchlistEntry:
    def test_perfect_candidate_scores_high_and_passes_pillars(self):
        entry = score_watchlist_entry(_mock_candidate())
        assert entry.five_pillars.all_pass is True
        assert entry.composite_score > 20
        assert set(entry.sub_scores) == {"change_pct", "relative_volume", "float", "catalyst"}

    def test_no_news_zeroes_catalyst_subscore(self):
        entry = score_watchlist_entry(_mock_candidate(has_news=False))
        assert entry.sub_scores["catalyst"] == 0.0

    def test_stale_headline_decays_toward_zero(self):
        stale = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        entry = score_watchlist_entry(_mock_candidate(newest_headline_at=stale))
        assert entry.sub_scores["catalyst"] == 0.0

    def test_fresh_headline_scores_full_catalyst(self):
        fresh = datetime.now(timezone.utc).isoformat()
        entry = score_watchlist_entry(_mock_candidate(newest_headline_at=fresh))
        assert entry.sub_scores["catalyst"] == 100.0

    def test_missing_float_scores_zero_not_a_crash(self):
        entry = score_watchlist_entry(_mock_candidate(float=None))
        assert entry.sub_scores["float"] == 0.0

    def test_tighter_float_scores_higher(self):
        tight = score_watchlist_entry(_mock_candidate(float=1_000_000))
        loose = score_watchlist_entry(_mock_candidate(float=19_000_000))
        assert tight.sub_scores["float"] > loose.sub_scores["float"]

    def test_to_dict_shape(self):
        payload = score_watchlist_entry(_mock_candidate()).to_dict()
        assert set(payload) == {
            "symbol", "composite_score", "sub_scores", "five_pillars",
            "price", "change_pct", "rel_volume", "rvol_source", "float_shares", "has_news",
        }

    def test_market_columns_come_from_the_scored_row(self):
        payload = score_watchlist_entry(_mock_candidate(rvol_source="yfinance")).to_dict()
        assert payload["price"] == 5.0
        assert payload["change_pct"] == 0.15
        assert payload["rel_volume"] == 6.0
        assert payload["rvol_source"] == "yfinance"
        assert payload["float_shares"] == 8_000_000
        assert payload["has_news"] is True

    def test_market_columns_state_unknowns_as_none(self):
        payload = score_watchlist_entry({"symbol": "BARE", "rel_volume": float("nan"), "has_news": "yes"}).to_dict()
        for key in ("price", "change_pct", "rel_volume", "rvol_source", "float_shares", "has_news"):
            assert payload[key] is None, key

    def test_a_graded_move_past_100_percent_is_a_fraction_again(self):
        # routes.strategy._graded hands the graders 230.51 for a +230.51% move.
        payload = score_watchlist_entry(_mock_candidate(change_pct=230.51)).to_dict()
        assert payload["change_pct"] == pytest.approx(2.3051)


class TestBuildWatchlist:
    def test_all_pass_symbols_always_rank_above_partial_pass(self):
        candidates = [
            _mock_candidate(symbol="LOWSCORE_BUT_PASSES", rel_volume=5.1),
            _mock_candidate(symbol="HIGHSCORE_BUT_FAILS", rel_volume=49.0, price=25.00),  # fails price pillar
        ]
        entries = build_watchlist(candidates)
        assert entries[0].symbol == "LOWSCORE_BUT_PASSES"
        assert entries[0].five_pillars.all_pass is True
        assert entries[1].five_pillars.all_pass is False

    def test_composite_score_breaks_ties_within_pass_group(self):
        candidates = [
            _mock_candidate(symbol="WEAKER", rel_volume=5.1),
            _mock_candidate(symbol="STRONGER", rel_volume=40.0),
        ]
        entries = build_watchlist(candidates)
        assert [e.symbol for e in entries] == ["STRONGER", "WEAKER"]

    def test_respects_limit(self):
        candidates = [_mock_candidate(symbol=f"SYM{i}") for i in range(10)]
        entries = build_watchlist(candidates, limit=3)
        assert len(entries) == 3

    def test_empty_universe_returns_empty_list(self):
        assert build_watchlist([]) == []
