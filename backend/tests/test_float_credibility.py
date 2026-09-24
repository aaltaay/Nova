"""#532: Yahoo's float checked against Yahoo's own share counts, and the short-interest date carried.

Fixtures are the 2026-09-23 audit's yfinance ``.info`` reads (issue #532). Point 1 flags a float
that its own shares outstanding or short interest contradicts; point 2 (the gates) waits on an
operator decision, so the last tests prove every float gate passes and fails exactly as before.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import fundamentals as fund
import mover_enrich_view as mev
from hod_momo_filters import evaluate_strategy
from hod_momo_models import StrategyConfig, TickerSnap
from leaderboard.ranking import LEADERS_RULES, refusal
from leaderboard.rows import from_desk_row
from setup_scanner.grade import grade
from setup_scanner.lane_params import StockFilter
from strategy.five_pillars import evaluate_five_pillars

AUG_31 = int(datetime(2026, 8, 31, tzinfo=timezone.utc).timestamp())

# symbol: (floatShares, sharesOutstanding, heldPercentInsiders, sharesShort)
AUDIT = {
    "SECZ": (8_450_000, 163_270_000, 0.128, 3_760_000),   # de-SPAC; 30 "Low Float" alerts on 2026-09-23
    "RNAZ": (2_150_000, 16_930_000, 0.018, None),
    "WHLR": (54_000, 568_000, 0.0, None),
    "WNW": (156_000, 26_330_000, 0.005, 319_000),          # and FINRA short 319K > float
    "LGCL": (329_000, 42_790_000, 0.25, None),
    "DBGI": (916_000, 575_000, 0.0, 40_000),               # float above shares out: the count is stale
    "AAPL": (14_800_000_000, 14_840_000_000, 0.017, 120_000_000),
}
CONTRADICTED = ("SECZ", "RNAZ", "WHLR", "WNW", "LGCL")


def _info(symbol: str) -> dict:
    f, out, ins, si = AUDIT[symbol]
    info = {"floatShares": f, "sharesOutstanding": out, "heldPercentInsiders": ins, "shortRatio": 1.4}
    if si is not None:
        info.update(sharesShort=si, dateShortInterest=AUG_31)
    return info


@pytest.fixture
def yahoo(monkeypatch):
    """``fetch_fundamentals`` against a recorded ``.info``, with a clean cache either side."""
    infos: dict[str, dict] = {}

    class _Ticker:
        def __init__(self, symbol: str) -> None:
            self.info = infos[symbol]

    def clear() -> None:
        fund._fundamentals_cache.clear()
        fund._fundamentals_cache_ts.clear()
        fund._fundamentals_cache_ttl.clear()

    monkeypatch.setattr(fund.yf, "Ticker", _Ticker)
    clear()
    yield infos
    clear()


@pytest.mark.parametrize("symbol", CONTRADICTED)
def test_the_audits_stale_floats_are_contradicted(yahoo, symbol):
    yahoo[symbol] = _info(symbol)
    out = fund.fetch_fundamentals(symbol)
    assert out["float_contradicted"] is True
    assert "likely stale" in out["float_contradicted_reason"]


def test_the_reason_names_the_counts():
    flag, reason = fund.float_credibility(54_000, 568_000, 0.0, None)
    assert flag is True
    assert reason == ("Float 54K is under half of the 568K shares not held by insiders "
                      "(568K outstanding, 0% insiders) -- likely stale since a dilution")
    _, secz = fund.float_credibility(*AUDIT["SECZ"])
    assert secz.startswith("Float 8.45M is under half of the 142.37M shares not held by insiders "
                           "(163.27M outstanding, 12.8% insiders)")


def test_wnw_fails_both_checks():
    flag, reason = fund.float_credibility(*AUDIT["WNW"])
    assert flag is True
    below, short = reason.split("; ")
    assert below.startswith("Float 156K is under half of the 26.20M shares not held by insiders")
    assert short == "Short interest 319K is above the 156K float -- the float is likely stale"


def test_short_interest_above_the_float_is_enough_on_its_own():
    # Shares outstanding unknown: only the short check can run, and it fires.
    assert fund.float_credibility(156_000, None, None, 319_000)[0] is True


@pytest.mark.parametrize("symbol", ("DBGI", "AAPL"))
def test_a_credible_float_is_not_contradicted(yahoo, symbol):
    # DBGI's float sits above its shares outstanding: the share count is the stale field there, and a
    # float above it cannot pass a low-float gate falsely, so only the low side is flagged.
    yahoo[symbol] = _info(symbol)
    out = fund.fetch_fundamentals(symbol)
    assert out["float_contradicted"] is False
    assert out["float_contradicted_reason"] is None


@pytest.mark.parametrize("args", [
    (None, 568_000, 0.0, 10_000),        # no float
    (0, 568_000, 0.0, 10_000),           # a zero float is no float
    (54_000, None, None, None),          # nothing to check it against
    (5_000_000, 6_000_000, None, 100),   # insiders unknown: the low-side check cannot run
    (5_000_000, 6_000_000, 0.1, None),   # short interest unknown: the short check cannot run
    (5_000_000, 6_000_000, 1.7, 100),    # an insider share that is not a fraction is unknown
])
def test_a_check_short_of_its_inputs_is_unknown(args):
    assert fund.float_credibility(*args) == (None, None)


def test_the_payload_carries_the_new_facts_or_null(yahoo):
    yahoo["SECZ"] = _info("SECZ")
    out = fund.fetch_fundamentals("SECZ")
    assert out["shares_outstanding"] == 163_270_000
    assert out["held_percent_insiders"] == 0.128
    assert out["short_interest_ts"] == AUG_31
    assert out["short_ratio"] == 1.4

    yahoo["BARE"] = {"longName": "Bare Co"}
    bare = fund.fetch_fundamentals("BARE")
    for key in ("shares_outstanding", "held_percent_insiders", "short_interest_ts", "float_contradicted",
                "float_contradicted_reason"):
        assert bare[key] is None, key
    assert set(fund._EMPTY) <= set(bare)


# -- the scanner row ------------------------------------------------------------------------------------
def _cache(monkeypatch, symbol: str) -> dict:
    f, out, ins, si = AUDIT[symbol]
    flag, reason = fund.float_credibility(f, out, ins, si)
    row = {"float_shares": f, "shares_outstanding": out, "held_percent_insiders": ins, "short_interest": si,
           "short_interest_ts": AUG_31 if si is not None else None, "short_ratio": 1.4,
           "float_contradicted": flag, "float_contradicted_reason": reason}
    monkeypatch.setitem(fund._fundamentals_cache, symbol, row)
    return row


def test_decorated_rows_carry_the_check_and_the_date(monkeypatch):
    _cache(monkeypatch, "SECZ")
    _cache(monkeypatch, "AAPL")
    rows = [{"symbol": "SECZ", "price": 11.2}, {"symbol": "AAPL", "price": 250.0}, {"symbol": "NONE", "price": 1.0}]
    out = {r["symbol"]: r for r in mev.decorate_rows(rows)}

    secz = out["SECZ"]
    assert secz["float"] == 8_450_000 and secz["shares_outstanding"] == 163_270_000
    assert secz["float_contradicted"] is True
    assert secz["float_contradicted_reason"].startswith("Float 8.45M is under half")
    assert secz["short_interest_ts"] == AUG_31
    assert (out["AAPL"]["float_contradicted"], out["AAPL"]["float_contradicted_reason"]) == (False, None)
    # Nothing cached: every new field is unknown, never a placeholder.
    none = out["NONE"]
    assert [none[k] for k in ("shares_outstanding", "short_interest_ts", "float_contradicted",
                              "float_contradicted_reason")] == [None, None, None, None]
    assert rows[0] == {"symbol": "SECZ", "price": 11.2}          # a view, never the cached row (ADR 008)


def test_a_date_is_never_pinned_on_another_reports_figure(monkeypatch):
    # The runner stored the previous report's short interest; the cache now holds the Aug 31 one.
    _cache(monkeypatch, "SECZ")
    row = mev.decorate_rows([{"symbol": "SECZ", "short_interest": 3_030_000}])[0]
    assert row["short_interest"] == 3_030_000
    assert row["short_interest_ts"] is None


def test_the_check_reads_the_rows_own_float(monkeypatch):
    # A runner stamped a float the check does not contradict; the flag describes the float shown.
    _cache(monkeypatch, "SECZ")
    row = mev.decorate_rows([{"symbol": "SECZ", "float": 150_000_000, "short_interest": 3_760_000}])[0]
    assert row["float_contradicted"] is False


# -- point 2 is not built: every float gate passes and fails exactly as before --------------------------
LOW_FLOAT = StrategyConfig(strategy_id=1, name="Low Float", color="#fff", max_float=10_000_000)


@pytest.mark.parametrize("symbol", CONTRADICTED)
def test_hod_momo_max_float_is_unchanged_for_a_contradicted_float(yahoo, symbol):
    """HOD Momo's snapshot takes ``float_shares`` from the payload (``hod_momo_enrichment``); a contradicted
    float under the line still passes the 10M "Low Float" gate, as it did before the check existed."""
    yahoo[symbol] = _info(symbol)
    payload = fund.fetch_fundamentals(symbol)
    assert payload["float_contradicted"] is True
    snap = TickerSnap(price=5.0, float_shares=payload["float_shares"])
    assert evaluate_strategy(LOW_FLOAT, snap, None, lambda: None) == (True, "")


def test_hod_momo_max_float_still_refuses_a_contradicted_float_over_the_line():
    flag, _ = fund.float_credibility(15_000_000, 200_000_000, 0.05, None)
    assert flag is True
    passed, reason = evaluate_strategy(LOW_FLOAT, TickerSnap(price=5.0, float_shares=15_000_000), None, lambda: None)
    assert (passed, reason) == (False, "float:above_max(1.5e+07>1e+07)")


@pytest.mark.parametrize("symbol", CONTRADICTED + ("AAPL",))
def test_five_pillars_float_pillar_is_unchanged(monkeypatch, symbol):
    _cache(monkeypatch, symbol)
    decorated = mev.decorate_rows([{"symbol": symbol, "price": 5.0, "change_pct": 30.0, "rel_volume": 6.0,
                                    "has_news": True}])[0]
    bare = {k: v for k, v in decorated.items() if k not in ("float_contradicted", "float_contradicted_reason",
                                                               "shares_outstanding", "short_interest_ts")}
    flagged = evaluate_five_pillars(decorated)
    before = evaluate_five_pillars(bare)
    assert flagged == before
    float_pillar = next(c for c in flagged.checks if c.name == "float")
    assert float_pillar.passed is (symbol != "AAPL")


@pytest.mark.parametrize("symbol", CONTRADICTED)
def test_setup_grade_and_leaders_rule_are_unchanged(monkeypatch, symbol):
    _cache(monkeypatch, symbol)
    decorated = mev.decorate_rows([{"symbol": symbol, "price": 5.0, "prev_close": 3.85, "change_pct": 0.3,
                                    "volume": 500_000, "rel_volume": 6.0, "has_news": True}])[0]
    assert decorated["float_contradicted"] is True
    pillars = {"price": 5.0, "change_pct": 30.0, "rvol": 6.0, "news": True, "float": decorated["float"]}
    assert grade(pillars) == ("A", {"price": True, "change": True, "rvol": True, "news": True, "float": True})
    low_float = StockFilter(min_price=None, max_price=None, max_float=10_000_000, min_change_pct=None,
                            min_rvol=None, require_catalyst=False, min_grade="C", unknown_passes=False)
    assert low_float.check(pillars, "A") is None
    recorded = from_desk_row(decorated, minute_ts=1_790_000_000 // 60 * 60, board="gainers", rank=1)
    assert refusal(recorded, LEADERS_RULES) is None
