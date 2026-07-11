"""
Unit tests for the Five Pillars scoring module — mock data only, no network.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategy.five_pillars import evaluate_five_pillars, evaluate_many


def _mock_candidate(**overrides) -> dict:
    base = {
        "symbol": "MOCK",
        "price": 5.00,
        "change_pct": 0.15,      # 15%
        "rel_volume": 6.0,
        "has_news": True,
        "float": 8_000_000,
    }
    base.update(overrides)
    return base


class TestAllPillarsPass:
    def test_perfect_candidate_gets_checkmark(self):
        result = evaluate_five_pillars(_mock_candidate())
        assert result.all_pass is True
        assert result.pass_count == 5
        assert result.checkmark == "\u2705"

    def test_to_dict_shape(self):
        result = evaluate_five_pillars(_mock_candidate())
        payload = result.to_dict()
        assert payload["all_pass"] is True
        assert payload["checkmark"] == "\u2705"
        assert len(payload["pillars"]) == 5
        assert {p["name"] for p in payload["pillars"]} == {
            "price", "change_pct", "relative_volume", "catalyst", "float",
        }


class TestEachPillarCanFailIndependently:
    def test_price_too_low_fails_only_price(self):
        result = evaluate_five_pillars(_mock_candidate(price=1.50))
        by_name = {c.name: c.passed for c in result.checks}
        assert by_name["price"] is False
        assert result.all_pass is False
        assert result.pass_count == 4

    def test_price_too_high_fails(self):
        result = evaluate_five_pillars(_mock_candidate(price=25.00))
        by_name = {c.name: c.passed for c in result.checks}
        assert by_name["price"] is False

    def test_change_pct_below_threshold_fails(self):
        result = evaluate_five_pillars(_mock_candidate(change_pct=0.04))
        by_name = {c.name: c.passed for c in result.checks}
        assert by_name["change_pct"] is False
        assert result.pass_count == 4

    def test_change_pct_accepts_already_percent_form(self):
        # Some callers may pass 15 (already a percent) instead of 0.15 (a fraction).
        result = evaluate_five_pillars(_mock_candidate(change_pct=15.0))
        by_name = {c.name: c.passed for c in result.checks}
        assert by_name["change_pct"] is True

    def test_low_relative_volume_fails(self):
        result = evaluate_five_pillars(_mock_candidate(rel_volume=2.0))
        by_name = {c.name: c.passed for c in result.checks}
        assert by_name["relative_volume"] is False

    def test_no_catalyst_fails_unless_technical_breakout(self):
        result = evaluate_five_pillars(_mock_candidate(has_news=False))
        by_name = {c.name: c.passed for c in result.checks}
        assert by_name["catalyst"] is False

        result2 = evaluate_five_pillars(_mock_candidate(has_news=False), technical_breakout=True)
        by_name2 = {c.name: c.passed for c in result2.checks}
        assert by_name2["catalyst"] is True

    def test_float_too_high_fails(self):
        result = evaluate_five_pillars(_mock_candidate(float=50_000_000))
        by_name = {c.name: c.passed for c in result.checks}
        assert by_name["float"] is False

    def test_missing_float_fails_closed(self):
        """Unknown data should never silently count as a pass."""
        result = evaluate_five_pillars(_mock_candidate(float=None))
        by_name = {c.name: c.passed for c in result.checks}
        assert by_name["float"] is False


class TestFieldNameCompatibility:
    def test_accepts_scanner_field_names(self):
        """Real gapper/gainer cache rows use current_price / gap_percent / float_shares."""
        candidate = {
            "symbol": "REAL",
            "current_price": 4.20,
            "gap_percent": 0.22,
            "rel_volume": 8.5,
            "has_news": True,
            "float_shares": 3_000_000,
        }
        result = evaluate_five_pillars(candidate)
        assert result.all_pass is True


class TestEvaluateMany:
    def test_scans_a_full_mock_watchlist(self):
        watchlist = [
            _mock_candidate(symbol="AAA"),                      # passes all 5
            _mock_candidate(symbol="BBB", rel_volume=1.0),       # fails RVOL
            _mock_candidate(symbol="CCC", price=0.30),           # fails price
            _mock_candidate(symbol="DDD", float=100_000_000),    # fails float
            _mock_candidate(symbol="EEE", has_news=False),       # fails catalyst
        ]
        results = evaluate_many(watchlist)
        assert len(results) == 5
        passers = [r.symbol for r in results if r.all_pass]
        assert passers == ["AAA"]
        # Confirm every stock got scored against all five pillars (none skipped).
        assert all(len(r.checks) == 5 for r in results)
