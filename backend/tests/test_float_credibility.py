"""#532: Yahoo's float checked against Yahoo's own share counts, and the short-interest date carried.

Fixtures are the 2026-09-23 audit's yfinance ``.info`` reads (issue #532). Point 1 flags a float
that its own shares outstanding or short interest contradicts. Point 2 (operator decision
2026-09-24: ship it now): every max-float gate reads ``strategy.float_gate`` -- a contradicted float
passes only when shares outstanding is at or under the gate's limit, and is otherwise unknown and
never a pass; an unflagged or unchecked float is judged exactly as before.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

import fundamentals as fund
import hod_momo_enrichment as hme
import mover_enrich_view as mev
from hod_momo_filters import evaluate_strategy
from hod_momo_models import StrategyConfig, TickerSnap
from leaderboard.ranking import LEADERS_RULES, refusal
from leaderboard.rows import from_desk_row, make_row
from setup_scanner import grade as grade_mod
from setup_scanner.grade import float_note, grade
from setup_scanner.lane_params import GradeRules, StockFilter
from strategy.five_pillars import evaluate_five_pillars
from strategy.float_gate import float_for_gate
from strategy.watchlist import score_watchlist_entry

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
    "HAO": (20_000, 350_000, 0.0, None),                   # armed a setup on 2026-09-23 on this float
    "HKIT": (33_000, 800_000, 0.006, None),                # three reverse splits in 2026
}
CONTRADICTED = ("SECZ", "RNAZ", "WHLR", "WNW", "LGCL", "HAO", "HKIT")
# Contradicted, but shares outstanding is under 10M: the float cannot be larger, so the low-float pass stands.
RESCUED = ("WHLR", "HAO", "HKIT")
# Contradicted, and shares outstanding is over 10M: the float is unknown, never a pass.
OVER_10M = ("SECZ", "RNAZ", "WNW", "LGCL")


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


# -- point 2: the one rule -------------------------------------------------------------------------------
def test_an_uncontradicted_float_is_judged_as_before():
    assert float_for_gate(5_000_000, 10_000_000) == (True, None)
    assert float_for_gate(15_000_000, 10_000_000, contradicted=False, shares_outstanding=16_000_000) == (False, None)
    assert float_for_gate(None, 10_000_000, contradicted=None) == (None, None)
    # Null is unchecked, not contradicted: SECZ's float passes a 10M line exactly as it did before #532.
    assert float_for_gate(8_450_000, 10_000_000, contradicted=None, shares_outstanding=163_270_000) == (True, None)


def test_a_contradicted_float_passes_only_on_shares_outstanding():
    assert float_for_gate(54_000, 10_000_000, contradicted=True, shares_outstanding=568_000) == (
        True, "float 54K is contradicted by its own share counts; passes on 568K shares outstanding, "
              "at or under 10.00M")
    assert float_for_gate(8_450_000, 10_000_000, contradicted=True, shares_outstanding=163_270_000) == (
        None, "float 8.45M is contradicted by its own share counts and 163.27M shares outstanding is over "
              "10.00M -- float unknown, not a pass")
    passes, why = float_for_gate(156_000, 10_000_000, contradicted=True, shares_outstanding=None)
    assert passes is None and "shares outstanding is unknown" in why
    # At the line is a pass: the float is at most shares outstanding.
    assert float_for_gate(1_000, 10_000_000, contradicted=True, shares_outstanding=10_000_000)[0] is True


def test_sqlite_hands_the_flag_back_as_an_integer():
    assert float_for_gate(8_450_000, 10_000_000, contradicted=1, shares_outstanding=163_270_000)[0] is None
    assert float_for_gate(8_450_000, 10_000_000, contradicted=0, shares_outstanding=163_270_000) == (True, None)


# -- HOD Momo "Low Float" max_float (10M) ----------------------------------------------------------------
LOW_FLOAT = StrategyConfig(strategy_id=1, name="Low Float", color="#fff", max_float=10_000_000)


def _snap(payload: dict) -> TickerSnap:
    return TickerSnap(price=5.0, float_shares=payload["float_shares"], float_contradicted=payload["float_contradicted"],
                      shares_outstanding=payload["shares_outstanding"])


@pytest.mark.parametrize("symbol", OVER_10M)
def test_hod_momo_refuses_a_contradicted_float_shares_outstanding_does_not_rescue(yahoo, symbol):
    yahoo[symbol] = _info(symbol)
    payload = fund.fetch_fundamentals(symbol)
    queued: list[str] = []
    passed, reason = evaluate_strategy(LOW_FLOAT, _snap(payload), None, lambda: queued.append(symbol))
    out = AUDIT[symbol][1]
    assert (passed, reason) == (False, f"float:contradicted(shares_out={out:.3g}>{1e7:.3g})")
    assert queued == []   # another Yahoo read would return the same stale count


@pytest.mark.parametrize("symbol", RESCUED)
def test_hod_momo_passes_a_contradicted_float_on_small_shares_outstanding(yahoo, symbol):
    yahoo[symbol] = _info(symbol)
    payload = fund.fetch_fundamentals(symbol)
    assert payload["float_contradicted"] is True
    assert evaluate_strategy(LOW_FLOAT, _snap(payload), None, lambda: None) == (True, "")


def test_hod_momo_unflagged_and_unchecked_floats_behave_as_before(yahoo):
    yahoo["DBGI"] = _info("DBGI")
    dbgi = fund.fetch_fundamentals("DBGI")
    assert dbgi["float_contradicted"] is False
    assert evaluate_strategy(LOW_FLOAT, _snap(dbgi), None, lambda: None) == (True, "")
    unchecked = TickerSnap(price=5.0, float_shares=8_450_000, float_contradicted=None, shares_outstanding=163_270_000)
    assert evaluate_strategy(LOW_FLOAT, unchecked, None, lambda: None) == (True, "")
    over = TickerSnap(price=5.0, float_shares=15_000_000, float_contradicted=False)
    assert evaluate_strategy(LOW_FLOAT, over, None, lambda: None) == (False, "float:above_max(1.5e+07>1e+07)")
    queued: list[int] = []
    assert evaluate_strategy(LOW_FLOAT, TickerSnap(price=5.0), None, lambda: queued.append(1)) == (
        False, "float:unknown")
    assert queued == [1]


def test_hod_momo_contradicted_float_without_shares_outstanding_is_refused():
    snap = TickerSnap(price=5.0, float_shares=156_000, float_contradicted=True, shares_outstanding=None)
    assert evaluate_strategy(LOW_FLOAT, snap, None, lambda: None) == (False, "float:contradicted(shares_out=unknown)")


def test_the_snapshot_keeps_the_check_with_the_float_it_describes(monkeypatch):
    import archive.capture
    import hod_momo_market
    import hod_momo_state

    monkeypatch.setattr(archive.capture, "record_enrichment_snapshot", lambda **_kw: None)
    state = hod_momo_state.get_state()
    prev = dict(state.ticker_snaps)
    try:
        hod_momo_market.update_ticker_snapshot("ZZFLT", 5.0, float_shares=8_450_000, float_contradicted=True,
                                               shares_outstanding=163_270_000)
        snap = state.ticker_snaps["ZZFLT"]
        assert (snap.float_contradicted, snap.shares_outstanding) == (True, 163_270_000)
        hod_momo_market.update_ticker_snapshot("ZZFLT", 5.1, rvol=2.0)                  # no float: the check stays
        assert snap.float_contradicted is True
        hod_momo_market.update_ticker_snapshot("ZZFLT", 5.2, float_shares=9_000_000)    # a float without its check
        assert (snap.float_contradicted, snap.shares_outstanding) == (None, None)
    finally:
        state.ticker_snaps.clear()
        state.ticker_snaps.update(prev)


def test_the_fundamentals_loop_hands_hod_momo_the_check(yahoo, monkeypatch):
    yahoo["SECZ"] = _info("SECZ")
    requests = ["SECZ"]
    seen: dict = {}

    class _Hod:
        @staticmethod
        def pop_fundamentals_request():
            return requests.pop() if requests else None

        @staticmethod
        def get_ticker_snapshot(_sym):
            return TickerSnap(price=5.0)

        @staticmethod
        def update_ticker_snapshot(sym, **kw):
            seen[sym] = kw

        @staticmethod
        def mark_needs_fundamentals(_sym):
            return None

    monkeypatch.setattr(hme, "_hod_momo", _Hod)
    monkeypatch.setattr(hme, "HOD_MOMO_FUNDAMENTALS_QUEUE_INTERVAL_SEC", 0)
    monkeypatch.setattr(hme, "_get_discovery_provider", lambda: "ibkr")

    async def drive() -> None:
        loop_task = asyncio.create_task(hme.fundamentals_enrichment_loop())
        for _ in range(500):
            await asyncio.sleep(0.01)
            if seen:
                break
        loop_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await loop_task

    asyncio.run(drive())
    kw = seen["SECZ"]
    assert (kw["float_shares"], kw["float_contradicted"], kw["shares_outstanding"]) == (8_450_000, True, 163_270_000)


# -- the setup scanner: the grade's float pillar (20M) and a template's stock filter ---------------------
def _pillars(symbol: str, flag=True) -> dict:
    f, out, _ins, _si = AUDIT[symbol]
    return {"price": 5.0, "change_pct": 30.0, "rvol": 6.0, "news": True, "float": f,
            "float_contradicted": flag, "shares_outstanding": out}


@pytest.mark.parametrize(("symbol", "pillar"), [
    ("SECZ", None), ("WNW", None), ("LGCL", None),       # over 20M shares outstanding: unknown, never failed
    ("RNAZ", True),                                      # 16.93M outstanding is under the 20M pillar
    ("WHLR", True), ("HAO", True), ("HKIT", True),
])
def test_the_grade_float_pillar_reads_shares_outstanding_for_a_contradicted_float(symbol, pillar):
    letter, checks = grade(_pillars(symbol))
    assert checks["float"] is pillar
    assert letter == ("A" if pillar else "B")
    assert "contradicted by its own share counts" in float_note(_pillars(symbol))


def test_a_template_grade_limit_is_the_limit_the_rule_uses():
    ten = GradeRules(min_price=2, max_price=20, min_change_pct=10, min_rvol=5, max_float=10_000_000)
    assert grade(_pillars("RNAZ"), ten)[1]["float"] is None
    assert "over 10.00M" in float_note(_pillars("RNAZ"), ten)


def test_the_grade_behaves_as_before_for_an_unflagged_or_unchecked_float():
    for flag in (False, None):
        assert grade(_pillars("SECZ", flag)) == (
            "A", {"price": True, "change": True, "rvol": True, "news": True, "float": True})
        assert float_note(_pillars("SECZ", flag)) is None
    assert grade({**_pillars("SECZ", None), "float": 0})[1]["float"] is False


def test_the_armed_setup_reads_the_check_from_hod_momo(monkeypatch):
    import catalysts.live as catalyst_live
    import hod_momo

    snap = TickerSnap(price=5.0, change_pct=30.0, rvol=6.0, float_shares=8_450_000, float_contradicted=True,
                      shares_outstanding=163_270_000)
    monkeypatch.setattr(hod_momo, "get_ticker_snapshot", lambda _s: snap)
    monkeypatch.setattr(catalyst_live, "verdict_for", lambda *_a, **_k: None)
    pillars = grade_mod.read_pillars("SECZ", 0.0)
    assert (pillars["float"], pillars["float_contradicted"], pillars["shares_outstanding"]) == (
        8_450_000, True, 163_270_000)
    assert grade(pillars)[1]["float"] is None


def test_replayed_eyes_read_the_check_the_leaderboard_recorded(monkeypatch):
    import catalysts.live as catalyst_live
    from eyes.recording import pillars_at
    from leaderboard import store as lb_store

    monkeypatch.setattr(catalyst_live, "verdict_for", lambda *_a, **_k: None)
    minute = int(datetime(2026, 9, 23, 13, 40, tzinfo=timezone.utc).timestamp())    # 09:40 ET
    row = make_row(symbol="ZZSECZ", minute_ts=minute, board="gainers", source="recorded", rank=1, price=11.2,
                   prev_close=5.0, float_shares=8_450_000, float_contradicted=True, shares_outstanding=163_270_000)
    with lb_store.connect() as db:
        lb_store.write_batch(db, rows=[row])
    p = pillars_at("ZZSECZ", row["session_date"], minute + 30, last_price=11.3, prev_close=5.0)
    assert (p["float"], p["float_contradicted"], p["shares_outstanding"]) == (8_450_000, True, 163_270_000)
    assert grade(p)[1]["float"] is None


def _stock_filter(unknown_passes: bool) -> StockFilter:
    return StockFilter(min_price=None, max_price=None, max_float=10_000_000, min_change_pct=None, min_rvol=None,
                       require_catalyst=False, min_grade="C", unknown_passes=unknown_passes)


@pytest.mark.parametrize("unknown_passes", (True, False))
def test_the_stock_filter_never_passes_a_contradicted_float_shares_outstanding_does_not_rescue(unknown_passes):
    for symbol in OVER_10M:
        why = _stock_filter(unknown_passes).check(_pillars(symbol), "A")
        assert why is not None and "float unknown, not a pass" in why, symbol
    for symbol in RESCUED:
        assert _stock_filter(unknown_passes).check(_pillars(symbol), "A") is None, symbol


def test_the_stock_filter_behaves_as_before_for_an_unflagged_float():
    assert _stock_filter(False).check(_pillars("SECZ", None), "A") is None
    assert _stock_filter(False).check({**_pillars("SECZ", False), "float": 15e6}, "A") == "float 15.0M over 10.0M"
    assert _stock_filter(False).check({**_pillars("SECZ", None), "float": None}, "A") == (
        "float unknown (float ? over 10.0M)")
    assert _stock_filter(True).check({**_pillars("SECZ", None), "float": None}, "A") is None


# -- Five Pillars and the Contenders float score (20M), on the rows the Scanner shows --------------------
def _row(monkeypatch, symbol: str) -> dict:
    _cache(monkeypatch, symbol)
    return mev.decorate_rows([{"symbol": symbol, "price": 5.0, "change_pct": 30.0, "rel_volume": 6.0,
                               "has_news": True}])[0]


@pytest.mark.parametrize(("symbol", "passed"), [
    ("SECZ", False), ("WNW", False), ("LGCL", False),
    ("RNAZ", True), ("WHLR", True), ("HAO", True), ("HKIT", True),
])
def test_five_pillars_float_pillar_reads_shares_outstanding_for_a_contradicted_float(monkeypatch, symbol, passed):
    row = _row(monkeypatch, symbol)
    assert row["float_contradicted"] is True
    pillar = next(c for c in evaluate_five_pillars(row).checks if c.name == "float")
    assert pillar.passed is passed
    assert "contradicted by its own share counts" in pillar.detail


@pytest.mark.parametrize("symbol", ("AAPL", "DBGI"))
def test_five_pillars_float_pillar_is_unchanged_for_a_credible_float(monkeypatch, symbol):
    row = _row(monkeypatch, symbol)
    assert row["float_contradicted"] is False
    bare = {k: v for k, v in row.items() if k not in ("float_contradicted", "float_contradicted_reason",
                                                      "shares_outstanding", "short_interest_ts")}
    assert evaluate_five_pillars(row) == evaluate_five_pillars(bare)


def test_five_pillars_behaves_as_before_for_an_unchecked_float(monkeypatch):
    row = {**_row(monkeypatch, "SECZ"), "float_contradicted": None}
    pillar = next(c for c in evaluate_five_pillars(row).checks if c.name == "float")
    assert (pillar.passed, pillar.detail) == (True, "8,450,000 shares (need <= 20,000,000)")


def test_the_contenders_float_score_reads_the_same_rule(monkeypatch):
    assert score_watchlist_entry(_row(monkeypatch, "SECZ")).sub_scores["float"] == 0.0
    # WHLR scores on its 568K shares outstanding -- the most its float can be -- not on the 54K float.
    assert score_watchlist_entry(_row(monkeypatch, "WHLR")).sub_scores["float"] == pytest.approx(
        (1 - 568_000 / 20_000_000) * 100)
    unchecked = {**_row(monkeypatch, "SECZ"), "float_contradicted": None}
    assert score_watchlist_entry(unchecked).sub_scores["float"] == pytest.approx((1 - 8_450_000 / 20_000_000) * 100)


# -- the leaderboard's LEADERS_RULES (float <= 10M or unknown) --------------------------------------------
def _recorded(monkeypatch, symbol: str) -> dict:
    _cache(monkeypatch, symbol)
    decorated = mev.decorate_rows([{"symbol": symbol, "price": 5.0, "prev_close": 3.85, "volume": 500_000,
                                    "rel_volume": 6.0, "has_news": True}])[0]
    return from_desk_row(decorated, minute_ts=1_790_000_000 // 60 * 60, board="gainers", rank=1)


@pytest.mark.parametrize("symbol", OVER_10M)
def test_leaders_refuse_a_contradicted_float_though_an_unknown_float_qualifies(monkeypatch, symbol):
    row = _recorded(monkeypatch, symbol)
    assert (row["float_contradicted"], row["shares_outstanding"]) == (True, AUDIT[symbol][1])
    assert refusal(row, LEADERS_RULES) == "float_contradicted"
    assert refusal({**row, "float_shares": None, "float_contradicted": None}, LEADERS_RULES) is None


@pytest.mark.parametrize("symbol", RESCUED)
def test_leaders_keep_a_contradicted_float_small_shares_outstanding_rescues(monkeypatch, symbol):
    assert refusal(_recorded(monkeypatch, symbol), LEADERS_RULES) is None


def test_leaders_judge_a_row_without_the_check_as_before():
    rebuilt = make_row(symbol="SECZ", minute_ts=1_790_000_000 // 60 * 60, board="market", source="reconstructed",
                       rank=1, price=5.0, prev_close=3.85, volume=500_000, float_shares=8_450_000)
    assert (rebuilt["float_contradicted"], rebuilt["shares_outstanding"]) == (None, None)
    assert refusal(rebuilt, LEADERS_RULES) is None
    assert refusal({**rebuilt, "float_shares": 15_000_000}, LEADERS_RULES) == "float"


def test_a_recorded_row_keeps_no_check_without_a_float():
    row = make_row(symbol="SECZ", minute_ts=1_790_000_000 // 60 * 60, board="gainers", source="recorded", rank=1,
                   float_shares=None, float_contradicted=True, shares_outstanding=163_270_000)
    assert row["float_contradicted"] is None and row["shares_outstanding"] == 163_270_000
